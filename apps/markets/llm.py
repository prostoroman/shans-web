"""
LLM integration for AI asset summary using OpenAI Chat Completions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _build_prompt(data: Dict[str, Any]) -> str:
    meta = data.get("meta", {})
    calc = data.get("calc", {})
    price = data.get("price", {})
    fundamentals = data.get("fundamentals", {})
    consensus = data.get("consensus", {})
    macro = data.get("macro", {})
    news = data.get("news", [])

    # Keep the prompt concise yet structured
    prompt = (
        "You are a senior buy-side analyst. Analyze the provided asset data and write a concise, professional insight for shans.ai users.\n"
        "Structure strictly as three sections with headers: HISTORY, CURRENT SITUATION, FORECAST.\n"
        "- HISTORY: summarize long-term trend, notable drawdowns, and regime shifts.\n"
        "- CURRENT SITUATION: valuation vs history/peers, profitability/quality, balance-sheet risks, key recent news drivers.\n"
        "- FORECAST: base/bull/bear scenarios with a fair value range and a one-word recommendation (Positive / Neutral / Cautious).\n"
        "Write 120-170 words total. Avoid boilerplate. Use numbers when helpful.\n"
        "Use USD or the native currency provided.\n"
    )

    compact = {
        "meta": meta,
        "price": price,
        "calc": calc,
        "fundamentals": {
            "ttm_keys": list((fundamentals.get("ttm") or {}).keys())[:20],
        },
        "consensus": {
            "targets": consensus.get("targets"),
            "rating": consensus.get("rating"),
        },
        "macro": macro,
        "news": [{"title": n.get("title"), "publishedDate": n.get("publishedDate")} for n in news[:5]],
    }

    prompt += "\nDATA:\n" + json.dumps(compact, ensure_ascii=False)
    return prompt


def generate_asset_summary(data: Dict[str, Any]) -> Optional[str]:
    """Call OpenAI Chat Completions to generate summary text."""
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY is not configured; returning None for summary")
        return None

    model = "gpt-4o-mini"
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    system_prompt = "You are a precise financial analyst creating short, actionable insights."
    user_prompt = _build_prompt(data)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 450,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        choices = body.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content")
        return None
    except Exception as e:  # noqa: BLE001
        logger.error(f"OpenAI summary generation failed: {e}")
        return None


