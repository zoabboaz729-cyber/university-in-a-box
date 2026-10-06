"""Real OpenAI-compatible provider adapter (Phase 1 + Phase 13).

Speaks /chat/completions against AI_BASE_URL with AI_MODEL + AI_API_KEY.
Default .env points at OpenRouter with a :free model; any OpenAI-compatible
endpoint works by changing the same four vars. No provider SDK dependency.
"""
import asyncio
from dataclasses import dataclass

import httpx

from app.ai.config import AIConfig, load_config
from app.ai.quota import QuotaExceeded, resolve_ai_key_for_user
from app.monitor import get_logger


class ProviderError(Exception):
    """Raised when the LLM call fails twice or config is missing.

    Shown to the user as a clear error — never silently corrupts data.
    """


async def call_provider_async(provider, system_prompt: str, user_message: str) -> str:
    """Compatibility helper: async routes can call either async-capable or legacy sync providers."""
    if hasattr(provider, "agenerate") and callable(provider.agenerate):
        return await provider.agenerate(system_prompt, user_message)
    if hasattr(provider, "generate") and callable(provider.generate):
        return await asyncio.to_thread(provider.generate, system_prompt, user_message)
    raise ProviderError("AI provider does not support generate() or agenerate().")


@dataclass
class OpenAICompatibleProvider:
    config: AIConfig
    timeout_seconds: float = 60.0
    user: dict | None = None

    @property
    def name(self) -> str:
        return self.config.provider or "openai_compatible"

    def _resolved_config(self) -> tuple[str, str]:
        """Resolve the effective API key for the active user.

        This preserves the legacy default provider behavior for tests while
        enabling the Phase 13 BYOK + quota flow when a user object is supplied.
        """
        if self.user is not None:
            key, source = resolve_ai_key_for_user(self.user)
            if source == "byok" and key:
                return key, source
            if key:
                return key, source
        return (self.config.api_key or "").strip(), "config"

    def _post(self, system_prompt: str, user_message: str, api_key: str | None = None) -> str:
        effective_key = (api_key or self._resolved_config()[0]).strip()
        if not effective_key:
            raise ProviderError(
                "AI_API_KEY is not set. Copy .env.example to .env and paste "
                "your key (see README)."
            )
        if not self.config.base_url or not self.config.model:
            raise ProviderError(
                "AI_BASE_URL / AI_MODEL are not set. Check your .env file."
            )
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": "Bearer " + effective_key,
            "Content-Type": "application/json",
            # OpenRouter recommendations; harmless for other endpoints.
            "HTTP-Referer": "http://127.0.0.1:8000",
            "X-Title": "University in a Box",
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        try:
            response = httpx.post(
                url, json=payload, headers=headers, timeout=self.timeout_seconds
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.text[:300]
            except Exception:
                detail = ""
            raise ProviderError(
                "LLM request failed: " + str(exc) + " | API says: " + detail
            ) from exc
        except Exception as exc:
            raise ProviderError("LLM request failed: " + str(exc)) from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("LLM response was malformed: " + repr(data)) from exc
        if not content or not content.strip():
            raise ProviderError("LLM response was empty.")
        return content.strip()

    async def _apost(self, system_prompt: str, user_message: str, api_key: str | None = None) -> str:
        effective_key = (api_key or self._resolved_config()[0]).strip()
        if not effective_key:
            raise ProviderError(
                "AI_API_KEY is not set. Copy .env.example to .env and paste "
                "your key (see README)."
            )
        if not self.config.base_url or not self.config.model:
            raise ProviderError(
                "AI_BASE_URL / AI_MODEL are not set. Check your .env file."
            )
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": "Bearer " + effective_key,
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:8000",
            "X-Title": "University in a Box",
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.text[:300]
            except Exception:
                detail = ""
            raise ProviderError(
                "LLM request failed: " + str(exc) + " | API says: " + detail
            ) from exc
        except Exception as exc:
            raise ProviderError("LLM request failed: " + str(exc)) from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("LLM response was malformed: " + repr(data)) from exc
        if not content or not content.strip():
            raise ProviderError("LLM response was empty.")
        return content.strip()

    def generate(self, system_prompt: str, user_message: str) -> str:
        """One LLM call with exactly one retry, then a clear error.

        A failure after both attempts is written to data/app.log
        (docs/06-MONITORING, section A) before it propagates to the
        route, which renders it for the user.
        """
        try:
            return self._post(system_prompt, user_message)
        except ProviderError:
            try:
                return self._post(system_prompt, user_message)
            except ProviderError as final:
                get_logger().warning("LLM call failed after one retry: %s", final)
                raise

    async def agenerate(self, system_prompt: str, user_message: str) -> str:
        """Async variant of the LLM call, preserving the same retry semantics."""
        try:
            return await self._apost(system_prompt, user_message)
        except ProviderError:
            try:
                return await self._apost(system_prompt, user_message)
            except ProviderError as final:
                get_logger().warning("LLM call failed after one retry: %s", final)
                raise


def get_provider(user: dict | None = None) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(load_config(), user=user)
