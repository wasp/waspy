from abc import ABC, abstractmethod
from typing import Dict


class TransportListenerABC(ABC):

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def handle_work(self, data: Dict, **kwargs) -> None:
        pass
