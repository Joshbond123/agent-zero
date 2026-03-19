from python.helpers.api import ApiHandler, Request, Response
from python.helpers.cloudflare_workers_ai import get_manager


class DeleteCloudflareWorkersAICredential(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        cred_id = str(input.get("id", "")).strip()
        if not cred_id:
            raise ValueError("Credential id is required.")
        get_manager().delete_credential(cred_id)
        return {"deleted": True, "id": cred_id}
