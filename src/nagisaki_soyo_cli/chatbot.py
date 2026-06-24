from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APIError, AuthenticationError, RateLimitError

from .config import DEFAULT_MODEL, DEFAULT_TEMPERATURE, OPENAI_API_KEY, OPENAI_BASE_URL, TRANSCRIPTS_DIR
from .prompts import DEFAULT_SYSTEM_PROMPT


@dataclass
class ChatSession:
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    client: ChatOpenAI = field(init=False)
    messages: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is required. Set it in your environment or .env file.")
        client_kwargs: dict[str, object] = {
            "api_key": OPENAI_API_KEY,
            "model": self.model,
            "temperature": self.temperature,
        }
        if OPENAI_BASE_URL:
            client_kwargs["base_url"] = OPENAI_BASE_URL
        self.client = ChatOpenAI(**client_kwargs)

    def reply(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        response = self.client.invoke(self._build_messages())
        content = self._coerce_content(response.content)
        if not content:
            raise RuntimeError("The model returned an empty message.")
        self.messages.append({"role": "assistant", "content": content})
        return content

    def reset(self) -> None:
        self.messages.clear()

    def _build_messages(self) -> list[BaseMessage]:
        conversation: list[BaseMessage] = [SystemMessage(content=self.system_prompt)]
        for message in self.messages:
            role = message["role"]
            content = message["content"]
            if role == "user":
                conversation.append(HumanMessage(content=content))
                continue
            if role == "assistant":
                conversation.append(AIMessage(content=content))
                continue
            raise RuntimeError(f"Unsupported transcript role: {role}")
        return conversation

    def _coerce_content(self, content: object) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    text = block.strip()
                elif isinstance(block, dict):
                    maybe_text = block.get("text")
                    if not isinstance(maybe_text, str):
                        raise RuntimeError("The model returned a non-text content block.")
                    text = maybe_text.strip()
                else:
                    raise RuntimeError("The model returned an unsupported content block.")
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()
        raise RuntimeError("The model returned an unsupported content type.")

    def save_transcript(self) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = TRANSCRIPTS_DIR / f"{timestamp}.json"
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "system_prompt": self.system_prompt,
            "messages": self.messages,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


OPENAI_ERRORS = (AuthenticationError, RateLimitError, APIConnectionError, APIError)
