from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# Request/Response schemas for extract-file-content endpoint
class ExtractFileContentRequest(BaseModel):
    file_path: str = Field(..., description="Đường dẫn đến file cần trích xuất nội dung")

class ExtractFileContentResponse(BaseModel):
    file_path: str = Field(..., description="Đường dẫn file")
    file_name: str = Field(..., description="Tên file")
    file_size: int = Field(..., description="Kích thước file (bytes)")
    file_extension: str = Field(..., description="Phần mở rộng file")
    modified_time: str = Field(..., description="Thời gian chỉnh sửa cuối")
    content: str = Field(..., description="Nội dung được trích xuất")
    content_length: int = Field(..., description="Độ dài nội dung")
    success: bool = Field(default=True, description="Trạng thái thành công")
    message: str = Field(default="Trích xuất nội dung file thành công", description="Thông báo")

# Dashboard response schema
class FileDashboardResponse(BaseModel):
    total_files: int = Field(..., description="Tổng số lượng file")
    total_size: int = Field(..., description="Tổng dung lượng file (bytes)")
    total_size_mb: float = Field(..., description="Tổng dung lượng file (MB)")
    processed_files: int = Field(..., description="Số lượng file đã xử lý")
    unprocessed_files: int = Field(..., description="Số lượng file chưa xử lý")
    processing_rate: float = Field(..., description="Tỷ lệ xử lý (%)")
    avg_processing_duration: Optional[float] = Field(None, description="Thời gian xử lý trung bình (giây)")
    files_by_extension: dict = Field(..., description="Số lượng file theo phần mở rộng")
    files_by_status: dict = Field(..., description="Số lượng file theo trạng thái xử lý")

# Period statistics
class PeriodStatsRequest(BaseModel):
    period: str = Field(..., description="Kỳ thống kê: 'day', 'month', 'quarter', 'year'")
    from_time: Optional[str] = Field(None, description="Thời gian bắt đầu (YYYY-MM-DD hoặc YYYY-MM-DD HH:MM:SS)")
    to_time: Optional[str] = Field(None, description="Thời gian kết thúc (YYYY-MM-DD hoặc YYYY-MM-DD HH:MM:SS)")

class PeriodStatsResponse(BaseModel):
    period: str = Field(..., description="Kỳ thống kê")
    from_time: Optional[str] = Field(None, description="Thời gian bắt đầu")
    to_time: Optional[str] = Field(None, description="Thời gian kết thúc")
    total_files: int = Field(..., description="Tổng số lượng file")
    total_size: int = Field(..., description="Tổng dung lượng file (bytes)")
    total_size_mb: float = Field(..., description="Tổng dung lượng file (MB)")
    statistics: List[Dict[str, Any]] = Field(..., description="Thống kê chi tiết theo kỳ")
    files_by_extension: dict = Field(..., description="Số lượng file theo phần mở rộng")
    files_by_status: dict = Field(..., description="Số lượng file theo trạng thái xử lý")

# Country and Technology statistics
class CountryTechStatsRequest(BaseModel):
    from_time: Optional[str] = Field(None, description="Thời gian bắt đầu (YYYY-MM-DD hoặc YYYY-MM-DD HH:MM:SS)")
    to_time: Optional[str] = Field(None, description="Thời gian kết thúc (YYYY-MM-DD hoặc YYYY-MM-DD HH:MM:SS)")
    sort_by: str = Field(default="count", description="Sắp xếp theo: 'count' hoặc 'name'")
    sort_order: str = Field(default="desc", description="Thứ tự sắp xếp: 'asc' hoặc 'desc'")
    limit: Optional[int] = Field(None, description="Giới hạn số lượng kết quả trả về")

class CountryTechStatsResponse(BaseModel):
    from_time: Optional[str] = Field(None, description="Thời gian bắt đầu")
    to_time: Optional[str] = Field(None, description="Thời gian kết thúc")
    total_files: int = Field(..., description="Tổng số lượng file trong khoảng thời gian")
    listed_nations: List[Dict[str, Any]] = Field(..., description="Danh sách quốc gia và số lượng tài liệu")
    listed_technologies: List[Dict[str, Any]] = Field(..., description="Danh sách công nghệ và số lượng tài liệu")
    total_nations: int = Field(..., description="Tổng số quốc gia unique")
    total_technologies: int = Field(..., description="Tổng số công nghệ unique")

# File management schemas
class FileUpdateSchema(BaseModel):
    name: Optional[str] = Field(default=None, examples=[None], description="File name")

class FileMoveSchema(BaseModel):
    new_folder_id: Optional[int] = Field(default=None, examples=[None], description="Target folder ID, null = root")

class FileListAllSchema(BaseModel):
    """Query payload for POST /api/v1/files/list-all.

    `started_node` + `type_node` act together as a subtree filter: files
    are matched when their `node_path` contains the segment
    `<type_node>_<started_node>`. Recursive by nature — any file below
    that node in the tree is returned. Both must be provided together.
    """

    started_node: Optional[int] = Field(
        default=None,
        examples=[None, 4],
        description=(
            "Subtree root id. Combined with `type_node` to filter files by "
            "node_path segment. Must be sent together with `type_node`."
        ),
    )
    type_node: Optional[str] = Field(
        default=None,
        examples=[None, "folder", "role", "user"],
        description=(
            "Type of the subtree root: 'folder', 'role', or 'user'. "
            "Must be sent together with `started_node`."
        ),
    )
    type: Optional[str] = Field(
        default=None,
        examples=[None],
        description="Filter by file type: private / organization / general",
    )
    owner_name: Optional[str] = Field(
        default=None,
        examples=[None],
        description="Filter by creator full_name (ilike)",
    )
    search_text: Optional[str] = Field(
        default=None,
        examples=[None],
        description=(
            "Free-text search. Matches against file name, containing folder "
            "name, owner full_name, or pinned role name (case-insensitive OR)."
        ),
    )
    is_processed: Optional[bool] = Field(
        default=None,
        examples=[None, True, False],
        description="Filter by processing status. null = all, true = processed, false = not processed.",
    )
    sort_by: Optional[str] = Field(
        default="created_at",
        examples=["created_at", "size"],
        description="Sort field: 'created_at' or 'size'. Default: created_at.",
    )
    sort_order: Optional[str] = Field(
        default="desc",
        examples=["desc", "asc"],
        description="Sort direction: 'asc' or 'desc'. Default: desc.",
    )
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _validate_subtree_pair(self):
        if (self.started_node is None) != (self.type_node is None):
            raise ValueError(
                "started_node and type_node must be provided together"
            )
        if self.type_node is not None and self.type_node not in (
            "folder", "role", "user",
        ):
            raise ValueError(
                "type_node must be one of: folder, role, user"
            )
        return self
