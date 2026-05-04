import uvicorn
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import asyncio
from app.core.database import engine, Base
from app.core.errors import AppError, app_error_handler, http_exception_to_app
from app.presentation.api.v1.router import router
from app.core.logger import setup_logging
setup_logging()
from app.crons import start_scheduler, stop_scheduler
import multiprocessing
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="TMS API Service",
    description="A task management system API service",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Structured error responses — {detail, message, code, status}
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(HTTPException, http_exception_to_app)

# Create static directory and subdirectories if they don't exist
def create_static_directories():
    static_dir = "static"
    subdirs = ["uploads", "downloads", "downloads/docx"]
    
    # Create main static directory
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
        print(f"Created directory: {static_dir}")
    
    # Create subdirectories
    for subdir in subdirs:
        full_path = os.path.join(static_dir, subdir)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
            print(f"Created directory: {full_path}")

# Create static directories
create_static_directories()

# Mount static files directory
app.mount("/api/v1/static", StaticFiles(directory="static"), name="static")


# Include API router
app.include_router(router, prefix="")

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
 

if __name__ == "__main__":
    multiprocessing.freeze_support()  # For Windows support
    uvicorn.run(app=app, host="0.0.0.0", port=8000, workers=1, reload=False)

    # uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
    