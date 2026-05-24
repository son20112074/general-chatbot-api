from abc import ABC, abstractmethod
from typing import Any, Dict


class ProxyRequestRepository(ABC):
    @abstractmethod
    def create_request(self, request_data: Dict[str, Any]) -> Any:
        pass

    @abstractmethod
    def get_request(self, request_id: str) -> Any:
        pass

    @abstractmethod
    def update_request(self, request_id: str, request_data: Dict[str, Any]) -> Any:
        pass

    @abstractmethod
    def delete_request(self, request_id: str) -> None:
        pass


class CacheRepositoryInterface(ABC):
    @abstractmethod
    def get(self, key: str) -> Any:
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int) -> None:
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        pass