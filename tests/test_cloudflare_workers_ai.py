import os
import sys
import types

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "dotenv" not in sys.modules:
    dotenv_mod = types.ModuleType("dotenv")
    parser_mod = types.ModuleType("dotenv.parser")
    parser_mod.parse_stream = lambda stream: []
    dotenv_mod.parser = parser_mod
    sys.modules["dotenv"] = dotenv_mod
    sys.modules["dotenv.parser"] = parser_mod

import asyncio
import json
from pathlib import Path

from python.helpers.cloudflare_workers_ai import (
    CloudflareCredential,
    CloudflareWorkersAICredentialManager,
    CloudflareWorkersAIRouter,
)


def test_round_robin_rotation(tmp_path):
    storage = tmp_path / "cfwai.json"
    manager = CloudflareWorkersAICredentialManager(str(storage))
    manager.save_credentials([
        CloudflareCredential(id="a", name="A", account_id="acc-a", api_key_secret="A_KEY", model_name="m1"),
        CloudflareCredential(id="b", name="B", account_id="acc-b", api_key_secret="B_KEY", model_name="m1"),
    ])

    picks = [manager.next_credential().id for _ in range(4)]
    assert picks == ["a", "b", "a", "b"]


def test_failed_credential_enters_cooldown(tmp_path):
    storage = tmp_path / "cfwai.json"
    manager = CloudflareWorkersAICredentialManager(str(storage))
    manager.save_credentials([
        CloudflareCredential(id="a", name="A", account_id="acc-a", api_key_secret="A_KEY", model_name="m1"),
        CloudflareCredential(id="b", name="B", account_id="acc-b", api_key_secret="B_KEY", model_name="m1"),
    ])

    manager.mark_result("a", False, "boom")
    picks = [manager.next_credential().id for _ in range(3)]
    assert picks == ["b", "b", "b"]


def test_router_retries_next_credential(monkeypatch, tmp_path):
    storage = tmp_path / "cfwai.json"
    manager = CloudflareWorkersAICredentialManager(str(storage))
    manager.save_credentials([
        CloudflareCredential(id="a", name="A", account_id="acc-a", api_key_secret="A_KEY", model_name="m1"),
        CloudflareCredential(id="b", name="B", account_id="acc-b", api_key_secret="B_KEY", model_name="m1"),
    ])
    router = CloudflareWorkersAIRouter(manager)

    monkeypatch.setattr(CloudflareCredential, "get_api_key", lambda self: f"token-{self.id}")

    seen = []

    async def run():
        async def op(credential, route_kwargs):
            seen.append((credential.id, route_kwargs["api_base"]))
            if credential.id == "a":
                raise RuntimeError("simulated failure")
            return credential.id

        return await router.run_with_rotation(operation=op)

    result = asyncio.run(run())
    assert result == "b"
    assert [item[0] for item in seen] == ["a", "b"]
    saved = json.loads(Path(storage).read_text())
    statuses = {item["id"]: item["healthy"] for item in saved["credentials"]}
    assert statuses == {"a": False, "b": True}


def test_route_kwargs_uses_credential_model(monkeypatch, tmp_path):
    storage = tmp_path / "cfwai.json"
    manager = CloudflareWorkersAICredentialManager(str(storage))
    manager.save_credentials([
        CloudflareCredential(id="a", name="A", account_id="acc-a", api_key_secret="A_KEY", model_name="@cf/meta/llama-3.3"),
    ])
    router = CloudflareWorkersAIRouter(manager)
    monkeypatch.setattr(CloudflareCredential, "get_api_key", lambda self: "token-a")

    cred = manager.next_credential()
    kwargs = router.build_request_kwargs(cred)
    assert kwargs["model"] == "openai/@cf/meta/llama-3.3"
    assert kwargs["api_base"].endswith("/accounts/acc-a/ai/v1/")


def test_usage_counters_update(tmp_path):
    storage = tmp_path / "cfwai.json"
    manager = CloudflareWorkersAICredentialManager(str(storage))
    manager.save_credentials([
        CloudflareCredential(id="a", name="A", account_id="acc-a", api_key_secret="A_KEY", model_name="m1"),
    ])
    manager.mark_result("a", True, "ok")
    manager.mark_result("a", False, "fail")
    cred = manager.get_credential("a")
    assert cred.request_count == 2
    assert cred.success_count == 1
    assert cred.error_count == 1
    assert cred.last_used_at > 0
