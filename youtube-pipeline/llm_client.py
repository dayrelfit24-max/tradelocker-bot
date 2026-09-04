"""LLM helper — Claude (Anthropic) or OpenAI for scripts and SEO."""

from __future__ import annotations

import json
import re

import config


def _strip_json_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    return raw.strip()


def _parse_json(raw: str) -> dict | None:
    raw = _strip_json_fence(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def active_provider() -> str | None:
    """Returns 'claude', 'openai', or None."""
    mode = getattr(config, "AI_PROVIDER", "auto").lower()
    has_claude = bool(getattr(config, "ANTHROPIC_API_KEY", ""))
    has_openai = bool(config.OPENAI_API_KEY)
    if mode == "claude":
        return "claude" if has_claude else None
    if mode == "openai":
        return "openai" if has_openai else None
    if has_claude:
        return "claude"
    if has_openai:
        return "openai"
    return None


def chat_json(system: str, user: str, temperature: float = 0.7) -> dict | None:
    provider = active_provider()
    if not provider:
        return None
    try:
        if provider == "claude":
            raw = _claude_chat(system, user, temperature)
        else:
            raw = _openai_chat(system, user, temperature)
        return _parse_json(raw) if raw else None
    except Exception as e:
        print(f"      ⚠ LLM ({provider}) error: {e}")
        return None


CLAUDE_FALLBACK_MODELS = (
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
    "claude-opus-4-6",
)


def _claude_chat(system: str, user: str, temperature: float) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    models = [config.CLAUDE_MODEL, *CLAUDE_FALLBACK_MODELS]
    seen: set[str] = set()
    last_err: Exception | None = None

    for model in models:
        if model in seen:
            continue
        seen.add(model)
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=temperature,
            )
            parts = []
            for block in msg.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
            return "".join(parts)
        except Exception as e:
            last_err = e
            if "not_found" not in str(e).lower() and "404" not in str(e):
                raise
    raise last_err or RuntimeError("No Claude model available")


def _openai_chat(system: str, user: str, temperature: float) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""