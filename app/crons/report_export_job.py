import calendar
import os
import shutil
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import csv
import json as _json

import docx as _docx
import openpyxl
import requests
from docx import Document as DocxDocument
from docx.shared import Pt
from parser.pdf_parser import PDFParser
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.logger import get_logger
from app.domain.models.file import File as FileModel
from app.domain.models.report import Report, ReportStatusEnum
from app.domain.models.report_document import ReportDocument, ReportDocumentStatus
from app.domain.models.report_template import FileModeEnum, FrequencyEnum, ReportTemplate
from app.domain.models.user import User
from app.infrastructure.services.template_extraction_multi_files_service import (
    TemplateExtractionMultiFilesService,
)

logger = get_logger()

ADMIN_ROLE_ID = settings.ADMIN_ROLE_ID
REPORTS_OUTPUT_DIR = Path("static/downloads/reports")
REPORTS_STORAGE_PREFIX = "downloads/reports"

# ── Schedule helpers ──────────────────────────────────────────────────────────

_QUARTER_END_MONTHS = {3, 6, 9, 12}
_QUARTER_START_MONTHS = {1, 4, 7, 10}

# Minimum span (days) for a frequency cycle to be considered "large enough"
_MIN_WINDOW_DAYS = {
    FrequencyEnum.DAILY: 1,
    FrequencyEnum.WEEKLY: 7,
    FrequencyEnum.MONTHLY: 28,
    FrequencyEnum.QUARTERLY: 90,
}


