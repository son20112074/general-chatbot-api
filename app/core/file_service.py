import os
import hashlib
import mimetypes
from pathlib import Path
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.models.file import File
from datetime import datetime
from typing import List, Optional

class FileService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.upload_dir = Path("static/uploads")
        self._ensure_upload_dir()

    def _ensure_upload_dir(self):
        """Ensure upload directory exists"""
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_directory(self) -> Path:
        """Get directory for current date"""
        today = datetime.now()
        year_month = today.strftime("%Y/%m")
        directory = self.upload_dir / year_month
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    async def calculate_file_hash(self, file: UploadFile, algorithm='sha256'):
        """Calculate file hash"""
        await file.seek(0)
        hasher = hashlib.new(algorithm)
        while True:
            chunk = await file.read(4096)
            if not chunk:
                break
            hasher.update(chunk)
        await file.seek(0)  # Reset file pointer after reading
        return hasher.hexdigest()

    def get_mime_type(self, filename: str) -> str:
        """Get MIME type for file"""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or 'application/octet-stream'

    def _filter_fields(self, data: dict, fields: Optional[List[str]] = None) -> dict:
        """Filter dictionary to include only specified fields"""
        if not fields or "*" in fields:
            return data
        return {k: v for k, v in data.items() if k in fields}

    async def save_file(self, file: UploadFile, user_id: int, fields: Optional[List[str]] = None, is_save: bool = True) -> dict:
        """Save file and return file metadata
        
        Args:
            file: The file to upload
            user_id: ID of the user uploading the file
            fields: Optional list of fields to include in response
            is_save: If True, save to database. If False, only save to disk.
        """
        # Calculate file hash
        file_hash = await self.calculate_file_hash(file)
        
        # Get file metadata
        contents = await file.read()
        file_size = len(contents)
        file_name = file.filename
        file_root, file_extension = os.path.splitext(file_name)
        mime_type = self.get_mime_type(file_name)

        # Create file path in year/month directory
        file_dir = self._get_file_directory()
        file_path = str(file_dir / f"{file_hash}{file_extension}")
        
        # Save file if it doesn't exist
        if not os.path.exists(file_path):
            with open(file_path, "wb") as f:
                f.write(contents)

        # If is_save=False, only save to disk and return basic file info
        if not is_save:
            file_dict = {
                "name": file_name,
                "size": file_size,
                "hash": file_hash,
                "path": file_path,
                "extension": file_extension,
                "mime_type": mime_type,
                "url": f"/api/v1/static/uploads/{os.path.relpath(file_path, 'static/uploads')}",
                "saved_to_db": False
            }
            return self._filter_fields(file_dict, fields)

        # Check if file already exists in database
        existing_file = await self.session.execute(
            select(File).where(File.hash == file_hash)
        )
        existing_file = existing_file.scalar_one_or_none()

        if existing_file:
            # Reset processing and embedding status to null when file is re-uploaded
            existing_file.is_processed = None
            existing_file.is_embedded = None
            existing_file.updated_at = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(existing_file)
            
            file_dict = existing_file.to_dict()
            file_dict["url"] = f"/api/v1/static/uploads/{os.path.relpath(file_path, 'static/uploads')}"
            return self._filter_fields(file_dict, fields)

        # Create new file record
        new_file = File(
            name=file_name,
            size=file_size,
            hash=file_hash,
            path=file_path,
            extension=file_extension,
            mime_type=mime_type,
            created_by=user_id
        )

        self.session.add(new_file)
        await self.session.commit()
        await self.session.refresh(new_file)

        # Convert the file path to a public URL
        file_dict = new_file.to_dict()
        file_dict["url"] = f"/api/v1/static/uploads/{os.path.relpath(file_path, 'static/uploads')}"
        return self._filter_fields(file_dict, fields) 