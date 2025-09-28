from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx
from django.conf import settings


class FMPClient:
    BASE_URL = "https://financialmodelingprep.com/api/v3"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 20.0) -> None:
        self.api_key = api_key or settings.FMP_API_KEY
        self.timeout = timeout
        self.client = httpx.Client(timeout=self.timeout)

    def get_json(self, path: str, params: Optional[Dict[str, Any]] = None, retries: int = 3) -> Any:
        url = f"{self.BASE_URL}{path}"
        params = {**(params or {}), "apikey": self.api_key}
        for attempt in range(retries):
            try:
                resp = self.client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except Exception:
                if attempt == retries - 1:
                    raise
                time.sleep(0.5 * (attempt + 1))

