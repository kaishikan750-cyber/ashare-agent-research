"""Actual LangChain tools and model factory, used by the LangGraph pipeline."""
from __future__ import annotations

import json
import os

from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from research_agent.llm import AssistantMessage
from research_agent.settings import model_available


def structured_tools(registry):
    tools = {}
    for name, (schema, fn, description) in registry.specs.items():
        def invoke(_schema=schema, _fn=fn, **kwargs):
            return _fn(_schema.model_validate(kwargs))
        tools[name] = StructuredTool.from_function(func=invoke, name=name, description=description, args_schema=schema)
    return tools


class LangChainModelClient:
    def __init__(self, chat_model=None, http_client=None):
        self.chat_model = chat_model
        self.http_client = http_client

    def complete(self, messages, tools):
        if self.chat_model is None:
            if not model_available():
                raise ValueError("LLM mode requires LLM_BASE_URL, LLM_API_KEY and LLM_MODEL")
            base = os.environ["LLM_BASE_URL"].rstrip("/")
            from urllib.parse import urlparse
            parsed = urlparse(base)
            if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
                raise ValueError("LLM_BASE_URL requires HTTPS or local HTTP")
            from langchain.chat_models import init_chat_model
            self.chat_model = init_chat_model(os.environ["LLM_MODEL"], model_provider="openai",
                api_key=os.environ["LLM_API_KEY"], base_url=base, temperature=0,
                timeout=45, max_retries=0, max_tokens=1200, use_responses_api=False,
                **({"http_client": self.http_client} if self.http_client is not None else {}))
        try:
            response = self.chat_model.bind_tools(tools, tool_choice="auto").invoke(messages)
            if response.invalid_tool_calls:
                raise ValueError("invalid tool arguments")
            data = {"role": "assistant", "content": response.content if isinstance(response.content, str) else None}
            if response.tool_calls:
                data["tool_calls"] = [{"id": call["id"], "type": "function", "function": {
                    "name": call["name"], "arguments": json.dumps(call["args"], ensure_ascii=False)}} for call in response.tool_calls]
            validated = AssistantMessage.model_validate(data)
            if validated.tool_calls and len({c.id for c in validated.tool_calls}) != len(validated.tool_calls):
                raise ValueError("duplicate tool IDs")
            return validated.model_dump(exclude_none=True)
        except Exception:
            # Provider text may contain requests/credentials; persist only a stable error.
            raise RuntimeError("LangChain model request failed or invalid tool response") from None


def tool_definitions(registry):
    return [convert_to_openai_tool(t) for t in structured_tools(registry).values()]
