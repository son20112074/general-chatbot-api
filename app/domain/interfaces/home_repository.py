# from abc import ABC, abstractmethod
# from typing import List, Optional


# class HomeRepository(ABC):
#     @abstractmethod
#     async def create(self, object: Home) -> Home:
#         pass
    
#     @abstractmethod
#     async def get_by_id(self, object_id: str) -> Optional[Home]:
#         pass
    
#     @abstractmethod
#     async def get_all(self, object_id: str = None) -> List[Home]:
#         pass
    
#     @abstractmethod
#     async def update(self, object: str, object_data: Home) -> Home:
#         pass
    
#     @abstractmethod
#     async def delete(self, object_id: str) -> bool:
#         pass
    
#     @abstractmethod
#     async def get_by_type(self, object_type: str) -> List[Home]:
#         pass