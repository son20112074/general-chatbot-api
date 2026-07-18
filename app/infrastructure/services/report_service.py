from datetime import date as date_type
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.domain.models.report import Report, ReportStatusEnum
from app.domain.models.report_document import ReportDocument
from app.domain.models.report_template import FileModeEnum, FrequencyEnum, ReportTemplate
from app.presentation.api.v1.schemas.report import (
    ReportTemplateCreate,
    ReportTemplateUpdate,
)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Report Templates ──────────────────────────────────────────────────────

    async def create_template(
        self, data: ReportTemplateCreate, created_by: int
    ) -> ReportTemplate:
        is_select = data.file_mode == "select"
        template = ReportTemplate(
            name=data.name,
            description=data.description,
            frequency=None if is_select else (FrequencyEnum(data.frequency) if data.frequency else None),
            creation_time=data.creation_time,
            start_date=None if is_select else data.start_date,
            end_date=None if is_select else data.end_date,
            is_indefinite=data.is_indefinite,
            file_mode=FileModeEnum(data.file_mode),
            file_ids=data.file_ids,
            created_by=created_by,
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def get_template(self, template_id: int) -> Optional[ReportTemplate]:
        result = await self.db.execute(
            select(ReportTemplate).where(ReportTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def list_templates(
        self,
        created_by: Optional[int] = None,
        q: Optional[str] = None,
        file_mode: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        base_filter = []
        if created_by is not None:
            base_filter.append(ReportTemplate.created_by == created_by)
        if q:
            base_filter.append(ReportTemplate.name.ilike(f"%{_escape_like(q)}%"))
        if file_mode:
            base_filter.append(ReportTemplate.file_mode == FileModeEnum(file_mode))

        total_result = await self.db.execute(
            select(func.count()).select_from(ReportTemplate).where(*base_filter)
        )
        total = total_result.scalar_one()

        result = await self.db.execute(
            select(ReportTemplate)
            .where(*base_filter)
            .order_by(ReportTemplate.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {"data": list(result.scalars().all()), "total": total, "page": page, "page_size": page_size}

    async def update_template(
        self, template_id: int, data: ReportTemplateUpdate
    ) -> Optional[ReportTemplate]:
        template = await self.get_template(template_id)
        if not template:
            return None

        update_data = data.model_dump(exclude_unset=True)
        if "frequency" in update_data and update_data["frequency"] is not None:
            update_data["frequency"] = FrequencyEnum(update_data["frequency"])
        if "file_mode" in update_data and update_data["file_mode"] is not None:
            update_data["file_mode"] = FileModeEnum(update_data["file_mode"])

        effective_mode = update_data.get("file_mode", template.file_mode)
        if effective_mode == FileModeEnum.SELECT:
            update_data["frequency"] = None
            update_data["start_date"] = None
            update_data["end_date"] = None

        for field, value in update_data.items():
            setattr(template, field, value)

        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def delete_template(self, template_id: int) -> bool:
        template = await self.get_template(template_id)
        if not template:
            return False
        await self.db.delete(template)
        await self.db.commit()
        return True

    async def add_file_to_template(self, template_id: int, file_id: int) -> ReportTemplate:
        template = await self.get_template(template_id)
        if not template:
            raise ValueError("Template not found")
        if template.file_mode != FileModeEnum.SELECT:
            raise ValueError("Only select-mode templates can hold specific files")
        ids = list(template.file_ids or [])
        if file_id not in ids:
            ids.append(file_id)
            template.file_ids = ids
            flag_modified(template, "file_ids")
            await self.db.commit()
            await self.db.refresh(template)
        return template

    async def remove_file_from_template(self, template_id: int, file_id: int) -> ReportTemplate:
        template = await self.get_template(template_id)
        if not template:
            raise ValueError("Template not found")
        if template.file_mode != FileModeEnum.SELECT:
            raise ValueError("Only select-mode templates can hold specific files")
        ids = list(template.file_ids or [])
        if file_id in ids:
            ids = [i for i in ids if i != file_id]
            template.file_ids = ids
            flag_modified(template, "file_ids")
            await self.db.commit()
            await self.db.refresh(template)
        return template

    # ── Reports ───────────────────────────────────────────────────────────────


    async def get_report(self, report_id: int) -> Optional[Report]:
        result = await self.db.execute(
            select(Report)
            .options(
                selectinload(Report.template),
                selectinload(Report.creator),
                selectinload(Report.documents),
            )
            .where(Report.id == report_id)
        )
        return result.scalar_one_or_none()

    async def list_reports(
        self,
        q: Optional[str] = None,
        status: Optional[str] = None,
        template_id: Optional[int] = None,
        created_by: Optional[int] = None,
        start_date: Optional[date_type] = None,
        end_date: Optional[date_type] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        base_filter = []

        if q:
            escaped = _escape_like(q)
            base_filter.append(Report.name.ilike(f"%{escaped}%"))
        if status:
            base_filter.append(Report.status == ReportStatusEnum(status))
        if template_id:
            base_filter.append(Report.template_id == template_id)
        if created_by is not None:
            base_filter.append(Report.created_by == created_by)
        if start_date or end_date:
            ca_conds = []
            if start_date:
                ca_conds.append(func.date(Report.created_at) >= start_date)
            if end_date:
                ca_conds.append(func.date(Report.created_at) <= end_date)
            base_filter.append(and_(*ca_conds))

        total_result = await self.db.execute(
            select(func.count()).select_from(Report).where(*base_filter)
        )
        total = total_result.scalar_one()

        result = await self.db.execute(
            select(Report)
            .options(
                selectinload(Report.template),
                selectinload(Report.creator),
                selectinload(Report.documents),
            )
            .where(*base_filter)
            .order_by(Report.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        reports = list(result.scalars().all())

        return {"data": reports, "total": total, "page": page, "page_size": page_size}

    async def delete_report(self, report_id: int) -> bool:
        result = await self.db.execute(
            select(Report).where(Report.id == report_id)
        )
        report = result.scalar_one_or_none()
        if not report:
            return False
        await self.db.delete(report)
        await self.db.commit()
        return True

    # ── Report Documents ──────────────────────────────────────────────────────

    async def add_documents(
        self, report_id: int, documents: List[Dict[str, Any]], user_id: Optional[int] = None
    ) -> List[ReportDocument]:
        """Bulk-add source documents to a report. Each dict: {document_id, document_name}."""
        rows = [
            ReportDocument(
                report_id=report_id,
                document_id=doc.get("document_id"),
                document_name=doc.get("document_name"),
                user_id=user_id,
            )
            for doc in documents
        ]
        self.db.add_all(rows)
        await self.db.commit()
        for row in rows:
            await self.db.refresh(row)
        return rows

    async def remove_documents(self, report_id: int) -> None:
        await self.db.execute(
            delete(ReportDocument).where(ReportDocument.report_id == report_id)
        )
        await self.db.commit()
