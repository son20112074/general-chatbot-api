from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.domain.services.kpi_service import KPIService
from app.domain.schemas.kpi import (
    EmployeeKPICreate, 
    EmployeeKPIUpdate, 
    EmployeeKPIResponse, 
    EmployeeKPIFilter,
    KPISummaryRequest,
    KPISummaryResponse,
    SelfAssessmentRequest,
    ManagerAssessmentRequest,
    RoleKPISummaryRequest,
    RoleKPISummaryResponse
)
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData

router = APIRouter()

@router.post("/", response_model=EmployeeKPIResponse, summary="Tạo KPI mới")
async def create_kpi(
    kpi_data: EmployeeKPICreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Tạo KPI mới cho nhân viên
    """
    kpi_service = KPIService(db)
    
    # Kiểm tra xem KPI cho kỳ này đã tồn tại chưa
    existing_kpi = await kpi_service.get_kpi_by_period(
        kpi_data.user_id, 
        kpi_data.period_type, 
        kpi_data.period_value
    )
    
    if existing_kpi:
        raise HTTPException(
            status_code=400, 
            detail=f"KPI cho {kpi_data.period_type} {kpi_data.period_value} đã tồn tại"
        )
    
    kpi = await kpi_service.create_kpi(kpi_data)
    return kpi

@router.get("/", response_model=List[EmployeeKPIResponse], summary="Lấy danh sách KPI")
async def get_kpis(
    user_id: Optional[int] = Query(None, description="ID nhân viên"),
    period_type: Optional[str] = Query(None, description="Loại kỳ"),
    period_value: Optional[str] = Query(None, description="Giá trị kỳ"),
    assessed_by: Optional[int] = Query(None, description="ID người đánh giá"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Lấy danh sách KPI với bộ lọc
    """
    kpi_service = KPIService(db)
    
    filters = EmployeeKPIFilter(
        user_id=user_id,
        period_type=period_type,
        period_value=period_value,
        assessed_by=assessed_by
    )
    
    if user_id:
        # Nếu có user_id, chỉ lấy KPI của nhân viên đó
        kpis = await kpi_service.get_kpis_by_user(user_id, filters)
    else:
        # Nếu không có user_id, lấy tất cả KPI
        kpis = await kpi_service.get_all_kpis(filters)
    
    return kpis

@router.get("/{kpi_id}", response_model=EmployeeKPIResponse, summary="Lấy KPI theo ID")
async def get_kpi_by_id(
    kpi_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Lấy thông tin KPI theo ID
    """
    kpi_service = KPIService(db)
    kpi = await kpi_service.get_kpi_by_id(kpi_id)
    
    if not kpi:
        raise HTTPException(status_code=404, detail="KPI không tồn tại")
    
    return kpi

@router.get("/user/{user_id}", response_model=List[EmployeeKPIResponse], summary="Lấy KPI của nhân viên")
async def get_user_kpis(
    user_id: int,
    period_type: Optional[str] = Query(None, description="Loại kỳ"),
    period_value: Optional[str] = Query(None, description="Giá trị kỳ"),
    assessed_by: Optional[int] = Query(None, description="ID người đánh giá"),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Lấy danh sách KPI của một nhân viên cụ thể
    """
    kpi_service = KPIService(db)
    
    filters = EmployeeKPIFilter(
        period_type=period_type,
        period_value=period_value,
        assessed_by=assessed_by
    )
    
    kpis = await kpi_service.get_kpis_by_user(user_id, filters)
    return kpis

@router.put("/{kpi_id}", response_model=EmployeeKPIResponse, summary="Cập nhật KPI")
async def update_kpi(
    kpi_id: int,
    kpi_data: EmployeeKPIUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Cập nhật thông tin KPI
    """
    kpi_service = KPIService(db)
    kpi = await kpi_service.update_kpi(kpi_id, kpi_data)
    
    if not kpi:
        raise HTTPException(status_code=404, detail="KPI không tồn tại")
    
    return kpi

@router.delete("/{kpi_id}", summary="Xóa KPI")
async def delete_kpi(
    kpi_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Xóa KPI
    """
    kpi_service = KPIService(db)
    success = await kpi_service.delete_kpi(kpi_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="KPI không tồn tại")
    
    return {"message": "KPI đã được xóa thành công"}

@router.post("/summary", response_model=KPISummaryResponse, summary="Tổng hợp KPI theo kỳ")
async def get_kpi_summary(
    request: KPISummaryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Tổng hợp thông tin KPI theo kỳ của user hiện tại
    - Đếm tổng số lượng công việc theo từng kỳ trong khoảng thời gian
    - Mapping kỳ với bảng KPI để lấy thông tin đánh giá
    """
    kpi_service = KPIService(db)
    
    # Lấy user_id từ token
    user_id = current_user.user_id
    
    # Lấy tổng hợp KPI
    summary_items = await kpi_service.get_kpi_summary(user_id, request)
    
    return KPISummaryResponse(
        user_id=user_id,
        period_type=request.period_type,
        from_time=request.from_time,
        to_time=request.to_time,
        summary=summary_items
    )

@router.post("/self-assessment", response_model=EmployeeKPIResponse, summary="Tự đánh giá KPI")
async def self_assess_kpi(
    request: SelfAssessmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Tự đánh giá KPI cho người dùng hiện tại
    - Nếu chưa có KPI cho kỳ này: tạo mới
    - Nếu đã có KPI: cập nhật thông tin tự đánh giá
    """
    kpi_service = KPIService(db)
    
    # Lấy user_id từ token
    user_id = current_user.user_id
    
    # Thực hiện tự đánh giá
    kpi = await kpi_service.self_assess_kpi(user_id, request)
    
    return kpi

@router.post("/manager-assessment", response_model=EmployeeKPIResponse, summary="Quản lý đánh giá KPI")
async def manager_assess_kpi(
    request: ManagerAssessmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Quản lý đánh giá KPI cho nhân viên
    - Kiểm tra quyền đánh giá: chỉ quản lý trong chuỗi role path của nhân viên được đánh giá mới được phép
    - Nếu chưa có KPI cho kỳ này: tạo mới
    - Nếu đã có KPI: cập nhật thông tin đánh giá của quản lý
    """
    kpi_service = KPIService(db)
    
    # Lấy user_id từ token
    manager_user_id = current_user.user_id
    
    try:
        # Thực hiện đánh giá
        kpi = await kpi_service.manager_assess_kpi(manager_user_id, request)
        return kpi
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/role-summary", response_model=RoleKPISummaryResponse, summary="Tổng hợp KPI theo role và role con")
async def get_role_kpi_summary(
    request: RoleKPISummaryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user)
):
    """
    Lấy thông tin KPI theo role và role con của user hiện tại
    - Lấy tất cả user thuộc cùng role và role con
    - Đếm số công việc của tất cả user đó trong khoảng thời gian
    - Map với thông tin trong bảng KPI theo period_type và period_value cụ thể
    - Sắp xếp kết quả theo role_path (theo thứ tự alphabet)
    - Trả về thông tin: Nhân viên, Vị trí, Role Path, Role Parent Path, Avatar, Công việc, Task Work, Tự đánh giá, Lý do tự đánh giá, QL đánh giá, Lý do QL đánh giá
    """
    kpi_service = KPIService(db)
    
    # Lấy user_id từ token
    user_id = current_user.user_id
    
    # Lấy tổng hợp KPI theo role
    summary_items = await kpi_service.get_role_kpi_summary(user_id, request)
    
    return RoleKPISummaryResponse(
        from_time=request.from_time,
        to_time=request.to_time,
        summary=summary_items
    )
