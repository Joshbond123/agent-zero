from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Optional

from python.helpers import files
from python.helpers.secrets import SecretsManager

LOGGER = logging.getLogger("agent_zero.cloudflare_workers_ai")
CREDENTIALS_FILE = files.get_abs_path("tmp/cloudflare_workers_ai_credentials.json")
DEFAULT_MODEL = "@cf/openai/gpt-oss-120b"
DEFAULT_ENABLED = False
COOLDOWN_SECONDS = 60
RECOVERY_CHECK_INTERVAL_SECONDS = 30
MAX_RETRY_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 8.0


@dataclass
class CloudflareCredential:
    id: str
    name: str
    account_id: str
    api_key_secret: str
    model_name: str
    enabled: bool = True
    status: str = "unknown"
    healthy: bool = True
    last_checked_at: float = 0.0
    last_success_at: float = 0.0
    last_failure_at: float = 0.0
    last_status_message: str = "Not checked yet"
    failure_count: int = 0
    cooldown_until: float = 0.0

    def to_dict(self, include_secret: bool = False) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "name": self.name,
            "account_id": self.account_id,
            "model_name": self.model_name,
            "enabled": self.enabled,
            "status": self.status,
            "healthy": self.healthy,
            "last_checked_at": self.last_checked_at,
            "last_success_at": self.last_success_at,
            "last_failure_at": self.last_failure_at,
            "last_status_message": self.last_status_message,
            "failure_count": self.failure_count,
            "cooldown_until": self.cooldown_until,
        }
        if include_secret:
            payload["api_key_secret"] = self.api_key_secret
        else:
            payload["masked_api_key"] = self.masked_api_key
        return payload

    @property
    def masked_api_key(self) -> str:
        return "••••••••" if self.api_key_secret else ""

    @property
    def secret_env_key(self) -> str:
        return self.api_key_secret

    @property
    def api_base(self) -> str:
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/v1/"

    def get_api_key(self) -> str:
        return SecretsManager.get_instance().load_secrets().get(self.secret_env_key, "")

    def is_available(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        if not self.enabled:
            return False
        if not self.healthy and now < self.cooldown_until:
            return False
        return True


class CloudflareWorkersAICredentialManager:
    def __init__(self, storage_path: str = CREDENTIALS_FILE):
        self.storage_path = Path(storage_path)
        self._lock = RLock()
        self._round_robin_index = 0

    def _read(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {"credentials": []}
        return json.loads(self.storage_path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_credentials(self) -> list[CloudflareCredential]:
        with self._lock:
            raw = self._read()
            return [CloudflareCredential(**item) for item in raw.get("credentials", [])]

    def save_credentials(self, credentials: list[CloudflareCredential]):
        with self._lock:
            self._write({"credentials": [cred.to_dict(include_secret=True) for cred in credentials]})

    def upsert_credential(self, payload: dict[str, Any]) -> CloudflareCredential:
        with self._lock:
            credentials = self.list_credentials()
            cred_id = payload.get("id") or f"cfwai_{uuid.uuid4().hex[:12]}"
            existing = next((cred for cred in credentials if cred.id == cred_id), None)
            secret_key = existing.api_key_secret if existing else f"CLOUDFLARE_WORKERS_AI_{cred_id.upper()}_API_KEY"
            api_key = (payload.get("api_key") or "").strip()
            if api_key and api_key != "••••••••":
                existing_secrets = SecretsManager.get_instance().read_secrets_raw()
                SecretsManager.get_instance().save_secrets_with_merge(
                    self._merge_secret(existing_secrets, secret_key, api_key)
                )
            elif not existing:
                raise ValueError("Cloudflare Workers AI API key is required for a new credential.")

            model_name = (payload.get("model_name") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
            credential = CloudflareCredential(
                id=cred_id,
                name=(payload.get("name") or f"Workers AI {cred_id[-4:]}").strip(),
                account_id=(payload.get("account_id") or "").strip(),
                api_key_secret=secret_key,
                model_name=model_name,
                enabled=bool(payload.get("enabled", True)),
                status=(existing.status if existing else "unknown"),
                healthy=(existing.healthy if existing else True),
                last_checked_at=(existing.last_checked_at if existing else 0.0),
                last_success_at=(existing.last_success_at if existing else 0.0),
                last_failure_at=(existing.last_failure_at if existing else 0.0),
                last_status_message=(existing.last_status_message if existing else "Not checked yet"),
                failure_count=(existing.failure_count if existing else 0),
                cooldown_until=(existing.cooldown_until if existing else 0.0),
            )
            if not credential.account_id:
                raise ValueError("Cloudflare Account ID is required.")

            credentials = [cred for cred in credentials if cred.id != cred_id]
            credentials.append(credential)
            self.save_credentials(credentials)
            return credential

    def delete_credential(self, cred_id: str):
        with self._lock:
            credentials = self.list_credentials()
            target = next((cred for cred in credentials if cred.id == cred_id), None)
            credentials = [cred for cred in credentials if cred.id != cred_id]
            self.save_credentials(credentials)
            if target:
                current = SecretsManager.get_instance().read_secrets_raw()
                updated_lines = []
                for line in current.splitlines():
                    if not line.startswith(f"{target.api_key_secret}="):
                        updated_lines.append(line)
                SecretsManager.get_instance().save_secrets("\n".join(updated_lines).strip() + ("\n" if updated_lines else ""))

    def get_credential(self, cred_id: str) -> Optional[CloudflareCredential]:
        return next((cred for cred in self.list_credentials() if cred.id == cred_id), None)

    def mark_result(self, cred_id: str, success: bool, message: str):
        with self._lock:
            credentials = self.list_credentials()
            now = time.time()
            updated: list[CloudflareCredential] = []
            for cred in credentials:
                if cred.id == cred_id:
                    cred.last_checked_at = now
                    cred.last_status_message = message
                    if success:
                        cred.status = "healthy"
                        cred.healthy = True
                        cred.last_success_at = now
                        cred.failure_count = 0
                        cred.cooldown_until = 0.0
                    else:
                        cred.status = "cooldown"
                        cred.healthy = False
                        cred.last_failure_at = now
                        cred.failure_count += 1
                        cooldown = min(COOLDOWN_SECONDS * (2 ** max(0, cred.failure_count - 1)), 15 * 60)
                        cred.cooldown_until = now + cooldown
                updated.append(cred)
            self.save_credentials(updated)

    def select_available_credentials(self) -> list[CloudflareCredential]:
        credentials = self.list_credentials()
        now = time.time()
        available = [cred for cred in credentials if cred.is_available(now)]
        recovering = [
            cred for cred in credentials
            if cred.enabled and not cred.healthy and now >= cred.cooldown_until
        ]
        return available + recovering

    def next_credential(self) -> Optional[CloudflareCredential]:
        with self._lock:
            candidates = self.select_available_credentials()
            if not candidates:
                return None
            index = self._round_robin_index % len(candidates)
            self._round_robin_index = (self._round_robin_index + 1) % max(len(candidates), 1)
            return candidates[index]

    def _merge_secret(self, existing_text: str, key: str, value: str) -> str:
        lines = existing_text.splitlines()
        replaced = False
        out: list[str] = []
        for line in lines:
            if line.startswith(f"{key}="):
                out.append(f"{key}={value}")
                replaced = True
            else:
                out.append(line)
        if not replaced:
            if out and out[-1].strip():
                out.append("")
            out.append(f"{key}={value}")
        return "\n".join(out).strip() + "\n"


class CloudflareWorkersAIRouter:
    def __init__(self, manager: Optional[CloudflareWorkersAICredentialManager] = None):
        self.manager = manager or CloudflareWorkersAICredentialManager()

    def build_request_kwargs(self, credential: CloudflareCredential) -> dict[str, Any]:
        api_key = credential.get_api_key()
        if not api_key:
            raise ValueError(f"Cloudflare Workers AI credential '{credential.name}' is missing an API key.")
        return {
            "api_key": api_key,
            "api_base": credential.api_base,
            "base_url": credential.api_base,
            "extra_headers": {},
        }

    async def test_credential(self, credential: CloudflareCredential, prompt: str = "Reply with OK") -> dict[str, Any]:
        import openai

        client = openai.AsyncOpenAI(api_key=credential.get_api_key(), base_url=credential.api_base)
        response = await client.chat.completions.create(
            model=credential.model_name,
            messages=[{"role": "user", "content": prompt}],
        )
        content = ""
        if response.choices:
            content = response.choices[0].message.content or ""
        return {"ok": True, "response": content}

    async def run_with_rotation(
        self,
        *,
        operation: Callable[[CloudflareCredential, dict[str, Any]], Any],
        on_retry: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> Any:
        errors: list[str] = []
        for attempt in range(MAX_RETRY_ATTEMPTS):
            credential = self.manager.next_credential()
            if credential is None:
                raise RuntimeError(
                    "No enabled Cloudflare Workers AI credentials are currently healthy enough to serve requests."
                )
            route_kwargs = self.build_request_kwargs(credential)
            try:
                LOGGER.info(
                    "workers_ai.route.selected",
                    extra={
                        "provider": "cloudflare_workers_ai",
                        "credential_id": credential.id,
                        "attempt": attempt + 1,
                        "model": credential.model_name,
                    },
                )
                result = operation(credential, route_kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                self.manager.mark_result(credential.id, True, "Healthy")
                return result
            except Exception as exc:
                message = str(exc)
                errors.append(f"{credential.name}: {message}")
                self.manager.mark_result(credential.id, False, message)
                if on_retry:
                    on_retry(
                        {
                            "credential_id": credential.id,
                            "attempt": attempt + 1,
                            "error": message,
                        }
                    )
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    delay = min(BACKOFF_BASE_SECONDS * (2 ** attempt) + random.random(), BACKOFF_MAX_SECONDS)
                    await asyncio.sleep(delay)
                    await self._recover_credentials_if_due()
        raise RuntimeError("Cloudflare Workers AI routing failed after retries: " + " | ".join(errors))


    def run_with_rotation_sync(
        self,
        *,
        operation: Callable[[CloudflareCredential, dict[str, Any]], Any],
        on_retry: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> Any:
        errors: list[str] = []
        for attempt in range(MAX_RETRY_ATTEMPTS):
            credential = self.manager.next_credential()
            if credential is None:
                raise RuntimeError(
                    "No enabled Cloudflare Workers AI credentials are currently healthy enough to serve requests."
                )
            route_kwargs = self.build_request_kwargs(credential)
            try:
                LOGGER.info(
                    "workers_ai.route.selected",
                    extra={
                        "provider": "cloudflare_workers_ai",
                        "credential_id": credential.id,
                        "attempt": attempt + 1,
                        "model": credential.model_name,
                    },
                )
                result = operation(credential, route_kwargs)
                self.manager.mark_result(credential.id, True, "Healthy")
                return result
            except Exception as exc:
                message = str(exc)
                errors.append(f"{credential.name}: {message}")
                self.manager.mark_result(credential.id, False, message)
                if on_retry:
                    on_retry({"credential_id": credential.id, "attempt": attempt + 1, "error": message})
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    delay = min(BACKOFF_BASE_SECONDS * (2 ** attempt) + random.random(), BACKOFF_MAX_SECONDS)
                    time.sleep(delay)
        raise RuntimeError("Cloudflare Workers AI routing failed after retries: " + " | ".join(errors))

    async def _recover_credentials_if_due(self):
        now = time.time()
        for credential in self.manager.list_credentials():
            if not credential.enabled or credential.healthy:
                continue
            if now < credential.cooldown_until:
                continue
            if credential.last_checked_at and now - credential.last_checked_at < RECOVERY_CHECK_INTERVAL_SECONDS:
                continue
            try:
                await self.test_credential(credential, prompt="Reply with HEALTHY")
                self.manager.mark_result(credential.id, True, "Recovered after health check")
            except Exception as exc:
                self.manager.mark_result(credential.id, False, f"Recovery check failed: {exc}")


_manager: Optional[CloudflareWorkersAICredentialManager] = None
_router: Optional[CloudflareWorkersAIRouter] = None


def get_manager() -> CloudflareWorkersAICredentialManager:
    global _manager
    if _manager is None:
        _manager = CloudflareWorkersAICredentialManager()
    return _manager


def get_router() -> CloudflareWorkersAIRouter:
    global _router
    if _router is None:
        _router = CloudflareWorkersAIRouter(get_manager())
    return _router
