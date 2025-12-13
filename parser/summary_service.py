"""
Summary Service Module

This module provides a service to summarize extracted content using an external AI API.
"""

import requests
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import json
from app.core.config import settings

logger = logging.getLogger(__name__)


class SummaryService:
    """Service for summarizing extracted content using AI API."""
    
    def __init__(self, api_url: str = ""):
        self.api_url = api_url
        # print(f"SummaryService initialized with api_url: {self.api_url}")
        self.model = "gpt-oss:20b"
        self.session = requests.Session()
    
    def summarize_content(self, content: str, file_type: str = "unknown", max_length: int = 500) -> Dict[str, Any]:
        """
        Summarize extracted content using the AI API with streaming.
        
        - Chia content thành nhiều chunk theo dòng (\n), mỗi chunk không vượt quá CONTENT_LIMIT ký tự.
        - Gọi API tóm tắt từng chunk.
        - Ghép các summary con thành summary tổng.
        """
        try:
            if not content or len(content.strip()) == 0:
                return {
                    "success": False,
                    "error": "No content to summarize",
                    "summary": "",
                    "api_response": None
                }

            # Nếu nội dung đã nhỏ hơn hạn mức thì xử lý như cũ (1 chunk)
            if len(content) <= settings.CONTENT_LIMIT:
                return self._summarize_single_chunk(content, file_type, max_length)

            # Chia nội dung thành các chunk theo dòng, mỗi chunk <= CONTENT_LIMIT
            lines = content.split("\n")
            chunks: list[str] = []
            current_chunk = ""

            for line in lines:
                # Giữ lại newline để không mất cấu trúc đoạn
                candidate = (line + "\n")
                if len(current_chunk) + len(candidate) <= settings.CONTENT_LIMIT:
                    current_chunk += candidate
                else:
                    if current_chunk:
                        chunks.append(current_chunk.rstrip())
                        current_chunk = ""

                    # Nếu một dòng đơn lẻ dài hơn CONTENT_LIMIT thì cắt cứng
                    if len(candidate) > settings.CONTENT_LIMIT:
                        start = 0
                        while start < len(candidate):
                            chunks.append(candidate[start:start + settings.CONTENT_LIMIT])
                            start += settings.CONTENT_LIMIT
                    else:
                        current_chunk = candidate

            if current_chunk:
                chunks.append(current_chunk.rstrip())

            logger.info(
                f"Content length {len(content)} exceeds limit {settings.CONTENT_LIMIT}. "
                f"Split into {len(chunks)} chunks."
            )

            all_summaries: list[str] = []
            chunk_results: list[Dict[str, Any]] = []

            for idx, chunk in enumerate(chunks, start=1):
                logger.info(f"Summarizing chunk {idx}/{len(chunks)} (length: {len(chunk)})")
                result = self._summarize_single_chunk(chunk, file_type, max_length)
                chunk_results.append(result)

                if not result.get("success"):
                    # Nếu một chunk fail, dừng và trả lỗi (kèm summary đã có nếu có)
                    combined_partial = "\n\n".join(all_summaries).strip()
                    return {
                        "success": False,
                        "error": f"Failed to summarize chunk {idx}: {result.get('error')}",
                        "summary": combined_partial,
                        "api_response": None,
                    }

                chunk_summary = (result.get("summary") or "").strip()
                if chunk_summary:
                    all_summaries.append(chunk_summary)

            combined_summary = "\n\n".join(all_summaries).strip()

            # Lấy metadata của chunk cuối cùng (nếu cần)
            last_api_response = None
            last_metadata = None
            for r in reversed(chunk_results):
                if r.get("api_response") is not None:
                    last_api_response = r.get("api_response")
                    last_metadata = r.get("metadata")
                    break

            logger.info(
                f"✅ Successfully summarized {file_type} content via streaming in {len(chunks)} chunks "
                f"(original_length={len(content)}, summary_length={len(combined_summary)})"
            )

            return {
                "success": True,
                "summary": combined_summary,
                "api_response": last_api_response,
                "metadata": last_metadata,
                "original_length": len(content),
                "summary_length": len(combined_summary),
                "streaming": True,
                "chunks_count": len(chunks),
            }

        except Exception as e:
            error_msg = f"Unexpected error during multi-chunk summarization: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "summary": "",
                "api_response": None
            }

    def _summarize_single_chunk(
        self,
        content: str,
        file_type: str = "unknown",
        max_length: int = 500,
    ) -> Dict[str, Any]:
        """
        Tóm tắt một chunk nội dung (đã đảm bảo không vượt quá CONTENT_LIMIT).
        Giữ nguyên cơ chế streaming hiện tại.
        """
        try:
            if not content or len(content.strip()) == 0:
                return {
                    "success": False,
                    "error": "No content to summarize",
                    "summary": "",
                    "api_response": None
                }

            # Truncate phòng khi content vẫn dài hơn limit (phòng hờ)
            if len(content) > settings.CONTENT_LIMIT:
                content = content[:settings.CONTENT_LIMIT] + "..."

            system_prompt = f"""
                You are a helpful assistant tasked with summarizing content extracted from {file_type} files. 
                Please create a concise yet comprehensive summary that captures all key information without omitting important details. 
                Focus on clarity, logical structure, and readability. 
                Correct any grammatical, lexical, or stylistic errors in the original text. 
                MUST:
                    - The summary must be written in Vietnamese, 
                    - Using a scientific and formal writing style, presented in well-structured paragraphs.
                    - Do not use bullet points or tables markdown format in the summary.
                    - Separate each paragraph by a new line.
            """

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"Please summarize this {file_type} content:\n\n{content}"
                    }
                ],
                "stream": True
            }

            logger.info(f"Requesting streaming summary for {file_type} content (length: {len(content)})")
            response = self.session.post(
                self.api_url,
                headers={'Content-Type': 'application/json'},
                json=payload,
                timeout=120,
                stream=True
            )

            if response.status_code == 200:
                summary = ""
                metadata = {}
                last_response = None

                try:
                    for line in response.iter_lines(decode_unicode=True):
                        if line.strip():
                            try:
                                chunk_data = json.loads(line)

                                if chunk_data.get("message") and chunk_data["message"].get("content"):
                                    chunk_content = chunk_data["message"]["content"]
                                    summary += chunk_content

                                if chunk_data.get("done", False):
                                    last_response = chunk_data
                                    metadata = {
                                        "model": chunk_data.get("model"),
                                        "created_at": chunk_data.get("created_at"),
                                        "total_duration": chunk_data.get("total_duration"),
                                        "done_reason": chunk_data.get("done_reason"),
                                        "done": chunk_data.get("done"),
                                        "prompt_eval_count": chunk_data.get("prompt_eval_count"),
                                        "eval_count": chunk_data.get("eval_count"),
                                        "eval_duration": chunk_data.get("eval_duration")
                                    }
                                    break

                            except json.JSONDecodeError as e:
                                logger.warning(f"Failed to parse streaming chunk: {line[:100]}... Error: {e}")
                                continue

                except Exception as e:
                    logger.error(f"Error processing streaming response: {str(e)}")
                    return {
                        "success": False,
                        "error": f"Error processing streaming response: {str(e)}",
                        "summary": summary,
                        "api_response": None
                    }

                logger.info(f"✅ Successfully summarized {file_type} content via streaming")

                cleaned_summary = (summary or "").strip()

                return {
                    "success": True,
                    "summary": cleaned_summary,
                    "api_response": last_response,
                    "metadata": metadata,
                    "original_length": len(content),
                    "summary_length": len(cleaned_summary),
                    "streaming": True
                }
            else:
                error_msg = f"API request failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "summary": "",
                    "api_response": None
                }

        except requests.exceptions.Timeout:
            error_msg = "Streaming API request timed out"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "summary": "",
                "api_response": None
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Streaming API request failed: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "summary": "",
                "api_response": None
            }
        except Exception as e:
            error_msg = f"Unexpected error during streaming summarization: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "summary": "",
                "api_response": None
            }
    
    def summarize_parser_result(self, parser_result: Dict[str, Any], file_extension: str) -> Dict[str, Any]:
        """
        Summarize content from a parser result.
        
        Args:
            parser_result: Result from any parser
            file_extension: File extension for context
            
        Returns:
            Enhanced parser result with AI summary replacing regular summary
        """
        try:
            # Extract content from parser result
            content = self._extract_content_from_result(parser_result)
            
            if not content:
                logger.warning(f"No content found in parser result for {file_extension}")
                return parser_result
            
            # Get AI summary
            summary_result = self.summarize_content(content, file_extension)
            
            # Enhance the original result with AI summary
            enhanced_result = parser_result.copy()
            
            if summary_result["success"]:
                # Replace the regular summary with AI summary
                enhanced_result["summary"] = summary_result["summary"]
                enhanced_result["ai_summary_metadata"] = summary_result["metadata"]
                enhanced_result["has_ai_summary"] = True
                logger.info(f"✅ Added AI summary to {file_extension} result")
            else:
                # Keep original summary if AI summary fails
                enhanced_result["ai_summary_error"] = summary_result["error"]
                enhanced_result["has_ai_summary"] = False
                logger.warning(f"❌ Failed to add AI summary to {file_extension}: {summary_result['error']}")
            
            return enhanced_result
            
        except Exception as e:
            logger.error(f"Error enhancing parser result with AI summary: {str(e)}")
            return parser_result
    
    def extract_metadata(self, content: str, file_type: str = "unknown") -> Dict[str, Any]:
        """
        Extract metadata from content including countries, technologies, companies, and important news.
        
        Args:
            content: The extracted content to analyze
            file_type: Type of file being analyzed
            
        Returns:
            Dictionary containing the metadata response
        """
        try:
            if not content or len(content.strip()) == 0:
                return {
                    "success": False,
                    "error": "No content to analyze",
                    "metadata": None
                }
            
            # Truncate content if too long to avoid API limits
            if len(content) > settings.CONTENT_LIMIT:
                content = content[:settings.CONTENT_LIMIT] + "..."
            
            # Create system prompt for metadata extraction
            system_prompt = f"""
                You are a helpful assistant tasked with extracting specific metadata from {file_type} files. 
                Please analyze the content and extract the following information in JSON format only:
                - listed_nation: List of countries mentioned in the document
                - listed_technology: List the main technologies, tools, or technical terms mentioned
                - listed_company: List of organizations, main objects, or institutions mentioned (Add explaining like Công ty, Khu vực, Địa điểm, Đối tượng (human), Sản phẩm... + name)
                - important_news: List of important news items (a news need to be unique, about 1 topic, each as a short (2 or 3) sentence)
                
                CRITICAL: Return ONLY valid JSON format without any additional text, explanations, or markdown formatting.
                Do NOT use the special character in answering content that cause json parse error
                Do NOT use ```json``` or ``` or any other markdown formatting. 
                Do NOT add any comments or explanations before or after the JSON.
                Start your response directly with {{ and end with }}.
                Just return the raw JSON object.
                
                Example format (return exactly like this):
                {{"listed_nation": ["Vietnam", "United States", "China"], "listed_technology": ["AI", "Machine Learning", "Blockchain"], "listed_company": ["Công ty: Google", "Khu vực: Biển Đông", "Đối tượng: Trump"], "important_news": ["Company announces new AI breakthrough in healthcare", "Partnership established between major tech companies", "New regulations affect technology sector"]}}
                
                Language: Always translate and answering in Vietnamese
                Luôn trả về định dạng JSON chính xác.
            """
            
            # Prepare the API request with streaming enabled
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"Please extract metadata from this {file_type} content:\n\n{content}"
                    }
                ],
                "stream": True  # Enable streaming for JSON response
            }
            
            # Make streaming API request
            logger.info(f"Requesting streaming metadata extraction for {file_type} content (length: {len(content)})")
            response = self.session.post(
                self.api_url,
                headers={'Content-Type': 'application/json'},
                json=payload,
                timeout=120,  # Increased timeout for streaming
                stream=True  # Enable streaming response
            )
            
            if response.status_code == 200:
                # Process streaming response
                json_content = ""
                metadata = {}
                last_response = None
                
                try:
                    for line in response.iter_lines(decode_unicode=True):
                        if line.strip():
                            try:
                                chunk_data = json.loads(line)
                                
                                # Extract content from streaming chunk
                                if chunk_data.get("message") and chunk_data["message"].get("content"):
                                    chunk_content = chunk_data["message"]["content"]
                                    json_content += chunk_content
                                
                                # Store metadata from the last chunk
                                if chunk_data.get("done", False):
                                    last_response = chunk_data
                                    break
                                    
                            except json.JSONDecodeError as e:
                                logger.warning(f"Failed to parse streaming chunk: {line[:100]}... Error: {e}")
                                continue
                    
                    logger.info(f"JSON content: {json_content[:200]}...")

                    # Parse the complete JSON content
                    if json_content.strip():
                        try:
                            # Clean the JSON content by removing markdown formatting
                            cleaned_json = self._clean_json_content(json_content.strip())
                            logger.info(f"Cleaned JSON content: {cleaned_json[:200]}...")
                            metadata = json.loads(cleaned_json)
                            
                            # Validate required fields
                            required_fields = ["listed_nation", "listed_technology", "listed_company", "important_news"]
                            for field in required_fields:
                                if field not in metadata:
                                    metadata[field] = []
                            
                            # Print the JSON result for debugging
                            print(f"🏷️ Metadata JSON Result for {file_type}:")
                            print(json.dumps(metadata, indent=2, ensure_ascii=False))
                            
                            logger.info(f"✅ Successfully extracted metadata for {file_type} content via streaming")
                            
                            return {
                                "success": True,
                                "metadata": metadata,
                                "api_response": last_response,
                                "original_length": len(content),
                                "streaming": True
                            }
                            
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse JSON from streaming response: {e}")
                            logger.error(f"Original JSON content: {json_content[:500]}...")
                            logger.error(f"Cleaned JSON content: {cleaned_json[:500]}...")
                            return {
                                "success": False,
                                "error": f"Failed to parse JSON response: {str(e)}",
                                "metadata": None,
                                "raw_response": json_content,
                                "cleaned_response": cleaned_json
                            }
                    else:
                        error_msg = "No JSON content received from streaming response"
                        logger.error(error_msg)
                        return {
                            "success": False,
                            "error": error_msg,
                            "metadata": None,
                            "api_response": last_response
                        }
                                
                except Exception as e:
                    logger.error(f"Error processing streaming response: {str(e)}")
                    return {
                        "success": False,
                        "error": f"Error processing streaming response: {str(e)}",
                        "metadata": None,
                        "raw_response": json_content
                    }
            else:
                error_msg = f"API request failed with status {response.status_code}: {response.text}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "metadata": None
                }
                
        except requests.exceptions.Timeout:
            error_msg = "Metadata extraction API request timed out"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "metadata": None
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"Metadata extraction API request failed: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "metadata": None
            }
        except Exception as e:
            error_msg = f"Unexpected error during metadata extraction: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "metadata": None
            }

    def _clean_json_content(self, json_content: str) -> str:
        """
        Clean JSON content by removing markdown formatting and other unwanted characters.
        
        Args:
            json_content: Raw JSON content that may contain markdown formatting
            
        Returns:
            Cleaned JSON string ready for parsing
        """
        if not json_content:
            return ""
        
        # Remove markdown code block formatting
        # Remove ```json at the beginning
        if json_content.strip().startswith('```json'):
            json_content = json_content.strip()[7:]  # Remove ```json
        elif json_content.strip().startswith('```'):
            json_content = json_content.strip()[3:]   # Remove ```
        
        # Remove ``` at the end
        if json_content.strip().endswith('```'):
            json_content = json_content.strip()[:-3]  # Remove trailing ```
        
        # Remove any leading/trailing whitespace
        json_content = json_content.strip()
        
        # Remove any other markdown artifacts
        lines = json_content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Skip empty lines or lines that look like markdown artifacts
            if line.strip() and not line.strip().startswith('#') and not line.strip().startswith('*'):
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    def _extract_content_from_result(self, result: Dict[str, Any]) -> str:
        """Extract content from parser result for summarization."""
        if not result:
            return ""
        
        # Try different content fields
        content_fields = ['content', 'text_content', 'data', 'text', 'description']
        
        for field in content_fields:
            if field in result and result[field]:
                content = result[field]
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    return '\n'.join(str(item) for item in content)
                elif isinstance(content, dict):
                    return str(content)
        
        # If no specific content field, return the whole result as string
        return str(result)
