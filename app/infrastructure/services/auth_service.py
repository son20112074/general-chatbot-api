# from fastapi import Depends, HTTPException
# from app.core.config import settings
# from app.domain.interfaces.services import AuthServiceInterface
# import httpx

# class AuthService(AuthServiceInterface):
#     def __init__(self, base_url: str = settings.AUTH_SERVICE_URL):
#         self.base_url = base_url

#     async def authenticate(self, username: str, password: str) -> dict:
#         async with httpx.AsyncClient() as client:
#             response = await client.post(f"{self.base_url}/login", json={"username": username, "password": password})
#             if response.status_code != 200:
#                 raise HTTPException(status_code=response.status_code, detail=response.json().get("detail", "Authentication failed"))
#             return response.json()

#     async def register(self, username: str, password: str) -> dict:
#         async with httpx.AsyncClient() as client:
#             response = await client.post(f"{self.base_url}/register", json={"username": username, "password": password})
#             if response.status_code != 201:
#                 raise HTTPException(status_code=response.status_code, detail=response.json().get("detail", "Registration failed"))
#             return response.json()