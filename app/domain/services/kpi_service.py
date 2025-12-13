from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, and_, select, any_
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import text
from app.domain.models.kpi import EmployeeKPI
from app.domain.models.task import Task
from app.domain.models.task_work import TaskWork
from app.domain.models.user import User
from app.domain.models.role import Role
from app.domain.schemas.kpi import EmployeeKPICreate, EmployeeKPIUpdate, EmployeeKPIFilter, KPISummaryRequest, KPISummaryItem, UserInfo, SelfAssessmentRequest, ManagerAssessmentRequest, RoleKPISummaryRequest, RoleKPISummaryItem

class KPIService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_kpi(self, kpi_data: EmployeeKPICreate) -> EmployeeKPI:
        """Tạo KPI mới cho nhân viên"""
        db_kpi = EmployeeKPI(**kpi_data.dict())
        self.db.add(db_kpi)
        await self.db.commit()
        await self.db.refresh(db_kpi)
        return db_kpi

    async def get_kpi_by_id(self, kpi_id: int) -> Optional[EmployeeKPI]:
        """Lấy KPI theo ID"""
        result = await self.db.execute(select(EmployeeKPI).where(EmployeeKPI.id == kpi_id))
        return result.scalar_one_or_none()

    async def get_kpis_by_user(self, user_id: int, filters: Optional[EmployeeKPIFilter] = None) -> List[EmployeeKPI]:
        """Lấy danh sách KPI của một nhân viên"""
        query = select(EmployeeKPI).where(EmployeeKPI.user_id == user_id)
        
        if filters:
            if filters.period_type:
                query = query.where(EmployeeKPI.period_type == filters.period_type)
            if filters.period_value:
                query = query.where(EmployeeKPI.period_value == filters.period_value)
            if filters.assessed_by:
                query = query.where(EmployeeKPI.assessed_by == filters.assessed_by)
        
        query = query.order_by(EmployeeKPI.created_at.desc())
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_all_kpis(self, filters: Optional[EmployeeKPIFilter] = None) -> List[EmployeeKPI]:
        """Lấy tất cả KPI với bộ lọc"""
        query = select(EmployeeKPI)
        
        if filters:
            if filters.user_id:
                query = query.where(EmployeeKPI.user_id == filters.user_id)
            if filters.period_type:
                query = query.where(EmployeeKPI.period_type == filters.period_type)
            if filters.period_value:
                query = query.where(EmployeeKPI.period_value == filters.period_value)
            if filters.assessed_by:
                query = query.where(EmployeeKPI.assessed_by == filters.assessed_by)
        
        query = query.order_by(EmployeeKPI.created_at.desc())
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_kpi(self, kpi_id: int, kpi_data: EmployeeKPIUpdate) -> Optional[EmployeeKPI]:
        """Cập nhật KPI"""
        db_kpi = await self.get_kpi_by_id(kpi_id)
        if not db_kpi:
            return None
        
        update_data = kpi_data.dict(exclude_unset=True)
        
        # Tự động cập nhật thời gian đánh giá nếu có dữ liệu mới
        if kpi_data.user_self_assessment is not None:
            update_data["user_assessment_time"] = datetime.utcnow()
        if kpi_data.manager_assessment is not None:
            update_data["manager_assessment_time"] = datetime.utcnow()
        
        for field, value in update_data.items():
            setattr(db_kpi, field, value)
        
        await self.db.commit()
        await self.db.refresh(db_kpi)
        return db_kpi

    async def delete_kpi(self, kpi_id: int) -> bool:
        """Xóa KPI"""
        db_kpi = await self.get_kpi_by_id(kpi_id)
        if not db_kpi:
            return False
        
        await self.db.delete(db_kpi)
        await self.db.commit()
        return True

    async def get_kpi_by_period(self, user_id: int, period_type: str, period_value: str) -> Optional[EmployeeKPI]:
        """Lấy KPI theo kỳ cụ thể của nhân viên"""
        query = select(EmployeeKPI).where(
            and_(
                EmployeeKPI.user_id == user_id,
                EmployeeKPI.period_type == period_type,
                EmployeeKPI.period_value == period_value
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Lấy thông tin user theo ID"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def calculate_auto_kpi(self, user_id: int, period_type: str, period_value: str) -> Optional[float]:
        """Tính toán KPI tự động dựa trên dữ liệu hệ thống"""
        # TODO: Implement logic tính toán KPI tự động
        # Có thể dựa trên số lượng task hoàn thành, thời gian làm việc, etc.
        return None

    async def self_assess_kpi(self, user_id: int, request: SelfAssessmentRequest) -> EmployeeKPI:
        """Tự đánh giá KPI cho người dùng hiện tại"""
        # Kiểm tra xem KPI cho kỳ này đã tồn tại chưa
        existing_kpi = await self.get_kpi_by_period(user_id, request.period_type, request.period_value)
        
        if existing_kpi:
            # Nếu đã có KPI, cập nhật thông tin tự đánh giá
            update_data = EmployeeKPIUpdate(
                user_self_assessment=request.user_self_assessment,
                user_assessment_reason=request.user_assessment_reason
            )
            updated_kpi = await self.update_kpi(existing_kpi.id, update_data)
            return updated_kpi
        else:
            # Nếu chưa có KPI, tạo mới
            kpi_data = EmployeeKPICreate(
                user_id=user_id,
                period_type=request.period_type,
                period_value=request.period_value,
                user_self_assessment=request.user_self_assessment,
                user_assessment_reason=request.user_assessment_reason,
                auto_kpi=None,
                manager_assessment=None,
                manager_assessment_reason=None,
                assessed_by=None
            )
            return await self.create_kpi(kpi_data)

    async def get_kpi_summary(self, user_id: int, request: KPISummaryRequest) -> List[KPISummaryItem]:
        """Tổng hợp KPI theo kỳ với thống kê công việc"""
        summary_items = []
        
        # Tạo danh sách các kỳ trong khoảng thời gian
        periods = self._generate_periods(request.period_type, request.from_time, request.to_time)
        
        for period_value, period_display in periods:
            # Tính toán thời gian bắt đầu và kết thúc cho period này
            period_start, period_end = self._get_period_time_range(request.period_type, period_value)
            
            # Đếm số lượng task và work riêng biệt cho period này
            task_count, work_count = await self._count_tasks_and_works_in_period(user_id, period_start, period_end)
            
            # Lấy thông tin KPI nếu có
            kpi = await self.get_kpi_by_period(user_id, request.period_type, period_value)
            
            # Lấy thông tin người quản lý đánh giá nếu có
            manager_info = None
            if kpi and kpi.assessed_by:
                manager_user = await self.get_user_by_id(kpi.assessed_by)
                if manager_user:
                    manager_info = UserInfo(
                        id=manager_user.id,
                        full_name=manager_user.full_name,
                        account_name=manager_user.account_name,
                        email=manager_user.email,
                        avatar=manager_user.avatar
                    )
            
            # Tạo summary item
            summary_item = KPISummaryItem(
                period=period_display,
                task_count=task_count,
                work_count=work_count,
                user_self_assessment=kpi.user_self_assessment if kpi and kpi.user_self_assessment else None,
                user_assessment_reason=kpi.user_assessment_reason if kpi and kpi.user_assessment_reason else None,
                manager_assessment=kpi.manager_assessment if kpi and kpi.manager_assessment else None,
                manager_assessment_reason=kpi.manager_assessment_reason if kpi and kpi.manager_assessment_reason else None,
                manager_info=manager_info
            )
            
            summary_items.append(summary_item)
        
        return summary_items

    def _generate_periods(self, period_type: str, from_time: datetime, to_time: datetime) -> List[tuple]:
        """Tạo danh sách các kỳ trong khoảng thời gian"""
        periods = []
        current = from_time
        
        if period_type == "daily":
            while current <= to_time:
                period_value = current.strftime("%Y-%m-%d")
                period_display = current.strftime("%d/%m/%Y")
                periods.append((period_value, period_display))
                current += timedelta(days=1)
        
        elif period_type == "monthly":
            while current <= to_time:
                period_value = current.strftime("%Y-%m")
                period_display = f"Tháng {current.month} {current.year}"
                periods.append((period_value, period_display))
                # Chuyển sang tháng tiếp theo
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)
        
        elif period_type == "quarterly":
            while current <= to_time:
                quarter = (current.month - 1) // 3 + 1
                period_value = f"Q{quarter}-{current.year}"
                period_display = f"Q{quarter} {current.year}"
                periods.append((period_value, period_display))
                # Chuyển sang quý tiếp theo
                if quarter == 4:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=quarter * 3 + 1)
        
        elif period_type == "yearly":
            while current <= to_time:
                period_value = str(current.year)
                period_display = str(current.year)
                periods.append((period_value, period_display))
                current = current.replace(year=current.year + 1)
        
        return periods

    def _get_period_time_range(self, period_type: str, period_value: str) -> tuple[datetime, datetime]:
        """Lấy thời gian bắt đầu và kết thúc cho một period cụ thể"""
        if period_type == "daily":
            # period_value format: "2025-07-01"
            start_date = datetime.strptime(period_value, "%Y-%m-%d")
            end_date = start_date + timedelta(days=1)
            
        elif period_type == "monthly":
            # period_value format: "2025-07"
            year, month = period_value.split("-")
            start_date = datetime(int(year), int(month), 1)
            if int(month) == 12:
                end_date = datetime(int(year) + 1, 1, 1)
            else:
                end_date = datetime(int(year), int(month) + 1, 1)
                
        elif period_type == "quarterly":
            # period_value format: "Q1-2025"
            quarter = int(period_value[1])
            year = int(period_value.split("-")[1])
            start_month = (quarter - 1) * 3 + 1
            start_date = datetime(year, start_month, 1)
            if quarter == 4:
                end_date = datetime(year + 1, 1, 1)
            else:
                end_date = datetime(year, start_month + 3, 1)
                
        elif period_type == "yearly":
            # period_value format: "2025"
            year = int(period_value)
            start_date = datetime(year, 1, 1)
            end_date = datetime(year + 1, 1, 1)
            
        else:
            raise ValueError(f"Unsupported period_type: {period_type}")
            
        return start_date, end_date

    async def _count_tasks_and_works_in_period(self, user_id: int, period_start: datetime, period_end: datetime) -> tuple[int, int]:
        """Đếm số lượng task và work riêng biệt trong kỳ cụ thể"""
        # Chuyển datetime về UTC để tránh lỗi timezone
        period_start_utc = period_start.replace(tzinfo=None) if period_start.tzinfo else period_start
        period_end_utc = period_end.replace(tzinfo=None) if period_end.tzinfo else period_end
        
        # Đếm task được assign cho user trong khoảng thời gian của period này
        task_query = text("""
            SELECT COUNT(*) 
            FROM tasks 
            WHERE :user_id = ANY(assigned_to) 
            AND created_at >= :period_start 
            AND created_at < :period_end
        """)
        task_result = await self.db.execute(task_query, {
            "user_id": user_id,
            "period_start": period_start_utc,
            "period_end": period_end_utc
        })
        task_count = task_result.scalar()
        
        # Đếm task work của user trong khoảng thời gian của period này
        task_work_query = select(func.count(TaskWork.id)).where(
            and_(
                TaskWork.created_by == user_id,
                TaskWork.created_at >= period_start_utc,
                TaskWork.created_at < period_end_utc
            )
        )
        task_work_result = await self.db.execute(task_work_query)
        work_count = task_work_result.scalar()
        
        return (task_count or 0), (work_count or 0) 

    async def get_role_kpi_summary(self, current_user_id: int, request: RoleKPISummaryRequest) -> List[RoleKPISummaryItem]:
        """Lấy thông tin KPI theo role và role con của user hiện tại"""
        # Lấy thông tin user hiện tại
        current_user = await self.get_user_by_id(current_user_id)
        if not current_user or not current_user.role_id:
            return []
        
        # Lấy thông tin role của user hiện tại
        current_role = await self._get_role_by_id(current_user.role_id)
        if not current_role:
            return []
        
        # Lấy danh sách role con (các role có parent_path chứa role hiện tại)
        child_roles = await self._get_child_roles(current_role.id)
        
        # Debug: In ra thông tin role
        print(f"Current role: {current_role.name} (ID: {current_role.id}, parent_path: {current_role.parent_path})")
        print(f"Found {len(child_roles)} child roles:")
        for role in child_roles:
            print(f"  - {role.name} (ID: {role.id}, parent_path: {role.parent_path})")
        
        # Lấy tất cả user thuộc role hiện tại và role con
        target_role_ids = [role.id for role in child_roles]  # child_roles đã bao gồm cả role hiện tại
        print(f"Target role IDs: {target_role_ids}")
        users = await self._get_users_by_role_ids(target_role_ids)
        
        # Debug: In ra thông tin user
        print(f"Found {len(users)} users with role IDs: {target_role_ids}")
        for user in users:
            user_role = await self._get_role_by_id(user.role_id) if user.role_id else None
            role_name = user_role.name if user_role else "No role"
            print(f"  - {user.full_name} (ID: {user.id}, Role: {role_name})")
        
        summary_items = []
        
        for user in users:
            # Đếm số lượng task và work của user trong khoảng thời gian
            task_count = await self._count_user_tasks_in_period(user.id, request.from_time, request.to_time)
            work_count = await self._count_user_works_in_period(user.id, request.from_time, request.to_time)
            
            # Lấy thông tin KPI theo period_type và period_value cụ thể
            kpi = await self.get_kpi_by_period(user.id, request.period_type, request.period_value)
            
            # Lấy thông tin role của user
            user_role = await self._get_role_by_id(user.role_id) if user.role_id else None
            position = user_role.name if user_role else "Không có vị trí"
            
            # Lấy đường dẫn role
            role_path = await self._get_role_path(user.role_id) if user.role_id else "Không có vị trí"
            
            # Lấy parent path của role
            role_parent_path = user_role.parent_path if user_role and user_role.parent_path else ""
            
            # Tạo summary item
            summary_item = RoleKPISummaryItem(
                user_id=user.id,
                full_name=user.full_name,
                position=position,
                role_id=user.role_id if user.role_id else 0,
                role_path=role_path,
                role_parent_path=role_parent_path,
                user_avatar=user.avatar,
                task_count=task_count,
                work_count=work_count,
                user_self_assessment=kpi.user_self_assessment if kpi else None,
                user_assessment_reason=kpi.user_assessment_reason if kpi else None,
                manager_assessment=kpi.manager_assessment if kpi else None,
                manager_assessment_reason=kpi.manager_assessment_reason if kpi else None
            )
            
            summary_items.append(summary_item)
        
        # Sắp xếp theo role path (theo thứ tự alphabet)
        summary_items.sort(key=lambda x: x.role_path)
        
        return summary_items

    async def _get_role_by_id(self, role_id: int) -> Optional[Role]:
        """Lấy thông tin role theo ID"""
        result = await self.db.execute(select(Role).where(Role.id == role_id))
        return result.scalar_one_or_none()

    async def _get_role_path(self, role_id: int) -> str:
        """Lấy đường dẫn role (tên các role cha)"""
        role = await self._get_role_by_id(role_id)
        if not role or not role.parent_path:
            return role.name if role else "Không có vị trí"
        
        # Parse parent_path để lấy tên các role cha
        # parent_path format: ",1,2,3," -> lấy role IDs: 1, 2, 3
        path_ids = [int(id_str) for id_str in role.parent_path.strip(',').split(',') if id_str.isdigit()]
        
        if not path_ids:
            return role.name
        
        # Lấy tên các role cha
        parent_roles = []
        for parent_id in path_ids:
            parent_role = await self._get_role_by_id(parent_id)
            if parent_role:
                parent_roles.append(parent_role.name)
        
        # Thêm role hiện tại
        parent_roles.append(role.name)
        
        # Tạo đường dẫn: "Admin > Manager > Employee"
        return " > ".join(parent_roles)

    async def _get_child_roles(self, parent_role_id: int) -> List[Role]:
        """Lấy danh sách role con của role hiện tại"""
        # Query để tìm tất cả role có parent_path chứa role_id hiện tại
        # Bao gồm cả role hiện tại và tất cả role con
        role_query = text("""
            SELECT * FROM roles 
            WHERE id = :parent_role_id
            OR parent_path LIKE :exact_path 
            OR parent_path LIKE :anywhere_path 
            ORDER BY parent_path ASC
        """)
        
        role_result = await self.db.execute(
            role_query,
            {
                "parent_role_id": parent_role_id,  # Bao gồm role hiện tại
                "exact_path": f",{parent_role_id},",  # Exact match cho direct children
                "anywhere_path": f"%,{parent_role_id},%"  # Match anywhere in path cho tất cả descendants
            }
        )
        
        # Convert kết quả thành Role objects
        roles = []
        for row in role_result.fetchall():
            role = Role(
                id=row[0],
                name=row[1],
                level=row[2],
                parent_path=row[3],
                description=row[4],
                created_by=row[5],
                created_at=row[6]
            )
            roles.append(role)
        
        return roles

    async def _get_users_by_role_ids(self, role_ids: List[int]) -> List[User]:
        """Lấy danh sách user theo danh sách role ID"""
        query = select(User).where(User.role_id.in_(role_ids))
        result = await self.db.execute(query)
        return result.scalars().all()

    async def _count_user_tasks_in_period(self, user_id: int, from_time: datetime, to_time: datetime) -> int:
        """Đếm số lượng task của user trong khoảng thời gian"""
        # Chuyển datetime về UTC để tránh lỗi timezone
        from_time_utc = from_time.replace(tzinfo=None) if from_time.tzinfo else from_time
        to_time_utc = to_time.replace(tzinfo=None) if to_time.tzinfo else to_time
        
        # Đếm task được assign cho user trong khoảng thời gian
        task_query = text("""
            SELECT COUNT(*) 
            FROM tasks 
            WHERE :user_id = ANY(assigned_to) 
            AND created_at >= :from_time 
            AND created_at <= :to_time
        """)
        result = await self.db.execute(task_query, {
            "user_id": user_id,
            "from_time": from_time_utc,
            "to_time": to_time_utc
        })
        return result.scalar() or 0

    async def _count_user_works_in_period(self, user_id: int, from_time: datetime, to_time: datetime) -> int:
        """Đếm số lượng task work của user trong khoảng thời gian"""
        # Chuyển datetime về UTC để tránh lỗi timezone
        from_time_utc = from_time.replace(tzinfo=None) if from_time.tzinfo else from_time
        to_time_utc = to_time.replace(tzinfo=None) if to_time.tzinfo else to_time
        
        # Đếm task work được tạo bởi user trong khoảng thời gian
        work_query = select(func.count(TaskWork.id)).where(
            and_(
                TaskWork.created_by == user_id,
                TaskWork.created_at >= from_time_utc,
                TaskWork.created_at <= to_time_utc
            )
        )
        result = await self.db.execute(work_query)
        return result.scalar() or 0

    async def _get_latest_kpi_by_user(self, user_id: int) -> Optional[EmployeeKPI]:
        """Lấy KPI mới nhất của user"""
        query = select(EmployeeKPI).where(
            EmployeeKPI.user_id == user_id
        ).order_by(EmployeeKPI.created_at.desc()).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none() 

    async def _check_manager_permission(self, manager_user_id: int, target_user_id: int) -> bool:
        """Kiểm tra quyền đánh giá của quản lý"""
        # Lấy thông tin quản lý
        manager_user = await self.get_user_by_id(manager_user_id)
        if not manager_user or not manager_user.role_id:
            return False
        
        # Lấy thông tin nhân viên được đánh giá
        target_user = await self.get_user_by_id(target_user_id)
        if not target_user or not target_user.role_id:
            return False
        
        # Nếu quản lý đánh giá chính mình, không cho phép
        if manager_user_id == target_user_id:
            return False
        
        # Lấy role của quản lý
        manager_role = await self._get_role_by_id(manager_user.role_id)
        if not manager_role:
            return False
        
        # Lấy role của nhân viên được đánh giá
        target_role = await self._get_role_by_id(target_user.role_id)
        if not target_role:
            return False
        
        # Kiểm tra xem role của quản lý có trong parent_path của role nhân viên không
        # parent_path format: ",1,2,3," -> kiểm tra xem manager_role.id có trong đó không
        if target_role.parent_path and str(manager_role.id) in target_role.parent_path.split(','):
            return True
        
        return False

    async def manager_assess_kpi(self, manager_user_id: int, request: ManagerAssessmentRequest) -> EmployeeKPI:
        """Quản lý đánh giá KPI cho nhân viên"""
        # Kiểm tra quyền đánh giá
        if not await self._check_manager_permission(manager_user_id, request.user_id):
            raise ValueError("Không có quyền đánh giá nhân viên này")
        
        # Kiểm tra xem KPI cho kỳ này đã tồn tại chưa
        existing_kpi = await self.get_kpi_by_period(request.user_id, request.period_type, request.period_value)
        
        if existing_kpi:
            # Nếu đã có KPI, cập nhật thông tin đánh giá của quản lý
            update_data = EmployeeKPIUpdate(
                manager_assessment=request.manager_assessment,
                manager_assessment_reason=request.manager_assessment_reason,
                assessed_by=manager_user_id
            )
            updated_kpi = await self.update_kpi(existing_kpi.id, update_data)
            return updated_kpi
        else:
            # Nếu chưa có KPI, tạo mới
            kpi_data = EmployeeKPICreate(
                user_id=request.user_id,
                period_type=request.period_type,
                period_value=request.period_value,
                manager_assessment=request.manager_assessment,
                manager_assessment_reason=request.manager_assessment_reason,
                assessed_by=manager_user_id,
                auto_kpi=None,
                user_self_assessment=None,
                user_assessment_reason=None
            )
            return await self.create_kpi(kpi_data)