from typing import List
from fastapi import APIRouter, Depends, HTTPException, status


from app.domain.interfaces.home_repository import HomeRepository
from app.presentation.api.dependencies import get_home_repository, get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.presentation.api.v1.schemas.home import HomeUpdate

router = APIRouter()

@router.get("/")
async def get_homes(
    home_id: str = None,
    repository: HomeRepository = Depends(get_home_repository),
    current_user: TokenData = Depends(get_current_user)
):
    home_list = await repository.get_all(home_id)
    
    return [home.to_dict() for home in home_list]


@router.put("/{home_id}")
async def update_home(
    home_id: str,
    home: HomeUpdate,
    repository: HomeRepository = Depends(get_home_repository),
    current_user: TokenData = Depends(get_current_user)
):
    try:
        updated_device = await repository.update(home_id, home)
        return updated_device
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating device: {str(e)}"
        )
