# request_model.py
from pydantic import BaseModel
from typing import List, Optional

class RequestModel(BaseModel):
    org_number: str
    criteria: str

class BatchRequestModel(BaseModel):
    org_numbers: List[str]
    criteria: str
    batch_size: Optional[int] = 5  # Process this many at a time