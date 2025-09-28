from __future__ import annotations

import os


def generate_commentary(summary: str, pro: bool = False) -> str:
    # Placeholder; integrate OpenAI later
    if pro:
        return f"Pro commentary: {summary[:500]}"
    return f"Basic commentary: {summary[:200]}"

