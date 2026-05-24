from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.exceptions import AuthenticationError
from app.infrastructure.services.auth_service import AuthService

class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.auth_service = AuthService()

    async def dispatch(self, request: Request, call_next):
        token = request.headers.get("Authorization")
        
        if not token:
            raise HTTPException(status_code=401, detail="Authorization token is missing")
        
        try:
            user = self.auth_service.verify_token(token)
            request.state.user = user
        except AuthenticationError:
            raise HTTPException(status_code=403, detail="Invalid token")

        response = await call_next(request)
        return response
