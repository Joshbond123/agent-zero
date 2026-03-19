from python.helpers.extension import Extension
from agent import LoopData
from python.helpers import memory, settings


class MemoryInit(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        set = settings.get_settings()
        if not set["memory_recall_enabled"] and not set["memory_memorize_enabled"]:
            return
        await memory.Memory.get(self.agent)
