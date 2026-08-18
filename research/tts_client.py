"""Minimal REST wrapper around Gemini's text-to-speech generateContent endpoint. Mirrors
gemini_client.py's contract exactly: any failure (missing key, network error, bad/empty response)
returns None after a bounded number of immediate retries so callers can record FAILED instead of
crashing the pipeline. No google-genai SDK is installed in this project (see 12's plan notes) --
this hits the same public REST surface the SDK itself calls, confirmed live as of 2026:
generateContent with generationConfig.responseModalities=["AUDIO"] and
generationConfig.speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName, returning base64 PCM at
candidates[0].content.parts[0].inlineData.{data,mimeType}.
"""
from __future__ import annotations

import base64
import logging

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://generativelanguage.googleapis.com/v1beta"

_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


class GeminiTTSClient:
    def __init__(
        self, api_key: str | None, model: str = "gemini-3.1-flash-tts-preview",
        timeout_seconds: int = 30, max_retries: int = 3,
    ):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._max_retries = max_retries

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    @property
    def model(self) -> str:
        return self._model

    def synthesize(self, prompt: str, voice_name: str) -> dict | None:
        """Returns {"audio_base64": ..., "mime_type": ..., "attempts": N} on success, or None if
        every attempt failed. `attempts` lets the caller aggregate api_calls/retry_count without
        this client needing to know anything about asset_generation_runs."""
        if not self._api_key:
            return None
        url = f"{API_BASE}/models/{self._model}:generateContent?key={self._api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}},
            },
        }

        attempts = 0
        last_error: Exception | None = None
        while attempts < max(1, self._max_retries):
            attempts += 1
            try:
                resp = requests.post(url, json=payload, timeout=self._timeout)
                if resp.status_code in _RETRYABLE_STATUS_CODES:
                    last_error = RuntimeError(f"retryable status {resp.status_code}")
                    continue
                resp.raise_for_status()
                data = resp.json()
                part = data["candidates"][0]["content"]["parts"][0]
                inline = part.get("inlineData") or part.get("inline_data")
                audio_b64 = inline["data"] if inline else None
                if not audio_b64:
                    last_error = RuntimeError("empty audio response")
                    continue
                # Validate it actually decodes -- an empty/garbage inlineData.data should be
                # treated as a retryable empty response, not silently handed to the caller.
                base64.b64decode(audio_b64, validate=True)
                return {
                    "audio_base64": audio_b64,
                    "mime_type": inline.get("mimeType") or inline.get("mime_type"),
                    "attempts": attempts,
                }
            except Exception as e:  # noqa: BLE001 - any failure retries, then falls through to None
                last_error = e
                continue

        logger.warning("Gemini TTS call failed after %d attempt(s): %s", attempts, last_error)
        return None
