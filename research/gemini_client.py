"""Minimal REST wrapper around the Gemini Generative Language API. Any failure (missing key,
API not enabled, network error, bad response) returns None so callers can fall back to
rule-based logic instead of breaking the pipeline."""
from __future__ import annotations

import json
import logging

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiClient:
    def __init__(self, api_key: str | None, model: str = "gemini-flash-latest", timeout_seconds: int = 30):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def generate_json(self, prompt: str, max_output_tokens: int = 1024) -> dict | None:
        """Sends a prompt asking for a JSON response and parses it. Returns None on any failure."""
        if not self._api_key:
            return None
        url = f"{API_BASE}/models/{self._model}:generateContent?key={self._api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
            },
        }
        try:
            resp = requests.post(url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except Exception as e:  # noqa: BLE001 - any failure here must not crash the pipeline
            logger.warning("Gemini call failed, falling back to rule-based logic: %s", e)
            return None
