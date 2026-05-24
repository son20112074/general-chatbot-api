from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.domain.schemas.migration import MigrationRequest, MigrationResponse, MigrationStatusResponse
from app.domain.services.migration_service import MigrationService
from datetime import datetime

router = APIRouter()

@router.post("/run", response_model=MigrationResponse, summary="Chạy migration")
async def run_migration(
    request: MigrationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Chạy migration từ version này sang version khác
    - Kiểm tra version hiện tại
    - Thực hiện migration
    - Trả về kết quả chi tiết
    """
    try:
        migration_service = MigrationService(db)
        result = await migration_service.run_migration(request)
        
        if not result.success:
            raise HTTPException(status_code=400, detail=result.message)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi chạy migration: {str(e)}")

@router.get("/status", response_model=MigrationStatusResponse, summary="Lấy trạng thái migration")
async def get_migration_status(
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Lấy trạng thái migration hiện tại
    - Version hiện tại
    - Version mới nhất
    - Danh sách migration chưa chạy
    - Trạng thái up-to-date
    """
    try:
        migration_service = MigrationService(db)
        return await migration_service.get_migration_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy trạng thái migration: {str(e)}")

@router.post("/upgrade-to-latest", response_model=MigrationResponse, summary="Upgrade lên version mới nhất")
async def upgrade_to_latest(
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Tự động upgrade lên version mới nhất
    - Lấy version hiện tại
    - Lấy version mới nhất
    - Thực hiện migration
    """
    try:
        migration_service = MigrationService(db)
        
        # Lấy trạng thái hiện tại
        status = await migration_service.get_migration_status()
        
        if status.is_up_to_date:
            return MigrationResponse(
                success=True,
                message="Đã ở version mới nhất",
                from_version=status.current_version,
                to_version=status.latest_version,
                executed_at=datetime.utcnow(),
                details="No migration needed"
            )
        
        # Tạo request migration
        request = MigrationRequest(
            from_version=status.current_version,
            to_version=status.latest_version,
            force=force
        )
        
        return await migration_service.run_migration(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi upgrade: {str(e)}") 