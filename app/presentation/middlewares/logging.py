from fastapi import Request, Response
import logging
from starlette.middleware.base import BaseHTTPMiddleware

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger = logging.getLogger("api-proxy-service")
        
        # Log request details
        logger.info(f"Request: {request.method} {request.url}")
        logger.info(f"Headers: {request.headers}")
        
        # Process the request
        response: Response = await call_next(request)
        
        # Log response details
        logger.info(f"Response status: {response.status_code}")
        
        return response

# To use this middleware, add it to your FastAPI app in main.py
# from app.presentation.middlewares.logging import LoggingMiddleware
# app.add_middleware(LoggingMiddleware)