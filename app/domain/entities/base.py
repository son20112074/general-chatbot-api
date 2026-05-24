from typing import Any, Dict

class BaseEntity:
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

    def from_dict(self, data: Dict[str, Any]) -> None:
        for key, value in data.items():
            setattr(self, key, value)