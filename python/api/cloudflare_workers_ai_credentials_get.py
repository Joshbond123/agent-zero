from python.helpers.api import ApiHandler, Request, Response
from python.helpers.cloudflare_workers_ai import get_manager


class GetCloudflareWorkersAICredentials(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict | Response:
        credentials = [cred.to_dict() for cred in get_manager().list_credentials()]
        return {"credentials": credentials}

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]
