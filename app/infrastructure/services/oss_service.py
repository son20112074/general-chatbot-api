import os
import httpx
import asyncio
from typing import Optional
import json
from langchain_core.messages import AIMessage
from app.core.config import settings
    

class OpenRouterClient:
    def __init__(self):
        print("---- USING GPT-OSS 20B ----")
        self.api_base = settings.LLM_API
        self.model = settings.LLM_MODEL
        self.api_key = settings.OPENAI_API_KEY

    async def ainvoke(self, prompt: str):
        return await self.safe_generate(prompt)

    # -------------------------
    # SAFETY WRAPPER
    # -------------------------
    async def safe_generate(self, prompt: str) -> AIMessage:
        try:
            return await asyncio.wait_for(self.generate(prompt), timeout=25)
        except asyncio.TimeoutError:
            print("⏱ Timeout → fallback")
            return AIMessage(content="Hệ thống đang bận, vui lòng thử lại.")
        except Exception as e:
            print("💥 Error:", e)
            return AIMessage(content="Có lỗi xảy ra, vui lòng thử lại.")

    # -------------------------
    # FIX ARGUMENTS (CRITICAL)
    # -------------------------
    def _fix_arguments(self, args: str) -> str:
        if not args:
            return "{}"

        args = args.strip()

        if args == "":
            return "{}"

        # ✅ CASE 1: already valid JSON
        try:
            json.loads(args)
            return args
        except:
            pass

        # ✅ CASE 2: split by comma OR newline
        parts = re.split(r"[,\n]+", args)

        cleaned = [p.strip() for p in parts if p.strip()]

        if not cleaned:
            return "{}"

        # ✅ If single value → still wrap correctly
        if len(cleaned) == 1:
            return json.dumps({"tables": cleaned})

        return json.dumps({"tables": cleaned})

    # -------------------------
    # MAIN GENERATE
    # -------------------------
    async def generate(self, prompt: str) -> AIMessage:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 2000,  # ✅ increase to avoid truncation
            "provider": {
                "allow_fallbacks": True,
                "order": ["fireworks", "deepinfra"]
            }
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30.0
            )

        if response.status_code != 200:
            raise Exception(f"OpenRouter error: {response.text}")

        result = response.json()
        # print("---- RAW RESULT ----")
        # print(result)

        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = message.get("content")
        tool_calls = message.get("tool_calls")
        finish_reason = choice.get("finish_reason")

        # -------------------------
        # HANDLE TOOL CALLS (FIX)
        # -------------------------
        if tool_calls:
            fixed_calls = []

            for tc in tool_calls:
                try:
                    fn = tc.get("function", {})
                    name = fn.get("name")
                    args = fn.get("arguments", "")

                    fixed_args = self._fix_arguments(args)

                    fixed_calls.append({
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": fixed_args
                        }
                    })

                except Exception as e:
                    print("⚠️ Tool parse error:", e)
                    continue

            return AIMessage(
                content="",
                additional_kwargs={"tool_calls": fixed_calls}
            )

        # -------------------------
        # HANDLE TRUNCATION
        # -------------------------
        if finish_reason == "length":
            print("⚠️ Truncated output")
            return AIMessage(content="⚠️ Kết quả bị cắt, vui lòng thử lại.")

        # -------------------------
        # NORMAL TEXT RESPONSE
        # -------------------------
        if content:
            return AIMessage(content=content)

        # -------------------------
        # LAST RESORT FALLBACK
        # -------------------------
        return AIMessage(content="Không có kết quả phù hợp.")