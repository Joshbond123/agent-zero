from python.helpers.api import ApiHandler, Request, Response
from python.helpers.cloudflare_workers_ai import get_manager, get_router


class TestCloudflareWorkersAICredential(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        cred_id = str(input.get("id", "")).strip()
        if not cred_id:
            raise ValueError("Credential id is required.")
        credential = get_manager().get_credential(cred_id)
        if not credential:
            raise ValueError("Credential not found.")
        result = await get_router().test_credential(credential)
        get_manager().mark_result(credential.id, True, "Manual test succeeded")
        return {"success": True, "result": result, "credential": get_manager().get_credential(cred_id).to_dict()}
