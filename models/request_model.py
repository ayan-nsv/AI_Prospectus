# request_model.py
from pydantic import BaseModel
from typing import List, Optional

class RequestModel(BaseModel):
    org_number: str
    criteria: str

class BatchRequestModel(BaseModel):
    org_numbers: List[str]
    criteria: Optional[str] = None
    batch_id: Optional[str] = None
    batch_size: Optional[int] = 20  # Process this many at a time (increased for better performance)