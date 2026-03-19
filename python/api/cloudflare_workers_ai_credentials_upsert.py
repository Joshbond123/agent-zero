from python.helpers.api import ApiHandler, Request, Response
from python.helpers.cloudflare_workers_ai import get_manager


class UpsertCloudflareWorkersAICredential(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        credential = get_manager().upsert_credential(input)
        return {"credential": credential.to_dict()}
