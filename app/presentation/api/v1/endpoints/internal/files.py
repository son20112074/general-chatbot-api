from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, text as sa_text
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.file_service import FileService
from app.core.query import CursorPaginationResult, QueryInput
from app.domain.services.file_service import FileQueryService
from app.domain.models.file import File as FileModel
from app.domain.models.folder import Folder as FolderModel
from app.domain.models.role import Role as RoleModel
from app.domain.models.user import User
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData
from app.presentation.api.v1.schemas.file import (
    ExtractFileContentRequest, ExtractFileContentResponse,
    FileDashboardResponse, PeriodStatsRequest, PeriodStatsResponse,
    CountryTechStatsRequest, CountryTechStatsResponse,
    FileUpdateSchema, FileMoveSchema, FileListAllSchema,
)
from app.utils.table_lookup import get_table_with_schema
from app.utils.helpers import check_file_permission, compute_and_set_node_path, build_file_item
from typing import List, Optional
from datetime import datetime
from dateutil import parser as date_parser
import os
import docx
import openpyxl
import csv
import codecs

ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID

router = APIRouter()

def parse_datetime_safe(datetime_str: str) -> datetime:
    """
    Parse datetime string and convert to timezone-naive datetime.
    
    Args:
        datetime_str: Datetime string to parse
        
    Returns:
        timezone-naive datetime object
        
    Raises:
        ValueError: If datetime string is invalid
    """
    try:
        parsed_time = date_parser.parse(datetime_str)
        # Convert to timezone-naive datetime if it has timezone info
        if parsed_time.tzinfo is not None:
            return parsed_time.replace(tzinfo=None)
        else:
            return parsed_time
    except Exception as e:
        raise ValueError(f"Invalid datetime format: {str(e)}")



# ── Endpoints ────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    fields: Optional[List[str]] = Query(None, description="Fields to include in response"),
    is_save: bool = Query(True, description="If False, only save file to disk without saving to database"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Upload a file.
    
    The file will be:
    1. Hashed to detect duplicates
    2. Saved to static/uploads directory
    3. Metadata stored in database (if is_save=True)
    4. Returns file information
    
    Parameters:
    - file: The file to upload
    - fields: Optional list of fields to include in response. Use "*" for all fields.
    - is_save: If True (default), save to database. If False, only save to disk.
    """
    try:
        file_service = FileService(session)
        result = await file_service.save_file(file, current_user.user_id, fields, is_save=is_save)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading file: {str(e)}"
        ) 
        

@router.post("/my-files", response_model=CursorPaginationResult)
async def query_with_cursor(
    query_input: QueryInput,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Query files with cursor-based pagination.
    If include_children is True, will include files from current user and all child users.
    
    Parameters:
    - query_input: Query parameters including:
        - table_name: Name of the model/table to query
        - ids: List of IDs to filter by
        - fields: List of fields to select
        - page: Page number (1-based)
        - page_size: Number of items per page
        - cursor: Cursor for pagination
        - sort_by: Field to sort by
        - sort_order: Sort order ("asc" or "desc")
        - condition: Dictionary of conditions to filter by
        - include_children: If True, include files from current user and all child users
    """
    try:
        # Get model class from SQLAlchemy metadata with schema support
        model = get_table_with_schema(query_input.table_name)
        
        # Create FileQueryService instance with session
        file_query_service = FileQueryService(session)
        
        # Execute query with user hierarchy support
        result = await file_query_service.query_with_cursor(model, query_input, current_user.user_id)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error executing query: {str(e)}"
        )

