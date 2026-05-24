from fastapi import APIRouter
from app.presentation.api.v1.endpoints.internal import auth, users, dashboard
from app.presentation.api.v1.routers import home

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(home.router)
api_router.include_router(users.router)
api_router.include_router(dashboard.router) 