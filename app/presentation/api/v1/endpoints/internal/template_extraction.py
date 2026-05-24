import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.infrastructure.services.template_extraction_service import TemplateExtractionService
from app.infrastructure.services.template_extraction_multi_files_service import TemplateExtractionMultiFilesService, MultiFileExtractionReport
from app.presentation.api.dependencies import get_current_user
from app.presentation.api.v1.schemas.auth import TokenData

router = APIRouter()
logger = logging.getLogger(__name__)

class TemplateExtractionResponse(BaseModel):
    result: MultiFileExtractionReport
    
# @router.post("/test-multi", response_model=TemplateExtractionResponse)
# async def extract_template():
#         extraction_multi_service = TemplateExtractionMultiFilesService()
#         report_template = """
#     - Thông tin chiến tranh hoặc xung đột quân sự
#     - Ảnh hưởng gì tới Việt Nam
#     - AI ảnh hưởng đến y tế
#     """

#         EXTRACTION_PROMPT = f"""
#     ## TASK
#     Extract information from INPUT TEXT into structured Markdown.

#     ## TEMPLATE
#     {report_template}

#     ## INSTRUCTION
#     - Convert each line into a section
#     - Keep short
#     - Do not hallucinate
#     """
#         report = await extraction_multi_service.extract_documents(
#             ["iran-war.pdf", "news.txt"],
#             EXTRACTION_PROMPT,
#             report_template,
#              "template.txt",
#         )
#         return {"result": report}
