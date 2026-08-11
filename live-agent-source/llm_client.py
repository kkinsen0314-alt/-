"""OpenAI-compatible chat client with retries and tool-call parsing."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional
from urllib import error, request

from observability import log_event


RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


class ToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict[str, Any]):
        self.id = call_id
        self.name = name
        self.arguments = arguments


class LLMResponse:
    def __init__(
        self,
        content: Optional[str],
        tool_calls: Optional[list[ToolCall]] = None,
        finish_reason: str = "",
    ):
        self.content = content
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMClient:
    """通用 LLM 客户端，支持普通对话、结构化 JSON 和 function calling。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        logger=None,
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        if not self.api_key:
            raise ValueError("未设置 LLM_API_KEY，不能调用 LLM API")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", "deepseek-chat")
        self.timeout = _env_int("LLM_TIMEOUT_SECONDS", 60)
        self.max_retries = _env_int("LLM_MAX_RETRIES", 3)
        self.logger = logger

    @property
    def chat_url(self) -> str:
        return f"{self.base_url}/chat/completions" if self.base_url.endswith("/v1") else f"{self.base_url}/v1/chat/completions"

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        run_id: str = "",
        response_format: Optional[dict] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        result = self._post_json(self.chat_url, payload, run_id=run_id)
        return result["choices"][0]["message"].get("content") or ""

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 2500,
        run_id: str = "",
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        result = self._post_json(self.chat_url, payload, run_id=run_id)
        choice = result["choices"][0]
        message = choice.get("message", {})
        calls = []
        for raw_call in message.get("tool_calls") or []:
            function = raw_call.get("function", {})
            raw_arguments = function.get("arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"工具参数不是合法 JSON: {raw_arguments}") from exc
            calls.append(ToolCall(raw_call.get("id", ""), function.get("name", ""), arguments))
        return LLMResponse(
            content=message.get("content"),
            tool_calls=calls,
            finish_reason=choice.get("finish_reason", ""),
        )

    def _post_json(self, url: str, payload: dict, run_id: str = "") -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        total_attempts = self.max_retries + 1
        for attempt in range(total_attempts):
            log_event(self.logger, "llm_request", run_id, {"attempt": attempt + 1, "url": url}) if self.logger else None
            try:
                with request.urlopen(req, timeout=self.timeout) as response:
                    raw_body = response.read().decode("utf-8")
                result = json.loads(raw_body)
                if self.logger:
                    log_event(self.logger, "llm_success", run_id, {"attempt": attempt + 1})
                return result
            except error.HTTPError as exc:
                body_text = exc.read().decode("utf-8", errors="replace")[:2000]
                retryable = exc.code in RETRYABLE_HTTP_CODES and attempt < self.max_retries
                if retryable:
                    self._retry(attempt, run_id, f"HTTP {exc.code}")
                    continue
                self._failure(run_id, f"HTTP {exc.code}: {body_text}")
                raise RuntimeError(f"API 调用失败 (HTTP {exc.code}): {body_text}") from exc
            except (error.URLError, TimeoutError) as exc:
                if attempt < self.max_retries:
                    self._retry(attempt, run_id, str(exc))
                    continue
                self._failure(run_id, str(exc))
                reason = getattr(exc, "reason", str(exc))
                raise RuntimeError(f"网络连接失败: {reason}") from exc
            except json.JSONDecodeError as exc:
                self._failure(run_id, f"invalid_json: {exc}")
                raise RuntimeError(f"API 返回不是合法 JSON: {exc}") from exc
            except (KeyError, IndexError, TypeError) as exc:
                self._failure(run_id, f"invalid_response: {exc}")
                raise RuntimeError(f"API 返回格式不符合预期: {exc}") from exc
        raise RuntimeError("API 调用失败：超过最大重试次数")

    def _retry(self, attempt: int, run_id: str, reason: str) -> None:
        delay = min(2 ** attempt, 8)
        if self.logger:
            log_event(self.logger, "llm_retry", run_id, {"attempt": attempt + 1, "delay_s": delay, "reason": reason})
        time.sleep(delay)

    def _failure(self, run_id: str, reason: str) -> None:
        if self.logger:
            log_event(self.logger, "llm_failure", run_id, {"reason": reason})
