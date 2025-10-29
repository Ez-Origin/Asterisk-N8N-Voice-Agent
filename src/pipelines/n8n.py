"""Adapter for n8n REST API integration."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

import aiohttp

from ..config import AppConfig
from ..logging_config import get_logger
from .base import LLMComponent

logger = get_logger(__name__)


class N8nAdapter(LLMComponent):
    """LLMComponent adapter for making calls to an n8n webhook."""

    def __init__(
        self,
        component_key: str,
        app_config: AppConfig,
        options: Optional[Dict[str, Any]] = None,
        *,
        session_factory: Optional[Callable[[], aiohttp.ClientSession]] = None,
    ):
        self.component_key = component_key
        self._app_config = app_config
        self._pipeline_defaults = dict(options or {})
        self._session_factory = session_factory
        self._session: Optional[aiohttp.ClientSession] = None

        # Extract n8n webhook URL from options
        self._webhook_url = self._pipeline_defaults.get("webhook_url")
        if not self._webhook_url:
            raise ValueError("n8n webhook_url must be configured in pipeline options")

    async def start(self) -> None:
        logger.debug(
            "n8n adapter initialized",
            component=self.component_key,
            webhook_url=self._webhook_url,
        )

    async def stop(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def generate(
        self,
        call_id: str,
        transcript: str,
        context: Dict[str, Any],
        options: Dict[str, Any],
    ) -> str:
        await self._ensure_session()
        assert self._session is not None

        # Merge options
        merged_options = self._pipeline_defaults.copy()
        merged_options.update(options)

        webhook_url = merged_options.get("webhook_url", self._webhook_url)
        timeout = float(merged_options.get("timeout_sec", 10.0))
        # The key in the response that holds the text to be spoken.
        response_json_key = merged_options.get("response_json_key", "response")

        payload = {
            "call_id": call_id,
            "transcript": transcript,
            "context": context,
        }

        logger.info(
            "Sending request to n8n webhook",
            call_id=call_id,
            url=webhook_url,
        )

        async with self._session.post(
            webhook_url,
            json=payload,
            timeout=timeout,
        ) as response:
            if response.status >= 400:
                body = await response.text()
                logger.error(
                    "n8n webhook request failed",
                    call_id=call_id,
                    status=response.status,
                    body_preview=body[:128],
                )
                response.raise_for_status()

            try:
                response_data = await response.json()
                response_text = response_data.get(response_json_key, "")
                if not response_text:
                     logger.warning(
                        "n8n response did not contain expected key or key was empty",
                        call_id=call_id,
                        response_json_key=response_json_key,
                        response_data=response_data,
                    )
                
                logger.info(
                    "n8n response received",
                    call_id=call_id,
                    preview=response_text[:80],
                )
                return response_text

            except (json.JSONDecodeError, aiohttp.ContentTypeError):
                text_response = await response.text()
                logger.info(
                    "n8n returned non-JSON response, returning as plain text",
                    call_id=call_id,
                    preview=text_response[:80],
                )
                return text_response


    async def _ensure_session(self) -> None:
        if self._session and not self._session.closed:
            return
        factory = self._session_factory or aiohttp.ClientSession
        self._session = factory()

__all__ = ["N8nAdapter"]