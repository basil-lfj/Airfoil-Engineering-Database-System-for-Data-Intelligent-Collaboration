from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import DeepSeekConfig


class DeepSeekError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatCompletion:
    raw_text: str
    content_text: str


def _endpoint(base_url: str) -> str:
    return base_url.rstrip("/") + "/chat/completions"


def _extract_first_json_object(text: str) -> str | None:
    t = text.strip()
    if not t:
        return None
    if t.startswith("{") and t.endswith("}"):
        return t

    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t, flags=re.IGNORECASE)
    if m:
        inner = m.group(1).strip()
        if inner.startswith("{") and inner.endswith("}"):
            return inner

    start = t.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(t)):
        ch = t[i]
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return t[start : i + 1].strip()
            continue

    return None


def _parse_json_object(text: str) -> dict:
    candidate = _extract_first_json_object(text)
    if candidate is None:
        raise ValueError("no json object found")
    return json.loads(candidate)


def chat_once(cfg: DeepSeekConfig, messages: list[dict], *, timeout_s: float | None = None) -> ChatCompletion:
    if not cfg.base_url:
        raise DeepSeekError("missing BASE_URL")
    if not cfg.api_key:
        raise DeepSeekError("missing API_KEY")

    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "top_p": cfg.top_p,
        "max_tokens": cfg.max_tokens,
        "stream": False,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        _endpoint(cfg.base_url),
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_s or cfg.timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        raise DeepSeekError(f"http {e.code}: {body[:500]}") from e
    except urllib.error.URLError as e:
        raise DeepSeekError("network error") from e

    try:
        obj = json.loads(raw)
        content = obj["choices"][0]["message"]["content"]
        return ChatCompletion(raw_text=raw, content_text=str(content))
    except Exception as e:
        raise DeepSeekError("unexpected response format") from e


@dataclass(frozen=True)
class JsonCallResult:
    obj: dict
    raw_text: str
    content_text: str
    parse_attempts: int


def call_json_with_retries(
    cfg: DeepSeekConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_s: float | None = None,
    max_format_retries: int = 3,
) -> JsonCallResult:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    net_attempt = 0
    while True:
        try:
            completion = chat_once(cfg, messages, timeout_s=timeout_s)
            break
        except DeepSeekError as e:
            if net_attempt >= cfg.max_retries:
                raise
            sleep_s = 0.5 * (2**net_attempt)
            time.sleep(sleep_s)
            net_attempt += 1
            continue

    parse_attempts = 0
    last_completion = completion
    while True:
        parse_attempts += 1
        try:
            obj = _parse_json_object(last_completion.content_text)
            return JsonCallResult(
                obj=obj,
                raw_text=last_completion.raw_text,
                content_text=last_completion.content_text,
                parse_attempts=parse_attempts,
            )
        except Exception:
            if parse_attempts > max_format_retries:
                raise DeepSeekError("json parse failed after retries")

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": user_prompt
                    + "\n\n请仅输出一个合法 JSON 对象，不要输出 Markdown 代码块，不要输出解释文字。",
                },
            ]

            last_completion = chat_once(cfg, messages, timeout_s=timeout_s)

