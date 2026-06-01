import json
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)

DEPARTMENTS_SETTING_KEY = "departments"

DEFAULT_DEPARTMENTS_JSON = """[
  {
    "code": "legal",
    "name": "Pháp chế",
    "description": "Phân loại tài liệu liên quan rà soát hợp đồng, tuân thủ quy định và xử lý vấn đề pháp lý."
  },
  {
    "code": "finance_accounting",
    "name": "Tài chính - Kế toán",
    "description": "Phân loại tài liệu liên quan Quản lý ngân sách, hóa đơn, thanh toán, báo cáo tài chính và quyết toán."
  },
  {
    "code": "human_resources",
    "name": "Nhân sự",
    "description": "Phân loại tài liệu liên quanTuyển dụng, đào tạo, chính sách nhân sự, lương thưởng và quản lý hồ sơ nhân viên."
  },
  {
    "code": "procurement",
    "name": "Mua sắm",
    "description": "Phân loại tài liệu liên quan Lập kế hoạch mua hàng, làm việc với nhà cung cấp và quản lý hợp đồng mua sắm."
  },
  {
    "code": "it",
    "name": "Công nghệ thông tin",
    "description": "Phân loại tài liệu liên quan Vận hành hệ thống CNTT, bảo mật, hạ tầng và hỗ trợ kỹ thuật nội bộ."
  },
  {
    "code": "tech-news",
    "name": "Tin tức vũ khí và công nghệ cao",
    "description": "Phân loại tài liệu liên quan thu thập thông tin vũ khí và công nghệ cao"
  },
  {
    "code": "domestic-news",
    "name": "Tin tức trong nước",
    "description": "Phân loại tài liệu liên quan thu thập thông tin trong nước"
  }
]"""


def parse_departments_json(raw: str) -> list[dict[str, str]]:
    data = json.loads(raw)
    if not isinstance(data, list):
        return []
    departments: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        name = str(item.get("name", "")).strip()
        description = str(item.get("description", "")).strip()
        if code and name:
            departments.append(
                {"code": code, "name": name, "description": description}
            )
    return departments


class SystemSettingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_key(self, key: str) -> Optional[SystemSetting]:
        result = await self.db.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        )
        return result.scalar_one_or_none()

    async def get_departments_list(self) -> list[dict[str, str]]:
        """Đọc key `departments` từ DB (JSON array); query mới mỗi lần gọi."""
        raw_json: str | None = None
        try:
            entity = await self.get_by_key(DEPARTMENTS_SETTING_KEY)
            if entity and entity.value and str(entity.value).strip():
                raw_json = str(entity.value).strip()
        except Exception as exc:
            logger.warning(
                "Failed to load departments from DB, using default | err=%s",
                exc,
            )

        if raw_json:
            try:
                departments = parse_departments_json(raw_json)
                if departments:
                    return departments
            except json.JSONDecodeError as exc:
                logger.warning(
                    "departments setting is not valid JSON, using default | err=%s",
                    exc,
                )

        try:
            return parse_departments_json(DEFAULT_DEPARTMENTS_JSON)
        except json.JSONDecodeError:
            return []

    async def upsert_by_key(
        self, key: str, value: str | None, created_by: int | None
    ) -> SystemSetting:
        entity = await self.get_by_key(key)

        if entity:
            entity.value = value
        else:
            entity = SystemSetting(
                key=key,
                value=value,
                created_by=created_by,
            )
            self.db.add(entity)

        await self.db.commit()
        await self.db.refresh(entity)
        return entity