def _quarter_start(d: date) -> date:
    return d.replace(month=((d.month - 1) // 3) * 3 + 1, day=1)


def _is_last_day_of_month(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def _is_last_day_of_quarter(d: date) -> bool:
    return d.month in _QUARTER_END_MONTHS and _is_last_day_of_month(d)


def _is_template_active(template: ReportTemplate, today: date) -> bool:
    if template.start_date and today < template.start_date:
        return False
    if not template.is_indefinite and template.end_date and today > template.end_date:
        return False
    return True


def _should_run_today(template: ReportTemplate, today: date, now_time: time) -> bool:
    """Return True if this template should be processed in the current run.

    creation_time acts as a gate: skip until the configured time has passed.
    If the job missed the target day (e.g. server was down), it catches up on
    the following day.
    """
    tid = template.id
    tname = template.name
    ct = template.creation_time
    if ct and now_time < ct:
        msg = f"[ReportExport] Template {tid} ({tname}) skipped: creation_time {ct} not yet reached (now={now_time})"
        logger.info(msg)
        print(msg)
        return False

    freq = template.frequency
    yesterday = today - timedelta(days=1)

    if freq == FrequencyEnum.DAILY:
        return True

    if freq == FrequencyEnum.WEEKLY:
        result = today.weekday() in {6, 0}  # Sunday (target) or Monday (catch-up)
        if not result:
            msg = f"[ReportExport] Template {tid} ({tname}) skipped: weekly — today weekday={today.weekday()} not in valid window"
            logger.info(msg)
            print(msg)
        return result

    if freq == FrequencyEnum.MONTHLY:
        result = _is_last_day_of_month(today) or _is_last_day_of_month(yesterday)
        if not result:
            msg = f"[ReportExport] Template {tid} ({tname}) skipped: monthly — today={today} not in valid window"
            logger.info(msg)
            print(msg)
        return result

    if freq == FrequencyEnum.QUARTERLY:
        result = _is_last_day_of_quarter(today) or _is_last_day_of_quarter(yesterday)
        if not result:
            msg = f"[ReportExport] Template {tid} ({tname}) skipped: quarterly — today={today} not in valid window"
            logger.info(msg)
            print(msg)
        return result

    return False


def _compute_period(frequency: FrequencyEnum, today: date) -> Tuple[date, date]:
    """Return (period_start, period_end) anchored to the logical target day.

    When running on a catch-up day (day after the target), yesterday becomes
    the anchor so the period still covers the correct cycle.
    """
    yesterday = today - timedelta(days=1)

    if frequency == FrequencyEnum.DAILY:
        return today, today

    if frequency == FrequencyEnum.WEEKLY:
        ref = today if today.weekday() == 6 else yesterday
        return ref - timedelta(days=6), ref

    if frequency == FrequencyEnum.MONTHLY:
        ref = today if _is_last_day_of_month(today) else yesterday
        return ref.replace(day=1), ref

    if frequency == FrequencyEnum.QUARTERLY:
        ref = today if _is_last_day_of_quarter(today) else yesterday
        return _quarter_start(ref), ref

    return today, today


# ── File content extractors (mirrors files.py) ───────────────────────────────

def _extract_docx_content(file_path: str) -> str:
    doc = _docx.Document(file_path)
    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _extract_doc_content(file_path: str) -> str:
    try:
        import docx2txt
        return docx2txt.process(file_path) or ""
    except ImportError:
        return ""


def _extract_xlsx_content(file_path: str) -> str:
    wb = openpyxl.load_workbook(file_path, data_only=True)
    parts = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        parts.append(f"=== Sheet: {sheet_name} ===")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(c.strip() for c in cells if c):
                parts.append(" | ".join(cells))
    wb.close()
    return "\n".join(parts)


def _extract_text_content(file_path: str) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "ascii"):
        try:
            with open(file_path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(file_path, "rb") as fh:
        return fh.read().decode("utf-8", errors="ignore")


def _extract_csv_content(file_path: str) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            with open(file_path, "r", encoding=enc, newline="") as fh:
                sample = fh.read(1024)
                fh.seek(0)
                delim = "\t" if "\t" in sample else (";" if ";" in sample else ",")
                rows = []
                for i, row in enumerate(csv.reader(fh, delimiter=delim), 1):
                    if row and any(c.strip() for c in row):
                        rows.append(f"Row {i}: {' | '.join(row)}")
                return "\n".join(rows)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def _extract_pdf_content(file_path: str) -> str:
    parser = PDFParser()
    result = parser.parse_pdf(file_path)
    if not result.get("success"):
        raise Exception(result.get("error", "Không thể trích xuất nội dung từ file PDF"))
    return result.get("content", "")


_EXTRACTORS = {
    ".docx": _extract_docx_content,
    ".doc":  _extract_doc_content,
    ".xlsx": _extract_xlsx_content,
    ".txt":  _extract_text_content,
    ".dat":  _extract_text_content,
    ".csv":  _extract_csv_content,
    ".pdf":  _extract_pdf_content,
}


def _extract_content_from_file(tmp_path: str, ext: str) -> str:
    extractor = _EXTRACTORS.get(ext.lower())
    if extractor:
        return extractor(tmp_path)
    return _extract_text_content(tmp_path)


# ── File visibility ───────────────────────────────────────────────────────────

async def _get_visible_files(
    session: AsyncSession,
    user_id: int,
    user_role_id: int,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> List[FileModel]:
    if user_role_id == ADMIN_ROLE_ID:
        visibility_filter = []
    else:
        child_rows = await session.execute(
            sa_text("""
                SELECT id FROM roles
                WHERE (parent_path ILIKE :exact OR parent_path ILIKE :anywhere)
                  AND is_deleted = false
            """),
            {"exact": f",{user_role_id},", "anywhere": f"%,{user_role_id},%"},
        )
        child_role_ids = [r[0] for r in child_rows.fetchall()]

        visibility_filter = [
            or_(
                FileModel.type == "general",
                and_(FileModel.type == "private", FileModel.created_by == user_id),
                and_(
                    FileModel.type == "organization",
                    FileModel.role_id == user_role_id,
                    FileModel.created_by == user_id,
                ),
                *(
                    [and_(FileModel.type == "organization", FileModel.role_id.in_(child_role_ids))]
                    if child_role_ids else []
                ),
            )
        ]

    period_filter = []
    if period_start or period_end:
        ps = period_start or date.min
        pe = period_end or date.max

        created_at_cond = and_(
            *([FileModel.created_at >= datetime.combine(ps, time.min)] if period_start else []),
            *([FileModel.created_at < datetime.combine(pe + timedelta(days=1), time.min)] if period_end else []),
        )

        # Also match files whose listed_timeline contains any ISO date within the period.
        # LEFT(tl, 10) isolates the date portion in case the string has extra characters.
        timeline_overlap = sa_text(
            "EXISTS ("
            "  SELECT 1 FROM unnest(files.listed_timeline) AS tl"
            "  WHERE tl ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'"
            "    AND LEFT(tl, 10)::date >= :tl_start"
            "    AND LEFT(tl, 10)::date <= :tl_end"
            ")"
        ).bindparams(tl_start=ps, tl_end=pe)

        period_filter = [or_(created_at_cond, timeline_overlap)]

    base_cond = and_(
        or_(FileModel.is_deleted == False, FileModel.is_deleted == None),
        FileModel.content.isnot(None),
        FileModel.content != "",
        *visibility_filter,
        *period_filter,
    )

    result = await session.execute(
        select(FileModel).where(base_cond).order_by(FileModel.created_at.desc())
    )
    seen_names: set = set()
    unique_files: List[FileModel] = []
    for f in result.scalars().all():
        if f.name not in seen_names:
            seen_names.add(f.name)
            unique_files.append(f)
    return unique_files


async def _get_files_for_template(
    session: AsyncSession,
    template: ReportTemplate,
    user_id: int,
    user_role_id: int,
    period_start: Optional[date],
    period_end: Optional[date],
) -> List[FileModel]:
    if template.file_mode == FileModeEnum.SELECT and template.file_ids:
        result = await session.execute(
            select(FileModel).where(
                FileModel.id.in_(template.file_ids),
                or_(FileModel.is_deleted == False, FileModel.is_deleted == None),
                FileModel.content.isnot(None),
                FileModel.content != "",
            ).order_by(FileModel.created_at.desc())
        )
        return list(result.scalars().all())
    return await _get_visible_files(session, user_id, user_role_id, period_start, period_end)


# ── Docx generation ───────────────────────────────────────────────────────────

def _write_json_section(doc: DocxDocument, data: Any, depth: int = 1) -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            doc.add_heading(key, level=min(depth, 4))
            _write_json_section(doc, value, depth + 1)
    elif isinstance(data, str) and data.strip():
        para = doc.add_paragraph(data.strip())
        para.style.font.size = Pt(11)


def _build_docx(template_name: str, final_json: Dict[str, Any]) -> bytes:
    doc = DocxDocument()
    doc.add_heading(template_name, level=0)
    doc.add_paragraph(f"Ngày tạo: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    doc.add_paragraph("")
    _write_json_section(doc, final_json, depth=1)

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        doc.save(tmp_path)
        with open(tmp_path, "rb") as f:
            data = f.read()
    finally:
        os.unlink(tmp_path)

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in template_name)
    local_path = Path(f"report_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx")
    local_path.write_bytes(data)
    print(f"[ReportExport] Docx saved locally → {local_path.resolve()}")

    return data


def _save_docx(template_name: str, report_id: int, content: bytes) -> str:
    REPORTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in template_name)
    filename = f"report_{report_id}_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    out_path = REPORTS_OUTPUT_DIR / filename
    out_path.write_bytes(content)
    return f"static/{REPORTS_STORAGE_PREFIX}/{filename}"


# ── Status helpers ────────────────────────────────────────────────────────────

async def _set_docs_status(
    session: AsyncSession,
    report_id: int,
    doc_status: ReportDocumentStatus,
    doc_ids: Optional[List[int]] = None,
) -> None:
    stmt = update(ReportDocument).where(ReportDocument.report_id == report_id)
    if doc_ids is not None:
        stmt = stmt.where(ReportDocument.id.in_(doc_ids))
    await session.execute(stmt.values(status=doc_status))
    await session.commit()


# ── Per-template extraction ───────────────────────────────────────────────────

async def _process_template(
    session: AsyncSession,
    template: ReportTemplate,
    files: List[FileModel],
    period_start: date,
    period_end: date,
) -> None:
    template_id = template.id
    template_name = template.name

    extraction_prompt = f"""
## TASK
Extract information from INPUT TEXT into structured Markdown following the template outline.

## TEMPLATE OUTLINE
{template.description or template_name}

## INSTRUCTIONS
- Map content to the most relevant section based on meaning
- Keep each section concise
- Do not hallucinate
- Vietnamese only
""".strip()

    report = Report(
        name=f"{template_name} - {datetime.now().strftime('%d/%m/%Y')}",
        template_id=template_id,
        status=ReportStatusEnum.COMPILING,
        period_start=period_start,
        period_end=period_end,
        created_by=template.created_by,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)

    doc_rows = [
        ReportDocument(
            report_id=report.id,
            document_id=f.id,
            document_name=f.name,
            user_id=template.created_by,
            status=ReportDocumentStatus.QUEUING,
        )
        for f in files
    ]
    session.add_all(doc_rows)
    await session.commit()
    for row in doc_rows:
        await session.refresh(row)

    doc_id_by_file_id = {row.document_id: row.id for row in doc_rows}
    msg = f"[ReportExport] Template {template_id} ({template_name}) → report_id={report.id}, {len(doc_rows)} doc(s) | period {period_start} → {period_end}"
    logger.info(msg)
    print(msg)

    await _set_docs_status(session, report.id, ReportDocumentStatus.PROCESSING)

    tmp_dir = tempfile.mkdtemp(prefix="report_export_")
    file_path_map: Dict[str, int] = {}

    try:
        for f in files:
            ext = Path(f.name).suffix or ".txt"
            dl_path = os.path.join(tmp_dir, f"{f.id}_{Path(f.name).stem}{ext}")
            txt_path = os.path.join(tmp_dir, f"{f.id}_{Path(f.name).stem}.txt")
            file_url = (
                f"{settings.STORAGE_PUBLIC_URL.rstrip('/')}/{settings.STORAGE_BUCKET_NAME}/{f.path.lstrip('/')}"
                if f.path else None
            )
            msg = f"[ReportExport] Fetching file id={f.id} name={f.name} url={file_url}"
            logger.info(msg)
            print(msg)

            text_content = ""
            if file_url:
                try:
                    with requests.get(file_url, stream=True, timeout=60) as resp:
                        resp.raise_for_status()
                        with open(dl_path, "wb") as fh:
                            for chunk in resp.iter_content(chunk_size=8192):
                                if chunk:
                                    fh.write(chunk)
                    msg = f"[ReportExport] Downloaded {os.path.getsize(dl_path)} bytes → extracting ({ext})"
                    logger.info(msg)
                    print(msg)
                    text_content = _extract_content_from_file(dl_path, ext)
                    msg = f"[ReportExport] Extracted {len(text_content)} chars from {f.name}"
                    logger.info(msg)
                    print(msg)
                except Exception as fetch_exc:
                    msg = f"[ReportExport] Fetch/extract failed for {file_url}: {fetch_exc} — falling back to content column"
                    logger.warning(msg)
                    print(msg)
                    text_content = f.content or ""
            else:
                msg = f"[ReportExport] No URL for file id={f.id}, using content column"
                logger.warning(msg)
                print(msg)
                text_content = f.content or ""

            Path(txt_path).write_text(text_content, encoding="utf-8")
            file_path_map[txt_path] = f.id

        service = TemplateExtractionMultiFilesService()
        result = await service.extract_documents(
            file_paths=list(file_path_map.keys()),
            extraction_prompt=extraction_prompt,
            report_template=template.description or "",
        )
        msg = f"[ReportExport] Extraction result — processed={result.processed_files} failed={result.failed_files} warnings={result.warnings}"
        logger.info(msg)
        print(msg)
        summary_dump = _json.dumps(result.final_json, ensure_ascii=False, indent=2)
        msg = f"[ReportExport] final_json:\n{summary_dump}"
        logger.info(msg)
        print(msg)
    except Exception as exc:
        msg = f"[ReportExport] Extraction failed for template {template_id} ({template_name}): {exc}"
        logger.exception(msg)
        print(msg)
        await _set_docs_status(session, report.id, ReportDocumentStatus.ERROR)
        await session.execute(
            update(Report).where(Report.id == report.id).values(status=ReportStatusEnum.FAILED)
        )
        await session.commit()
        return
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    failed_paths: Set[str] = {w.split(":")[0].strip() for w in result.warnings}
    failed_file_ids: Set[int] = {
        fid for path, fid in file_path_map.items() if path in failed_paths
    }

    for f in files:
        doc_id = doc_id_by_file_id.get(f.id)
        if doc_id is None:
            continue
        new_status = (
            ReportDocumentStatus.ERROR if f.id in failed_file_ids
            else ReportDocumentStatus.COMPLETED
        )
        await session.execute(
            update(ReportDocument).where(ReportDocument.id == doc_id).values(status=new_status)
        )
    await session.commit()

    try:
        docx_bytes = _build_docx(template_name, result.final_json)
        output_path = _save_docx(template_name, report.id, docx_bytes)
    except Exception as exc:
        msg = f"[ReportExport] Docx generation failed for report {report.id}: {exc}"
        logger.exception(msg)
        print(msg)
        await session.execute(
            update(Report).where(Report.id == report.id).values(status=ReportStatusEnum.FAILED)
        )
        await session.commit()
        return

    overall_status = (
        ReportStatusEnum.FAILED if result.processed_files == 0
        else ReportStatusEnum.COMPLETED
    )
    await session.execute(
        update(Report)
        .where(Report.id == report.id)
        .values(status=overall_status, file_url=output_path)
    )
    await session.commit()

    msg = f"[ReportExport] Template {template_id} ({template_name}) → report {report.id} {overall_status.value} | files: {result.processed_files} ok / {result.failed_files} failed | docx: {output_path}"
    logger.info(msg)
    print(msg)


# ── Per-frequency cycle ───────────────────────────────────────────────────────

async def _run_for_frequency(frequency: FrequencyEnum) -> None:
    today = date.today()
    now_time = datetime.now().time()

    async with get_db_session() as session:
        result = await session.execute(
            select(ReportTemplate)
            .where(ReportTemplate.frequency == frequency)
            .order_by(ReportTemplate.id)
        )
        templates = list(result.scalars().all())

        if not templates:
            msg = f"[ReportExport][{frequency.value}] No templates found"
            logger.info(msg)
            print(msg)
            return

        for template in templates:
            if not _is_template_active(template, today):
                msg = f"[ReportExport][{frequency.value}] Template {template.id} ({template.name}) inactive today, skipping"
                logger.info(msg)
                print(msg)
                continue

            if template.is_indefinite:
                if not _should_run_today(template, today, now_time):
                    continue
                period_start, period_end = _compute_period(frequency, today)
            else:
                period_start = template.start_date or today
                period_end = template.end_date or today
                span = (period_end - period_start).days
                # Always enforce creation_time gate.
                # Only enforce the frequency day-of-week/month gate when the
                # window is large enough to form a full cycle.
                ct = template.creation_time
                if ct and now_time < ct:
                    msg = f"[ReportExport][{frequency.value}] Template {template.id} ({template.name}) skipped: creation_time {ct} not yet reached (now={now_time})"
                    logger.info(msg)
                    print(msg)
                    continue
                if span >= _MIN_WINDOW_DAYS.get(frequency, 1):
                    # creation_time already checked above; pass time.max so
                    # _should_run_today's internal time gate always passes.
                    if not _should_run_today(template, today, time.max):
                        continue

            # Idempotency: skip if a report for this period already exists
            existing_count = await session.scalar(
                select(func.count()).select_from(Report)
                .where(Report.template_id == template.id)
                .where(Report.period_start == period_start)
                .where(Report.period_end == period_end)
            )
            if existing_count:
                msg = f"[ReportExport][{frequency.value}] Template {template.id} ({template.name}) report for {period_start}→{period_end} already exists, skipping"
                logger.info(msg)
                print(msg)
                continue

            if not template.created_by:
                msg = f"[ReportExport][{frequency.value}] Template {template.id} ({template.name}) has no creator, skipping"
                logger.warning(msg)
                print(msg)
                continue

            user_result = await session.execute(
                select(User.id, User.role_id).where(
                    User.id == template.created_by,
                    User.status == True,
                )
            )
            user_row = user_result.first()
            if not user_row:
                msg = f"[ReportExport][{frequency.value}] Creator (id={template.created_by}) for template {template.id} not found or inactive, skipping"
                logger.warning(msg)
                print(msg)
                continue

            files = await _get_files_for_template(
                session, template, user_row.id, user_row.role_id, period_start, period_end
            )
            if not files:
                msg = f"[ReportExport][{frequency.value}] Template {template.id} ({template.name}) — no files in {period_start}→{period_end}, skipping"
                logger.info(msg)
                print(msg)
                continue

            msg = f"[ReportExport][{frequency.value}] Template {template.id} ({template.name}) | user_id={user_row.id} | {len(files)} file(s) | {period_start}→{period_end}"
            logger.info(msg)
            print(msg)
            await _process_template(session, template, files, period_start, period_end)


# ── Test job ─────────────────────────────────────────────────────────────────

async def test_report_export_weekly() -> None:
    """One-shot test: run weekly extraction for user_id=1 with files from the last 3 months."""
    TEST_USER_ID = 1
    today = date.today()
    period_start = today - timedelta(days=90)
    period_end = today

    msg = f"[TestReportExport] Starting | user_id={TEST_USER_ID} | period {period_start} → {period_end}"
    logger.info(msg)
    print(msg)

    try:
        async with get_db_session() as session:
            user_result = await session.execute(
                select(User.id, User.role_id).where(User.id == TEST_USER_ID)
            )
            user_row = user_result.first()
            if not user_row:
                msg = f"[TestReportExport] User {TEST_USER_ID} not found, aborting"
                logger.warning(msg)
                print(msg)
                return

            template_result = await session.execute(
                select(ReportTemplate).order_by(ReportTemplate.id).limit(1)
            )
            template = template_result.scalar_one_or_none()
            if not template:
                msg = "[TestReportExport] No template found, aborting"
                logger.warning(msg)
                print(msg)
                return

            msg = f"[TestReportExport] Using template id={template.id} ({template.name})"
            logger.info(msg)
            print(msg)

            files = (await _get_visible_files(session, user_row.id, user_row.role_id, period_start, period_end))[:2]

            if not files:
                msg = f"[TestReportExport] No files found in {period_start} → {period_end}, aborting"
                logger.warning(msg)
                print(msg)
                return

            msg = f"[TestReportExport] Using {len(files)} file(s) (latest 3) — starting extraction"
            logger.info(msg)
            print(msg)

            await _process_template(session, template, files, period_start, period_end)

        msg = "[TestReportExport] Finished"
        logger.info(msg)
        print(msg)
    except Exception as exc:
        msg = f"[TestReportExport] Failed: {exc}"
        logger.exception(msg)
        print(msg)


# ── Exported jobs ─────────────────────────────────────────────────────────────

async def report_export_daily_job() -> None:
    try:
        msg = "[ReportExport] Daily job started"
        logger.info(msg)
        print(msg)
        await _run_for_frequency(FrequencyEnum.DAILY)
        msg = "[ReportExport] Daily job finished"
        logger.info(msg)
        print(msg)
    except Exception:
        msg = "[ReportExport] Daily job failed"
        logger.exception(msg)
        print(msg)


async def report_export_weekly_job() -> None:
    try:
        msg = "[ReportExport] Weekly job started"
        logger.info(msg)
        print(msg)
        await _run_for_frequency(FrequencyEnum.WEEKLY)
        msg = "[ReportExport] Weekly job finished"
        logger.info(msg)
        print(msg)
    except Exception:
        msg = "[ReportExport] Weekly job failed"
        logger.exception(msg)
        print(msg)


async def report_export_monthly_job() -> None:
    try:
        msg = "[ReportExport] Monthly job started"
        logger.info(msg)
        print(msg)
        await _run_for_frequency(FrequencyEnum.MONTHLY)
        msg = "[ReportExport] Monthly job finished"
        logger.info(msg)
        print(msg)
    except Exception:
        msg = "[ReportExport] Monthly job failed"
        logger.exception(msg)
        print(msg)


async def report_export_quarterly_job() -> None:
    try:
        msg = "[ReportExport] Quarterly job started"
        logger.info(msg)
        print(msg)
        await _run_for_frequency(FrequencyEnum.QUARTERLY)
        msg = "[ReportExport] Quarterly job finished"
        logger.info(msg)
        print(msg)
    except Exception:
        msg = "[ReportExport] Quarterly job failed"
        logger.exception(msg)
        print(msg)


async def report_export_all_job() -> None:
    try:
        msg = "[ReportExport] Daily run started"
        logger.info(msg)
        print(msg)
        for freq in FrequencyEnum:
            await _run_for_frequency(freq)
        msg = "[ReportExport] Daily run finished"
        logger.info(msg)
        print(msg)
    except Exception:
        msg = "[ReportExport] Daily run failed"
        logger.exception(msg)
        print(msg)
