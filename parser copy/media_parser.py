"""
Media Parser Module

This module contains the MediaParser class for parsing various media types
(images, videos, audio) using the API endpoints.
"""

import requests
import os
from pathlib import Path
from typing import Dict, Any, Union, Optional
import logging
from .config import get_base_url, get_timeout

logger = logging.getLogger(__name__)


class MediaParser:
    """Client for parsing various media types using the API endpoints."""
    
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or get_base_url()).rstrip('/')
        self.session = requests.Session()
    
    def _upload_file(self, endpoint: str, file_path: Union[str, Path], field_name: str) -> Dict[str, Any]:
        """Helper method to upload files to endpoints."""
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            with open(file_path, 'rb') as file:
                files = {field_name: file}
                response = self.session.post(endpoint, files=files, timeout=get_timeout())
                response.raise_for_status()
                return response.json()
        except KeyboardInterrupt:
            logger.info(f"Upload interrupted by user for file: {file_path}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error uploading file {file_path}: {e}")
            raise
    
    def parse_image(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse image files (PNG, JPEG, JPG, TIFF, WEBP).
        
        Args:
            file_path: Path to the image file
            
        Returns:
            Dictionary containing the parsed image information
        """
        endpoint = f"{self.base_url}/parse_image/image"
        return self._upload_file(endpoint, file_path, "file")
    
    def process_image(self, 
                     file_path: Union[str, Path], 
                     task: str, 
                     prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Process an image with a specific task.
        
        Args:
            file_path: Path to the image file
            task: The processing task (OCR, Caption, Object Detection, etc.)
            prompt: Optional prompt for certain tasks
            
        Returns:
            Dictionary containing the processed image information
        """
        endpoint = f"{self.base_url}/parse_image/process_image"
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Image file not found: {file_path}")
        
        # Prepare the multipart form data exactly as specified in the API
        files = {'image': open(file_path, 'rb')}
        data = {'task': task}
        
        if prompt:
            data['prompt'] = prompt
        
        # Log the request details for debugging
        logger.info(f"Processing image: {file_path}")
        logger.info(f"Task: {task}")
        logger.info(f"Prompt: {prompt}")
        logger.info(f"Endpoint: {endpoint}")
        
        try:
            # Use multipart/form-data format as specified in the curl example
            response = self.session.post(
                endpoint, 
                files=files, 
                data=data, 
                timeout=get_timeout(),
                headers={'Accept': 'application/json'}
            )
            response.raise_for_status()
            return response.json()
        except KeyboardInterrupt:
            logger.info(f"Image processing interrupted by user for file: {file_path}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error processing image: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response text: {e.response.text}")
            raise
        finally:
            files['image'].close()
    
    def parse_video(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse video files (MP4, AVI, MOV, MKV).
        
        Args:
            file_path: Path to the video file
            
        Returns:
            Dictionary containing the parsed video information
        """
        endpoint = f"{self.base_url}/parse_media/video"
        return self._upload_file(endpoint, file_path, "file")
    
    def parse_audio(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parse audio files (MP3, WAV, FLAC).
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Dictionary containing the parsed audio information
        """
        endpoint = f"{self.base_url}/parse_media/audio"
        return self._upload_file(endpoint, file_path, "file")
