"""
File Processing Job

This job processes files from the database that have is_processed = null,
extracts content using the parser, and updates the database with the results.
"""

import asyncio
import logging
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import time
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
from app.core.database import get_db

from app.domain.models.file import File

from parser.file_parser import FileParser
from parser.config import get_base_url
from parser.summary_service import SummaryService
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FileProcessingJob:
    """Job for processing files from database.
    
    This job:
    1. Finds unprocessed files (is_processed = null)
    2. Parses files using FileParser (which may already generate AI summaries for some file types)
    3. Extracts content and generates AI summaries using SummaryService when needed
    4. Updates the database with extracted content and AI summaries
    """
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.parser = FileParser()
        self.summary_service = SummaryService(api_url=settings.LLM_API)
        self.processed_count = 0
        self.failed_count = 0
        self.errors = []
    
    async def get_unprocessed_files(self) -> List[File]:
        """Get files that have not been processed yet (is_processed is null)."""
        try:
            result = await self.db.execute(
                select(File).where(File.is_processed.is_(None))
            )
            files = result.scalars().all()
            if len(files) > 0:
                logger.info(f"Found {len(files)} unprocessed files")
            return files
        except Exception as e:
            logger.error(f"Error getting unprocessed files: {e}")
            return []
    
    async def process_single_file(self, file: File) -> Dict[str, Any]:
        """Process a single file and update database."""
        start_time = time.time()  # Record start time for processing duration
        try:
            logger.info(f"Processing file: {file.name} (ID: {file.id})")
            
            # Check if file exists on disk
            if not os.path.exists(file.path):
                raise FileNotFoundError(f"File not found on disk: {file.path}")
            
            # Parse file using the parser
            logger.info(f"Parsing file with extension: {file.extension}")
            result = self.parser.parse_file(file.path, file.extension)
            
            # Check if parsing was successful
            if not result.get('success', True):  # Default to True for backward compatibility
                error_msg = result.get('error', 'Unknown parsing error')
                logger.error(f"❌ Parser failed for {file.name}: {error_msg}")
                # Check if it's an unsupported file type
                if 'Unsupported file type' in error_msg:
                    raise Exception(error_msg)  # Keep original error message for unsupported files
                else:
                    raise Exception(f"Parsing failed: {error_msg}")
            
            # Extract content and summary from result
            content = self._extract_content(result, file.extension)
            # Extract summary - will use AI summary if available, otherwise generate new one
            # Note: summary extraction already uses _extract_content which cleans the content
            summary = self._extract_summary(result, file.extension)
            
            # Extract metadata (countries, technologies, companies, important news)
            metadata = self._extract_metadata(summary, file.extension)

            # Log summary generation result
            if summary:
                logger.info(f"📝 AI Summary generated for {file.name}: {len(summary)} characters")
            else:
                logger.info(f"ℹ️ No AI summary available for {file.name} - will be stored as NULL")
            
            # Log metadata extraction result
            if metadata:
                logger.info(f"🏷️ Metadata extracted for {file.name}: {len(metadata.get('listed_nation', []))} countries, {len(metadata.get('listed_technology', []))} technologies, {len(metadata.get('listed_company', []))} companies, {len(metadata.get('important_news', []))} news items")
            else:
                logger.info(f"ℹ️ No metadata available for {file.name} - will be stored as empty arrays")
            
            # Calculate processing duration
            processing_duration = int(time.time() - start_time)
            logger.info(f"⏱️ Processing completed in {processing_duration} seconds for {file.name}")
            
            # Update file in database
            await self._update_file_processing(file.id, content, summary, metadata, True, processing_duration)
            
            self.processed_count += 1
            logger.info(f"✅ Successfully processed file: {file.name}")
            
            return {
                "success": True,
                "file_id": file.id,
                "file_name": file.name,
                "content_length": len(content) if content else 0,
                "summary_length": len(summary) if summary else None,
                "processing_duration": processing_duration
            }
            
        except Exception as e:
            # Calculate processing duration even for failed files
            processing_duration = int(time.time() - start_time)
            logger.error(f"⏱️ Processing failed after {processing_duration} seconds for {file.name}")
            
            self.failed_count += 1
            error_msg = f"Error processing file {file.name}: {str(e)}"
            self.errors.append(error_msg)
            logger.error(error_msg)
            
            # Mark file as processing failed
            await self._update_file_processing(file.id, None, None, None, False, processing_duration)
            
            return {
                "success": False,
                "file_id": file.id,
                "file_name": file.name,
                "error": str(e),
                "processing_duration": processing_duration
            }
    
    def _clean_content(self, content: str) -> str:
        """Clean content by decoding UTF-8 and removing null bytes."""
        if not content:
            return ""
        
        # If content is bytes, decode it to UTF-8
        if isinstance(content, bytes):
            try:
                content = content.decode('utf-8', errors='replace')
            except Exception:
                logger.warning("Failed to decode binary content to UTF-8")
                return ""
        
        # Remove null bytes (0x00) which PostgreSQL doesn't allow in UTF-8 strings
        return content.replace('\x00', '')
    
    def _extract_content(self, result: Dict[str, Any], extension: str) -> str:
        """Extract content from parser result based on file type."""
        if not result:
            return ""
        
        # Check if parsing was successful
        if not result.get('success', True):  # Default to True for backward compatibility
            logger.warning(f"Parser failed for {extension}: {result.get('error', 'Unknown error')}")
            return ""
        
        # Special handling for Excel files parsed with langchain
        if extension.lower() in ['.xlsx', '.xls', '.xlsm', '.xlsb'] and result.get('parsed_with') == 'langchain_community':
            content = self._extract_excel_content(result)
            return self._clean_content(content)
        
        # Try different content fields based on file type
        content_fields = ['content', 'text_content', 'data', 'text', 'description']
        
        for field in content_fields:
            if field in result and result[field]:
                content = result[field]
                if isinstance(content, str):
                    return self._clean_content(content)
                elif isinstance(content, list):
                    combined = '\n'.join(str(item) for item in content)
                    return self._clean_content(combined)
                elif isinstance(content, dict):
                    return self._clean_content(str(content))
        
        # If no specific content field, return the whole result as string
        return self._clean_content(str(result))
    
    def _extract_summary(self, result: Dict[str, Any], extension: str) -> Optional[str]:
        """Extract AI summary only from parser result or generate new AI summary."""
        if not result:
            return None
        
        # Priority: Use AI summary if already available in result
        if result.get('ai_summary'):
            logger.info(f"✅ Using pre-existing AI summary for {extension}")
            return self._clean_content(result['ai_summary'])
        
        # Generate AI summary from content using SummaryService
        content = self._extract_content(result, extension)
        if content and len(content.strip()) > 0:
            try:
                logger.info(f"Generating AI summary for {extension} file")
                summary_result = self.summary_service.summarize_content(content, extension)
                
                if summary_result["success"]:
                    logger.info(f"✅ AI summary generated successfully for {extension}")
                    return self._clean_content(summary_result["summary"])
                else:
                    logger.warning(f"❌ Failed to generate AI summary for {extension}: {summary_result['error']}")
                    # Return None if AI summary fails
                    return None
                    
            except Exception as e:
                logger.error(f"Error generating AI summary for {extension}: {str(e)}")
                # Return None if AI summary fails
                return None
        
        logger.info(f"No content available for AI summary generation for {extension}")
        return None
    
    def _extract_metadata(self, content: str, extension: str) -> Optional[Dict[str, Any]]:
        """Extract metadata (countries, technologies, companies, important news) from content."""
        if not content or len(content.strip()) == 0:
            return None
        
        try:
            logger.info(f"Extracting metadata for {extension} file")
            metadata_result = self.summary_service.extract_metadata(content, extension)
            
            if metadata_result["success"]:
                logger.info(f"✅ Metadata extracted successfully for {extension}")
                return metadata_result["metadata"]
            else:
                logger.warning(f"❌ Failed to extract metadata for {extension}: {metadata_result['error']}")
                # Return None if metadata extraction fails
                return None
                
        except Exception as e:
            logger.error(f"Error extracting metadata for {extension}: {str(e)}")
            # Return None if metadata extraction fails
            return None

    
    def _extract_excel_content(self, result: Dict[str, Any]) -> str:
        """Extract content specifically from Excel parsing results."""
        if not result or not result.get('success'):
            return result.get('error', 'Failed to parse Excel file')
        
        # If we have combined content, use it
        if result.get('content'):
            return result['content']
        
        # If we have individual elements, combine them
        if result.get('elements'):
            elements_content = []
            for element in result['elements']:
                if element.get('content'):
                    # Add metadata info if available
                    metadata_info = ""
                    if element.get('metadata'):
                        metadata = element['metadata']
                        if metadata.get('sheet_name'):
                            metadata_info = f"[Sheet: {metadata['sheet_name']}] "
                        elif metadata.get('page_number'):
                            metadata_info = f"[Page: {metadata['page_number']}] "
                    
                    elements_content.append(f"{metadata_info}{element['content']}")
            
            return '\n\n'.join(elements_content)
        
        return "No content extracted from Excel file"
    
    async def _update_file_processing(self, file_id: int, content: str, summary: Optional[str], metadata: Optional[Dict[str, Any]], is_processed: bool, processing_duration: Optional[int] = None):
        """Update file processing information in database."""
        try:
            # Clean content and summary to remove null bytes
            cleaned_content = self._clean_content(content) if content else None
            cleaned_summary = self._clean_content(summary) if summary else None
            
            # Prepare update values
            update_values = {
                "content": cleaned_content,
                "summary": cleaned_summary,  # This will be the AI summary or None
                "is_processed": is_processed,
                "updated_at": datetime.utcnow()
            }
            
            # Add processing duration if provided
            if processing_duration is not None:
                update_values["processing_duration"] = processing_duration
            
            # Add metadata fields - always set to empty arrays if no metadata
            update_values.update({
                "listed_nation": metadata.get("listed_nation", []) if metadata else [],
                "listed_technology": metadata.get("listed_technology", []) if metadata else [],
                "listed_company": metadata.get("listed_company", []) if metadata else [],
                "important_news": metadata.get("important_news", []) if metadata else []
            })
            
            # Update file record
            await self.db.execute(
                update(File)
                .where(File.id == file_id)
                .values(**update_values)
            )
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating file {file_id}: {e}")
            try:
                await self.db.rollback()
            except Exception as rollback_error:
                logger.error(f"Error during rollback for file {file_id}: {rollback_error}")
            raise
    
    async def process_all_files(self) -> Dict[str, Any]:
        """Process all unprocessed files."""
        # logger.info("="*50)
        # logger.info("🚀 Starting file processing job...")
        
        # Get unprocessed files
        files = await self.get_unprocessed_files()
        
        if not files:
            # logger.info("No unprocessed files found")
            return {
                "total_files": 0,
                "processed": 0,
                "failed": 0,
                "errors": []
            }
        
        # Process each file
        results = []
        for file in files:
            result = await self.process_single_file(file)
            results.append(result)
        
        # Generate summary
        summary = {
            "total_files": len(files),
            "processed": self.processed_count,
            "failed": self.failed_count,
            # "success_rate": (self.processed_count / len(files)) * 100 if files else 0,
            "errors": self.errors,
            "results": results
        }
        
        logger.info(f"🎯 Job completed: {self.processed_count} processed, {self.failed_count} failed")
        return summary


async def run_processing_job():
    """Run the file processing job."""
    try:
        # Get database session using the context manager
        from app.core.database import get_db_session
        
        async with get_db_session() as db:
            job = FileProcessingJob(db)
            result = await job.process_all_files()
            
            # Print summary
            # logger.info("📊 File Processing Job Summary")
            # logger.info(f"📁 Total files: {result['total_files']}")
            # logger.info(f"✅ Processed: {result['processed']}")
            # logger.info(f"❌ Failed: {result['failed']}")
            # logger.info(f"📈 Success rate: {result['success_rate']:.1f}%")
            
            if result['errors']:
                logger.info(f"\n❌ Errors:")
                for error in result['errors']:
                    logger.info(f"   - {error}")
            
            # logger.info("🎯 Job completed successfully!")
            
    except Exception as e:
        logger.error(f"Job failed: {e}")
        logger.error(f"❌ Job failed: {e}")


async def main():
    """Main function to run the job."""
    
    # Run the job
    while True:
        await run_processing_job()
        time.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
