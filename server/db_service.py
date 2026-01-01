from sqlalchemy.orm import Session
from database import User, Conversation, EpisodicMemory, LongTermMemory, BackgroundTask
from datetime import datetime
from typing import List, Optional, Dict

class DatabaseService:
    def __init__(self, session: Session):
        self.session = session
    
    # User operations
    def get_or_create_user(self, session_id: str) -> User:
        user = self.session.query(User).filter(User.session_id == session_id).first()
        if not user:
            user = User(session_id=session_id)
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)
        return user
    
    def update_user_profile(self, session_id: str, name: Optional[str] = None, email: Optional[str] = None) -> User:
        user = self.get_or_create_user(session_id)
        if name:
            user.name = name
        if email:
            user.email = email
        self.session.commit()
        self.session.refresh(user)
        return user
    
    # Conversation operations (Short-term memory)
    def add_conversation(self, session_id: str, role: str, content: str) -> Conversation:
        user = self.get_or_create_user(session_id)
        conversation = Conversation(user_id=user.id, role=role, content=content)
        self.session.add(conversation)
        self.session.commit()
        return conversation
    
    def get_recent_conversations(self, session_id: str, limit: int = 10) -> List[Conversation]:
        user = self.get_or_create_user(session_id)
        return self.session.query(Conversation)\
            .filter(Conversation.user_id == user.id)\
            .order_by(Conversation.timestamp.desc())\
            .limit(limit)\
            .all()
    
    def get_all_conversations(self, session_id: str) -> List[Conversation]:
        user = self.get_or_create_user(session_id)
        return self.session.query(Conversation)\
            .filter(Conversation.user_id == user.id)\
            .order_by(Conversation.timestamp.desc())\
            .all()
    
    # Episodic memory operations
    def create_episodic_memory(self, session_id: str, summary: str, message_count: int):
        user = self.get_or_create_user(session_id)
        episodic = EpisodicMemory(user_id=user.id, summary=summary, message_count=message_count)
        self.session.add(episodic)
        self.session.commit()
        return episodic
    
    def get_episodic_memories(self, session_id: str, limit: int = 5) -> List[EpisodicMemory]:
        user = self.get_or_create_user(session_id)
        return self.session.query(EpisodicMemory)\
            .filter(EpisodicMemory.user_id == user.id)\
            .order_by(EpisodicMemory.created_at.desc())\
            .limit(limit)\
            .all()
    
    # Long-term memory operations
    def set_long_term_memory(self, session_id: str, key: str, value: str):
        user = self.get_or_create_user(session_id)
        memory = self.session.query(LongTermMemory)\
            .filter(LongTermMemory.user_id == user.id, LongTermMemory.key == key)\
            .first()
        
        if memory:
            memory.value = value
            memory.updated_at = datetime.utcnow()
        else:
            memory = LongTermMemory(user_id=user.id, key=key, value=value)
            self.session.add(memory)
        
        self.session.commit()
        return memory
    
    def get_long_term_memory(self, session_id: str, key: str) -> Optional[str]:
        user = self.get_or_create_user(session_id)
        memory = self.session.query(LongTermMemory)\
            .filter(LongTermMemory.user_id == user.id, LongTermMemory.key == key)\
            .first()
        return memory.value if memory else None
    
    def get_all_long_term_memories(self, session_id: str) -> Dict[str, str]:
        user = self.get_or_create_user(session_id)
        memories = self.session.query(LongTermMemory)\
            .filter(LongTermMemory.user_id == user.id)\
            .all()
        return {m.key: m.value for m in memories}
    
    # Background task operations
    def create_background_task(self, session_id: str, task_id: str, task_type: str, description: str) -> BackgroundTask:
        user = self.get_or_create_user(session_id)
        task = BackgroundTask(
            task_id=task_id,
            user_id=user.id,
            task_type=task_type,
            description=description
        )
        self.session.add(task)
        self.session.commit()
        return task
    
    def update_task_status(self, task_id: str, status: str, result: Optional[str] = None):
        task = self.session.query(BackgroundTask).filter(BackgroundTask.task_id == task_id).first()
        if task:
            task.status = status
            if result:
                task.result = result
            if status == "completed" or status == "failed":
                task.completed_at = datetime.utcnow()
            self.session.commit()
        return task
    
    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        return self.session.query(BackgroundTask).filter(BackgroundTask.task_id == task_id).first()
    
    # Session management operations
    def get_all_sessions(self) -> List[Dict]:
        """Get all sessions with metadata (conversation count, created_at, etc.)"""
        from sqlalchemy import func
        
        sessions = self.session.query(
            User.session_id,
            User.name,
            User.created_at,
            func.count(Conversation.id).label('message_count')
        ).outerjoin(Conversation).group_by(User.id).order_by(User.created_at.desc()).all()
        
        return [
            {
                "session_id": s.session_id,
                "name": s.name,
                "created_at": s.created_at,
                "message_count": s.message_count
            }
            for s in sessions
        ]
