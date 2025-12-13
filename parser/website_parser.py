"""
Website Parser Module

This module contains the WebsiteParser class for parsing websites using the API endpoints.
"""

import requests
from typing import Dict, Any
import logging
from .config import get_base_url, get_timeout

logger = logging.getLogger(__name__)


class WebsiteParser:
    """Client for parsing websites using the API endpoints."""
    
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or get_base_url()).rstrip('/')
        self.session = requests.Session()
    
    def parse_website(self, url: str) -> Dict[str, Any]:
        """
        Parse a website given its URL.
        
        Args:
            url: The URL of the website to parse
            
        Returns:
            Dictionary containing the parsed website information
        """
        endpoint = f"{self.base_url}/parse_website"
        
        headers = {'Content-Type': 'application/json'}
        data = {'url': url}
        
        try:
            response = self.session.post(endpoint, headers=headers, json=data, timeout=get_timeout())
            response.raise_for_status()
            return response.json()
        except KeyboardInterrupt:
            logger.info(f"Website parsing interrupted by user for URL: {url}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error parsing website: {e}")
            raise
