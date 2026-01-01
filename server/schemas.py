from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class ChatRequest(BaseModel):
    message: str
    session_id: str

class ChatResponse(BaseModel):
    response: str
    session_id: str
    timestamp: datetime

class UserProfile(BaseModel):
    session_id: str
    name: Optional[str] = None
    email: Optional[str] = None

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None

class ConversationItem(BaseModel):
    role: str
    content: str
    timestamp: datetime

class ConversationsResponse(BaseModel):
    session_id: str
    conversations: List[ConversationItem]
    count: int

class HospitalSearchRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    place: Optional[str] = None
    radius: int = 5000

class BackgroundTaskRequest(BaseModel):
    task_type: str
    description: str
    session_id: str

class BackgroundTaskResponse(BaseModel):
    task_id: str
    status: str
    description: str
    created_at: datetime

class LongTermMemory(BaseModel):
    key: str
    value: str

class MemoryResponse(BaseModel):
    session_id: str
    memories: Dict[str, str]

class SessionItem(BaseModel):
    session_id: str
    name: Optional[str] = None
    created_at: datetime
    message_count: int

class SessionsResponse(BaseModel):
    sessions: List[SessionItem]
    count: int

