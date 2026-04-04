import os
import json
import httpx
from typing import Dict, Any, Optional

from app.core.config import settings


class OpenAIClient:
    """Client for interacting with OpenAI API"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        print("----------------------------------------------------USING OPENAI GPT-4o----------------------------------------------------")
        self.api_base = settings.LLM_API
        self.model = settings.LLM_MODEL
    
    async def ainvoke(self, prompt: str):
        """Invoke the OpenAI API with a prompt and return a response object"""
        content = await self.generate(prompt)
        
        # Create a simple object with a content attribute to match the expected interface
        class Response:
            def __init__(self, content):
                self.content = content
        
        return Response(content)

    async def generate(self, prompt: str) -> str:
        """Generate text completion using OpenAI API"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,  # Low temperature for more deterministic SQL generation
            "max_tokens": 1000
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30.0
            )
            
            if response.status_code != 200:
               
                raise Exception(f"OpenAI API error: {response.text}")
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
