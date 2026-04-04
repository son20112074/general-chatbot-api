from typing import Any, List, Optional
import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from pydantic import PrivateAttr

logger = logging.getLogger("LangChainLLMWrapper")


class LangChainLLMWrapper(BaseChatModel):
    """
    Adapter for custom async LLM client.
    """

    # ✅ IMPORTANT: declare as private attribute (NOT pydantic field)
    _client: Any = PrivateAttr()

    def __init__(self, client: Any, **kwargs):
        super().__init__(**kwargs)
        self._client = client

    # -------------------------
    async def _agenerate(
        self,
        messages: List[Any],
        stop: Optional[List[str]] = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:

        prompt = self._convert_messages_to_prompt(messages)

        response = await self._client.ainvoke(prompt)

        # Extract content and additional_kwargs from the response
        content = getattr(response, "content", None) or ""
        additional_kwargs = getattr(response, "additional_kwargs", {})
        
        content = str(content).strip() if content else ""
        
        logger.info(f"[LLM_WRAPPER] Raw content: '{content[:200] if content else '(empty)'}'")

        # If content is empty but we have tool_calls, convert to ReAct format
        if not content and additional_kwargs.get("tool_calls"):
            import json
            tool_calls = additional_kwargs["tool_calls"]
            tool_call = tool_calls[0] if tool_calls else None
            
            if tool_call and tool_call.get("function"):
                func_name = tool_call["function"].get("name", "")
                func_args = tool_call["function"].get("arguments", "")
                
                try:
                    args_dict = json.loads(func_args) if func_args else {}
                except (json.JSONDecodeError, TypeError):
                    args_dict = {}
                
                if func_name == "sql_db_query" and "query" in args_dict:
                    action_input = args_dict["query"]
                elif func_name == "sql_db_schema" and "table_name" in args_dict:
                    action_input = args_dict["table_name"]
                elif args_dict:
                    action_input = ", ".join(str(v) for v in args_dict.values())
                else:
                    action_input = ""
                
                content = f"Action: {func_name}\nAction Input: {action_input}"
                logger.info(f"[LLM_WRAPPER] Converted tool_call to ReAct: {content}")

        # Sanitize: if response contains BOTH Action and Final Answer, keep only the first Action
        if content and "Action:" in content and "Final Answer:" in content:
            action_pos = content.find("Action:")
            final_pos = content.find("Final Answer:")
            if action_pos < final_pos:
                # Keep only the Action part (strip everything from Final Answer onward)
                content = content[:final_pos].strip()
                logger.info(f"[LLM_WRAPPER] Stripped Final Answer from mixed response")
            else:
                # Final Answer comes first, keep only that
                content = content[final_pos:].strip()
                # Also strip any Action that follows
                action_after = content.find("Action:", len("Final Answer:"))
                if action_after > 0:
                    content = content[:action_after].strip()
                logger.info(f"[LLM_WRAPPER] Stripped Action from mixed response")

        # If still no content, use a fallback
        if not content:
            logger.warning("[LLM_WRAPPER] Empty content from LLM, using fallback")
            content = "Final Answer: Không có kết quả phù hợp."

        # Create message
        message = AIMessage(content=content)

        return ChatResult(
            generations=[
                ChatGeneration(message=message)
            ]
        )

    # -------------------------
    def _generate(self, *args, **kwargs):
        raise NotImplementedError("Sync not supported")

    # -------------------------
    def _convert_messages_to_prompt(self, messages: List[Any]) -> str:
        parts = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                parts.append(f"[SYSTEM]\n{msg.content}")
            elif isinstance(msg, HumanMessage):
                parts.append(f"[USER]\n{msg.content}")
            elif isinstance(msg, AIMessage):
                parts.append(f"[ASSISTANT]\n{msg.content}")
            else:
                parts.append(str(msg))

        return "\n\n".join(parts)

    # -------------------------
    @property
    def _llm_type(self) -> str:
        return "custom_chat_model"