from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class BaseModel:

    
    def to_dict(self) -> Dict[str, Any]:
        result = {}
        for key, value in self.__dict__.items():
            if value is not None:
                result[key] = value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        # Filter out keys that don't exist in the model
        if hasattr(cls, '__dataclass_fields__'):
            valid_keys = {field_name for field_name in cls.__dataclass_fields__.keys()}
            filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        else:
            filtered_data = data
        return cls(**filtered_data)