@router.post("/my-with-children", response_model=CursorPaginationResult)
async def query_files_with_children(
    query_input: QueryInput,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    Query files from current user and all their child users based on role hierarchy.
    
    Parameters:
    - query_input: Query parameters including:
        - table_name: Name of the model/table to query
        - ids: List of IDs to filter by
        - fields: List of fields to select
        - page: Page number (1-based)
        - page_size: Number of items per page
        - cursor: Cursor for pagination
        - sort_by: Field to sort by
        - sort_order: Sort order ("asc" or "desc")
        - condition: Dictionary of conditions to filter by
        - search_text: Text to search for
        - search_fields: List of fields to search in
    """
    try:
        # Get model class from SQLAlchemy metadata with schema support
        model = get_table_with_schema(query_input.table_name)
        
        # Create FileQueryService instance with session
        file_query_service = FileQueryService(session)
        
        # Execute query specifically for files with children
        result = await file_query_service.query_user_files_with_children(model, query_input, current_user.user_id)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error executing query: {str(e)}"
        )


# File content extraction functions
def extract_docx_content(file_path: str) -> str:
    """Trích xuất nội dung từ file DOCX"""
    try:
        doc = docx.Document(file_path)
        content = []
        
        # Trích xuất text từ các paragraph
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                content.append(paragraph.text.strip())
        
        # Trích xuất text từ các bảng
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    if cell.text.strip():
                        row_text.append(cell.text.strip())
                if row_text:
                    content.append(" | ".join(row_text))
        
        return "\n".join(content)
    except Exception as e:
        raise Exception(f"Lỗi khi đọc file DOCX: {str(e)}")


def extract_doc_content(file_path: str) -> str:
    """Trích xuất nội dung từ file DOC (cần python-docx2txt hoặc antiword)"""
    try:
        # Thử sử dụng python-docx2txt nếu có
        try:
            import docx2txt
            content = docx2txt.process(file_path)
            return content if content else "Không thể trích xuất nội dung từ file DOC"
        except ImportError:
            return "Cần cài đặt thư viện docx2txt để đọc file DOC"
    except Exception as e:
        raise Exception(f"Lỗi khi đọc file DOC: {str(e)}")


def extract_xlsx_content(file_path: str) -> str:
    """Trích xuất nội dung từ file XLSX"""
    try:
        workbook = openpyxl.load_workbook(file_path, data_only=True)
        content = []
        
        for sheet_name in workbook.sheetnames:
            worksheet = workbook[sheet_name]
            content.append(f"=== Sheet: {sheet_name} ===")
            
            for row in worksheet.iter_rows(values_only=True):
                # Lọc các cell không rỗng
                row_data = [str(cell) if cell is not None else "" for cell in row]
                if any(cell.strip() for cell in row_data if cell):
                    content.append(" | ".join(row_data))
        
        workbook.close()
        return "\n".join(content)
    except Exception as e:
        raise Exception(f"Lỗi khi đọc file XLSX: {str(e)}")


def extract_text_content(file_path: str) -> str:
    """Trích xuất nội dung từ file TXT hoặc DAT"""
    try:
        # Thử các encoding khác nhau
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'ascii']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as file:
                    content = file.read()
                    return content
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        # Nếu tất cả encoding đều thất bại, thử đọc dưới dạng binary
        with open(file_path, 'rb') as file:
            raw_content = file.read()
            # Thử decode với errors='ignore'
            content = raw_content.decode('utf-8', errors='ignore')
            return content
            
    except Exception as e:
        raise Exception(f"Lỗi khi đọc file text: {str(e)}")


def extract_csv_content(file_path: str) -> str:
    """Trích xuất nội dung từ file CSV"""
    try:
        content = []
        
        # Thử các encoding khác nhau
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding, newline='') as csvfile:
                    # Tự động phát hiện delimiter
                    sample = csvfile.read(1024)
                    csvfile.seek(0)
                    
                    delimiter = ','
                    if '\t' in sample:
                        delimiter = '\t'
                    elif ';' in sample:
                        delimiter = ';'
                    
                    csv_reader = csv.reader(csvfile, delimiter=delimiter)
                    
                    for row_num, row in enumerate(csv_reader, 1):
                        if row and any(cell.strip() for cell in row):
                            content.append(f"Row {row_num}: {' | '.join(row)}")
                    
                    return "\n".join(content)
                    
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        raise Exception("Không thể đọc file CSV với bất kỳ encoding nào")
        
    except Exception as e:
        raise Exception(f"Lỗi khi đọc file CSV: {str(e)}")


@router.post("/extract-file-content", response_model=ExtractFileContentResponse)
async def extract_file_content(
    request: ExtractFileContentRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """
    API để trích xuất nội dung từ file trong thư mục static
    Hỗ trợ các định dạng: doc, docx, xlsx, txt, csv, dat
    """
    try:
        file_path = request.file_path
        
        # Kiểm tra file_path có chứa đường dẫn đầy đủ tới thư mục static
        if not file_path.startswith('static'):
            file_path = f"static/{file_path}"
        
        # Kiểm tra file có tồn tại không
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"File {file_path} không tồn tại"
            )
        
        # Lấy phần mở rộng của file
        file_extension = os.path.splitext(file_path)[1].lower()
        
        # Danh sách các phần mở rộng được hỗ trợ
        supported_extensions = ['.doc', '.docx', '.xlsx', '.txt', '.csv', '.dat']
        
        if file_extension not in supported_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Định dạng file {file_extension} không được hỗ trợ. Chỉ hỗ trợ: {', '.join(supported_extensions)}"
            )
        
        content = ""
        
        # Trích xuất nội dung dựa trên định dạng file
        if file_extension == '.docx':
            content = extract_docx_content(file_path)
        elif file_extension == '.doc':
            content = extract_doc_content(file_path)
        elif file_extension == '.xlsx':
            content = extract_xlsx_content(file_path)
        elif file_extension in ['.txt', '.dat']:
            content = extract_text_content(file_path)
        elif file_extension == '.csv':
            content = extract_csv_content(file_path)
        
        # Lấy thông tin file
        file_stats = os.stat(file_path)
        file_info = {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "file_size": file_stats.st_size,
            "file_extension": file_extension,
            "modified_time": datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
            "content": content,
            "content_length": len(content)
        }
        
        return file_info
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi trích xuất nội dung file: {str(e)}"
        )


@router.get("/dashboard", response_model=FileDashboardResponse)
async def get_file_dashboard(
    from_time: Optional[datetime] = Query(None, description="Thời gian bắt đầu (ISO format)"),
    to_time: Optional[datetime] = Query(None, description="Thời gian kết thúc (ISO format)"),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    API để lấy thống kê dashboard cho file
    Bao gồm: tổng số file, dung lượng, số file đã xử lý/chưa xử lý, thống kê theo extension
    Có thể lọc theo khoảng thời gian với from_time và to_time
    """
    try:
        from sqlalchemy import func, case, select
        from app.domain.models import File
        
        # Lấy danh sách user IDs trong hierarchy
        file_query_service = FileQueryService(session)
        user_ids = await file_query_service.get_user_hierarchy_ids(current_user.user_id)
        
        # Xây dựng điều kiện lọc theo thời gian
        time_conditions = []
        if from_time:
            time_conditions.append(File.created_at >= from_time)
        if to_time:
            time_conditions.append(File.created_at <= to_time)
        
        # Tổng số file và tổng dung lượng
        total_query_conditions = [File.created_by.in_(user_ids)] + time_conditions
        total_query = await session.execute(
            select(
                func.count(File.id).label('total_files'),
                func.coalesce(func.sum(File.size), 0).label('total_size')
            ).where(*total_query_conditions)
        )
        total_result = total_query.first()
        total_files = total_result.total_files or 0
        total_size = total_result.total_size or 0
        
        # Số file đã xử lý và chưa xử lý
        processed_query_conditions = [File.created_by.in_(user_ids)] + time_conditions
        processed_query = await session.execute(
            select(
                func.count(case((File.is_processed == True, 1))).label('processed'),
                func.count(case((File.is_processed == False, 1))).label('unprocessed'),
                func.count(case((File.is_processed.is_(None), 1))).label('pending')
            ).where(*processed_query_conditions)
        )
        processed_result = processed_query.first()
        processed_files = processed_result.processed or 0
        unprocessed_files = (processed_result.unprocessed or 0) + (processed_result.pending or 0)
        
        # Thống kê theo extension
        extension_query_conditions = [File.created_by.in_(user_ids)] + time_conditions
        extension_query = await session.execute(
            select(
                File.extension,
                func.count(File.id).label('count')
            ).where(*extension_query_conditions)
            .group_by(File.extension)
            .order_by(func.count(File.id).desc())
        )
        extension_results = extension_query.all()
        files_by_extension = {row.extension or 'unknown': row.count for row in extension_results}
        
        # Thống kê theo trạng thái xử lý
        status_query_conditions = [File.created_by.in_(user_ids)] + time_conditions
        status_query = await session.execute(
            select(
                case(
                    (File.is_processed == True, 'processed'),
                    (File.is_processed == False, 'failed'),
                    (File.is_processed.is_(None), 'pending')
                ).label('status'),
                func.count(File.id).label('count')
            ).where(*status_query_conditions)
            .group_by(File.is_processed)
        )
        status_results = status_query.all()
        files_by_status = {row.status: row.count for row in status_results}
        
        # Tính thời gian xử lý trung bình (chỉ cho các file đã xử lý có processing_duration)
        avg_duration_query_conditions = [
            File.created_by.in_(user_ids),
            File.is_processed == True,
            File.processing_duration.isnot(None)
        ] + time_conditions
        avg_duration_query = await session.execute(
            select(
                func.avg(File.processing_duration).label('avg_duration')
            ).where(*avg_duration_query_conditions)
        )
        avg_duration_result = avg_duration_query.first()
        avg_processing_duration = round(avg_duration_result.avg_duration, 2) if avg_duration_result.avg_duration else None
        
        # Tính tỷ lệ xử lý
        processing_rate = (processed_files / total_files * 100) if total_files > 0 else 0
        
        # Chuyển đổi dung lượng sang MB
        total_size_mb = round(total_size / (1024 * 1024), 2)
        
        return FileDashboardResponse(
            total_files=total_files,
            total_size=total_size,
            total_size_mb=total_size_mb,
            processed_files=processed_files,
            unprocessed_files=unprocessed_files,
            processing_rate=round(processing_rate, 2),
            avg_processing_duration=avg_processing_duration,
            files_by_extension=files_by_extension,
            files_by_status=files_by_status
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi lấy thống kê dashboard: {str(e)}"
        )


@router.post("/period-stats", response_model=PeriodStatsResponse)
async def get_period_statistics(
    request: PeriodStatsRequest,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    API để lấy thống kê file theo kỳ (ngày, tháng, quý, năm)
    
    Parameters:
    - period: Kỳ thống kê ('day', 'month', 'quarter', 'year')
    - from_time: Thời gian bắt đầu (optional)
    - to_time: Thời gian kết thúc (optional)
    """
    try:
        from sqlalchemy import func, case, select, extract, text
        from app.domain.models import File
        
        # Validate period parameter
        valid_periods = ['day', 'month', 'quarter', 'year']
        if request.period not in valid_periods:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid period. Must be one of: {', '.join(valid_periods)}"
            )
        
        # Parse time parameters
        from_time = None
        to_time = None
        
        if request.from_time:
            try:
                from_time = parse_datetime_safe(request.from_time)
                print(f"Parsed from_time: {from_time} (timezone-naive: {from_time.tzinfo is None})")
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid from_time format: {str(e)}"
                )
        
        if request.to_time:
            try:
                to_time = parse_datetime_safe(request.to_time)
                print(f"Parsed to_time: {to_time} (timezone-naive: {to_time.tzinfo is None})")
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid to_time format: {str(e)}"
                )
        
        # Lấy danh sách user IDs trong hierarchy
        file_query_service = FileQueryService(session)
        user_ids = await file_query_service.get_user_hierarchy_ids(current_user.user_id)
        
        # Base query with user hierarchy filter
        base_query = select(File).where(File.created_by.in_(user_ids))
        
        # Add time filters if provided
        if from_time:
            base_query = base_query.where(File.created_at >= from_time)
        if to_time:
            base_query = base_query.where(File.created_at <= to_time)
        
        # Build period grouping based on period type
        if request.period == 'day':
            period_expr = func.date(File.created_at)
            period_label = 'date'
        elif request.period == 'month':
            period_expr = func.date_trunc('month', File.created_at)
            period_label = 'month'
        elif request.period == 'quarter':
            period_expr = func.date_trunc('quarter', File.created_at)
            period_label = 'quarter'
        elif request.period == 'year':
            period_expr = func.date_trunc('year', File.created_at)
            period_label = 'year'
        
        # Get period statistics
        stats_query = await session.execute(
            select(
                period_expr.label('period_date'),
                func.count(File.id).label('file_count'),
                func.coalesce(func.sum(File.size), 0).label('total_size')
            )
            .where(File.created_by.in_(user_ids))
            .where(from_time <= File.created_at if from_time else True)
            .where(File.created_at <= to_time if to_time else True)
            .group_by(period_expr)
            .order_by(period_expr)
        )
        
        stats_results = stats_query.all()
        
        # Format statistics data
        statistics = []
        total_files = 0
        total_size = 0
        
        for row in stats_results:
            period_date = row.period_date
            file_count = row.file_count
            size = row.total_size
            
            total_files += file_count
            total_size += size
            
            # Format period display based on type
            if request.period == 'day':
                period_display = period_date.strftime('%Y-%m-%d')
            elif request.period == 'month':
                period_display = period_date.strftime('%Y-%m')
            elif request.period == 'quarter':
                year = period_date.year
                quarter = (period_date.month - 1) // 3 + 1
                period_display = f"{year}-Q{quarter}"
            elif request.period == 'year':
                period_display = str(period_date.year)
            
            statistics.append({
                period_label: period_display,
                'file_count': file_count,
                'total_size': size,
                'total_size_mb': round(size / (1024 * 1024), 2)
            })
        
        # Get files by extension for the period
        extension_query = await session.execute(
            select(
                File.extension,
                func.count(File.id).label('count')
            )
            .where(File.created_by.in_(user_ids))
            .where(from_time <= File.created_at if from_time else True)
            .where(File.created_at <= to_time if to_time else True)
            .group_by(File.extension)
            .order_by(func.count(File.id).desc())
        )
        extension_results = extension_query.all()
        files_by_extension = {row.extension or 'unknown': row.count for row in extension_results}
        
        # Get files by status for the period
        status_query = await session.execute(
            select(
                case(
                    (File.is_processed == True, 'processed'),
                    (File.is_processed == False, 'failed'),
                    (File.is_processed.is_(None), 'pending')
                ).label('status'),
                func.count(File.id).label('count')
            )
            .where(File.created_by.in_(user_ids))
            .where(from_time <= File.created_at if from_time else True)
            .where(File.created_at <= to_time if to_time else True)
            .group_by(File.is_processed)
        )
        status_results = status_query.all()
        files_by_status = {row.status: row.count for row in status_results}
        
        # Calculate total size in MB
        total_size_mb = round(total_size / (1024 * 1024), 2)
        
        return PeriodStatsResponse(
            period=request.period,
            from_time=request.from_time,
            to_time=request.to_time,
            total_files=total_files,
            total_size=total_size,
            total_size_mb=total_size_mb,
            statistics=statistics,
            files_by_extension=files_by_extension,
            files_by_status=files_by_status
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi lấy thống kê theo kỳ: {str(e)}"
        )


@router.post("/country-tech-stats", response_model=CountryTechStatsResponse)
async def get_country_technology_statistics(
    request: CountryTechStatsRequest,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """
    API để lấy thống kê tần suất số lượng tài liệu nhắc đến các quốc gia và công nghệ
    trong khoảng thời gian từ from_time đến to_time
    
    Parameters:
    - from_time: Thời gian bắt đầu (optional)
    - to_time: Thời gian kết thúc (optional)
    - sort_by: Sắp xếp theo 'count' hoặc 'name' (default: 'count')
    - sort_order: Thứ tự sắp xếp 'asc' hoặc 'desc' (default: 'desc')
    - limit: Giới hạn số lượng kết quả trả về (optional)
    """
    try:
        from sqlalchemy import func, select, text
        from app.domain.models import File
        
        # Parse time parameters
        from_time = None
        to_time = None
        
        if request.from_time:
            try:
                from_time = parse_datetime_safe(request.from_time)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid from_time format: {str(e)}"
                )
        
        if request.to_time:
            try:
                to_time = parse_datetime_safe(request.to_time)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid to_time format: {str(e)}"
                )
        
        # Validate sort parameters
        if request.sort_by not in ['count', 'name']:
            raise HTTPException(
                status_code=400,
                detail="sort_by must be 'count' or 'name'"
            )
        
        if request.sort_order not in ['asc', 'desc']:
            raise HTTPException(
                status_code=400,
                detail="sort_order must be 'asc' or 'desc'"
            )
        
        # Lấy danh sách user IDs trong hierarchy
        file_query_service = FileQueryService(session)
        user_ids = await file_query_service.get_user_hierarchy_ids(current_user.user_id)
        
        # Base query with user hierarchy filter
        base_query = select(File).where(File.created_by.in_(user_ids))
        
        # Add time filters if provided
        if from_time:
            base_query = base_query.where(File.created_at >= from_time)
        if to_time:
            base_query = base_query.where(File.created_at <= to_time)
        
        # Get total files count
        total_files_query = select(func.count(File.id)).where(File.created_by.in_(user_ids))
        if from_time:
            total_files_query = total_files_query.where(File.created_at >= from_time)
        if to_time:
            total_files_query = total_files_query.where(File.created_at <= to_time)
        
        total_files_result = await session.execute(total_files_query)
        total_files = total_files_result.scalar() or 0
        
        # Get listed_nations statistics
        nations_query = select(
            func.unnest(File.listed_nation).label('nation'),
            func.count(File.id).label('count')
        ).where(File.created_by.in_(user_ids)) \
         .where(File.listed_nation.isnot(None)) \
         .where(func.array_length(File.listed_nation, 1) > 0)
        
        if from_time:
            nations_query = nations_query.where(File.created_at >= from_time)
        if to_time:
            nations_query = nations_query.where(File.created_at <= to_time)
            
        nations_query = nations_query.group_by(func.unnest(File.listed_nation)) \
         .order_by(
             func.count(File.id).desc() if request.sort_by == 'count' and request.sort_order == 'desc'
             else func.count(File.id).asc() if request.sort_by == 'count' and request.sort_order == 'asc'
             else func.unnest(File.listed_nation).asc() if request.sort_by == 'name' and request.sort_order == 'asc'
             else func.unnest(File.listed_nation).desc()
         )
        
        # Apply limit if specified
        if request.limit:
            nations_query = nations_query.limit(request.limit)
        
        nations_results = (await session.execute(nations_query)).all()
        listed_nations = [
            {
                "name": row.nation,
                "count": row.count,
                "percentage": round((row.count / total_files * 100), 2) if total_files > 0 else 0
            }
            for row in nations_results
        ]
        
        # Get listed_technologies statistics
        technologies_query = select(
            func.unnest(File.listed_technology).label('technology'),
            func.count(File.id).label('count')
        ).where(File.created_by.in_(user_ids)) \
         .where(File.listed_technology.isnot(None)) \
         .where(func.array_length(File.listed_technology, 1) > 0)
        
        if from_time:
            technologies_query = technologies_query.where(File.created_at >= from_time)
        if to_time:
            technologies_query = technologies_query.where(File.created_at <= to_time)
            
        technologies_query = technologies_query.group_by(func.unnest(File.listed_technology)) \
         .order_by(
             func.count(File.id).desc() if request.sort_by == 'count' and request.sort_order == 'desc'
             else func.count(File.id).asc() if request.sort_by == 'count' and request.sort_order == 'asc'
             else func.unnest(File.listed_technology).asc() if request.sort_by == 'name' and request.sort_order == 'asc'
             else func.unnest(File.listed_technology).desc()
         )
        
        # Apply limit if specified
        if request.limit:
            technologies_query = technologies_query.limit(request.limit)
        
        technologies_results = (await session.execute(technologies_query)).all()
        listed_technologies = [
            {
                "name": row.technology,
                "count": row.count,
                "percentage": round((row.count / total_files * 100), 2) if total_files > 0 else 0
            }
            for row in technologies_results
        ]
        
        # Get unique counts
        total_nations = len(listed_nations)
        total_technologies = len(listed_technologies)
        
        return CountryTechStatsResponse(
            from_time=request.from_time,
            to_time=request.to_time,
            total_files=total_files,
            listed_nations=listed_nations,
            listed_technologies=listed_technologies,
            total_nations=total_nations,
            total_technologies=total_technologies
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi lấy thống kê quốc gia và công nghệ: {str(e)}"
        )



@router.get("/detail/{file_id}",
            summary="Get file detail",
            description="Get full file detail by ID including all metadata, content, classification, owner info, and node_path.")
async def get_file_detail(
    file_id: int,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(FileModel, User.id.label("u_id"), User.full_name.label("u_name"))
        .outerjoin(User, FileModel.created_by == User.id)
        .where(and_(FileModel.id == file_id, or_(FileModel.is_deleted == False, FileModel.is_deleted == None)))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    data = row[0].to_dict()
    data["owner"] = {"id": row.u_id, "full_name": row.u_name} if row.u_id else None
    return data


@router.put("/update/{file_id}",
            summary="Update file name",
            description="Only the creator or admin (role_id=1) can update.")
async def update_file(
    file_id: int,
    data: FileUpdateSchema,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(FileModel).where(and_(FileModel.id == file_id, or_(FileModel.is_deleted == False, FileModel.is_deleted == None)))
    )
    file_obj = result.scalar_one_or_none()
    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        check_file_permission(file_obj, current_user.user_id, current_user.role_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if data.name is not None:
        file_obj.name = data.name
    await session.commit()
    await session.refresh(file_obj)
    return file_obj.to_dict()


@router.delete("/delete/{file_id}", status_code=204,
               summary="Soft delete a file",
               description="Only the creator or admin (role_id=1) can delete.")
async def delete_file(
    file_id: int,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(FileModel).where(and_(FileModel.id == file_id, or_(FileModel.is_deleted == False, FileModel.is_deleted == None)))
    )
    file_obj = result.scalar_one_or_none()
    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        check_file_permission(file_obj, current_user.user_id, current_user.role_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    file_obj.is_deleted = True
    await session.commit()


@router.put("/move/{file_id}",
            summary="Move file to another folder",
            description="Re-computes node_path. Only the creator or admin can move.")
async def move_file(
    file_id: int,
    data: FileMoveSchema,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(FileModel).where(and_(FileModel.id == file_id, or_(FileModel.is_deleted == False, FileModel.is_deleted == None)))
    )
    file_obj = result.scalar_one_or_none()
    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        check_file_permission(file_obj, current_user.user_id, current_user.role_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    file_obj.folder_id = data.new_folder_id
    await compute_and_set_node_path(session, file_obj)
    await session.commit()
    await session.refresh(file_obj)
    return file_obj.to_dict()


@router.post("/list-all",
             summary="Get all accessible files (flat list)",
             description="""Returns files the current user is allowed to see, sorted by created_at DESC.

**Visibility rules:**
- Own files (created_by = current user)
- Files from subordinate roles (child roles in hierarchy)
- Admin (role_id=1) sees all files
- Does NOT show files from other users at the same role level
- Private files only visible to their creator (admin sees all)

**Subtree filter (`started_node` + `type_node`):** both must be sent together.
Matches files whose `node_path` contains the segment `<type_node>_<started_node>`.
Recursive — any file anywhere below that node is returned.

- `started_node=4, type_node="folder"` → files with node_path containing `folder_4/`
- `started_node=3, type_node="role"`   → files under role 3 subtree
- `started_node=5, type_node="user"`   → files owned by user 5 in their user-node

**Search (`search_text`):** case-insensitive OR across file name, containing folder name,
owner full_name, and pinned role name.

**Filters:** `type`, `owner_name`, `is_processed`. All optional.

**`is_processed`:**
- `true` → only processed files
- `false` → only failed files
- omit or `null` → all files (no filter)

**Sort (`sort_by` + `sort_order`):** supports single or multi-field sorting.
Fields: `created_at` (default), `size`. Direction: `desc` (default), `asc`.

- Single: `"sort_by": "size", "sort_order": "asc"`
- Multi: `"sort_by": "size,created_at", "sort_order": "asc,desc"` → ORDER BY size ASC, created_at DESC
- If fewer sort_order values than sort_by, the last direction is reused.""")
async def list_all_files(
    query_params: FileListAllSchema,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        user_id = current_user.user_id
        user_role_id = current_user.role_id

        # ── Per-type visibility ──────────────────────────────────
        # - organization: files at own role + subordinate roles (by role
        #   hierarchy). Uses file.role_id — NOT file.created_by — so
        #   historical files left behind by transferred users stay visible.
        # - private:      only creator
        # - general:      everyone (no owner filter)
        # - admin:        sees everything regardless of type
        if user_role_id == ADMIN_ROLE_ID:
            visibility_filter = []
        else:
            # Resolve subordinate role ids
            child_roles_result = await session.execute(sa_text("""
                SELECT id FROM roles
                WHERE parent_path ILIKE :exact_path
                OR parent_path ILIKE :anywhere_path
            """), {
                "exact_path": f",{user_role_id},",
                "anywhere_path": f"%,{user_role_id},%",
            })
            child_role_ids = [row[0] for row in child_roles_result.fetchall()]
            allowed_role_ids = [user_role_id] + child_role_ids

            visibility_filter = [
                or_(
                    # general — visible to everyone
                    FileModel.type == "general",
                    # private — only creator
                    and_(
                        FileModel.type == "private",
                        FileModel.created_by == user_id,
                    ),
                    # organization at own role — same-role isolation:
                    # only files created by self (peers hidden)
                    and_(
                        FileModel.type == "organization",
                        FileModel.role_id == user_role_id,
                        FileModel.created_by == user_id,
                    ),
                    # organization at subordinate roles — see all files
                    and_(
                        FileModel.type == "organization",
                        FileModel.role_id.in_(child_role_ids),
                    ) if child_role_ids else and_(False),
                )
            ]

        base_cond = and_(
            or_(FileModel.is_deleted == False, FileModel.is_deleted == None),
            *visibility_filter,
        )

        # Single query builder joined with User/Folder/Role so we can
        # filter and search across all of them in one pass. Reused for
        # both the page query and the count query to keep filters in sync.
        def _base():
            return (
                select(FileModel, User.id.label("u_id"), User.full_name.label("u_name"))
                .outerjoin(User, FileModel.created_by == User.id)
                .outerjoin(FolderModel, FileModel.folder_id == FolderModel.id)
                .outerjoin(RoleModel, FileModel.role_id == RoleModel.id)
                .where(base_cond)
            )

        def _count_base():
            return (
                select(func.count(FileModel.id))
                .select_from(FileModel)
                .outerjoin(User, FileModel.created_by == User.id)
                .outerjoin(FolderModel, FileModel.folder_id == FolderModel.id)
                .outerjoin(RoleModel, FileModel.role_id == RoleModel.id)
                .where(base_cond)
            )

        query = _base()
        count_query = _count_base()

        # ── Subtree filter via node_path ─────────────────────────
        # node_path format: "type_<type>/role_<id>/.../user_<id>/folder_<id>/..."
        # To match a segment like `folder_4`, append "/" to node_path and
        # look for "/folder_4/" — this catches both tail and middle cases.
        if query_params.started_node is not None and query_params.type_node:
            segment = f"{query_params.type_node}_{query_params.started_node}"
            pattern = f"%/{segment}/%"
            node_match = func.concat(FileModel.node_path, "/").ilike(pattern)
            query = query.where(node_match)
            count_query = count_query.where(node_match)

        # ── type filter ──────────────────────────────────────────
        if query_params.type:
            query = query.where(FileModel.type == query_params.type)
            count_query = count_query.where(FileModel.type == query_params.type)

        # ── owner_name filter ────────────────────────────────────
        if query_params.owner_name:
            owner_cond = User.full_name.ilike(f"%{query_params.owner_name}%")
            query = query.where(owner_cond)
            count_query = count_query.where(owner_cond)

        # ── Free-text search across file/folder/owner/role names ──
        if query_params.search_text:
            like = f"%{query_params.search_text}%"
            search_cond = or_(
                FileModel.name.ilike(like),
                FolderModel.name.ilike(like),
                User.full_name.ilike(like),
                RoleModel.name.ilike(like),
            )
            query = query.where(search_cond)
            count_query = count_query.where(search_cond)

        # ── is_processed filter ──────────────────────────────────
        if query_params.is_processed is not None:
            proc_cond = FileModel.is_processed == query_params.is_processed
            query = query.where(proc_cond)
            count_query = count_query.where(proc_cond)

        # ── Sort (supports multiple fields: "size,created_at") ──
        sort_field_map = {
            "created_at": FileModel.created_at,
            "size": FileModel.size,
        }
        sort_fields = [s.strip() for s in (query_params.sort_by or "created_at").split(",")]
        sort_orders = [s.strip() for s in (query_params.sort_order or "desc").split(",")]
        order_clauses = []
        for i, field_name in enumerate(sort_fields):
            col = sort_field_map.get(field_name, FileModel.created_at)
            direction = sort_orders[i] if i < len(sort_orders) else sort_orders[-1]
            order_clauses.append(col.asc() if direction == "asc" else col.desc())

        total = (await session.execute(count_query)).scalar_one()
        offset = (query_params.page - 1) * query_params.page_size
        query = query.order_by(*order_clauses).offset(offset).limit(query_params.page_size)

        items = [
            build_file_item(row[0], row.u_id, row.u_name)
            for row in (await session.execute(query)).all()
        ]
        return {"data": items, "total": total, "message": "succeeded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")

