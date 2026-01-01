from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import logging
from datetime import datetime

from config import get_settings
from database import init_db, get_session_maker
from db_service import DatabaseService
from tools import HospitalSearchTool, ToolRegistry
from agent import ChatAgent
from background_tasks import BackgroundTaskManager
from profiling import ProfilingMiddleware, performance_tracker
from schemas import (
    ChatRequest, ChatResponse, UserProfile, UserProfileUpdate,
    ConversationsResponse, ConversationItem, HospitalSearchRequest,
    BackgroundTaskRequest, BackgroundTaskResponse, LongTermMemory, MemoryResponse,
    SessionItem, SessionsResponse
)

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
agent = None
task_manager = None
SessionMaker = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global agent, task_manager, SessionMaker
    
    # Startup
    settings = get_settings()
    logger.info("Initializing database...")
    engine = init_db(settings.database_url)
    SessionMaker = get_session_maker(engine)
    
    # Initialize tools
    logger.info("Initializing tools...")
    tool_registry = ToolRegistry()
    hospital_tool = HospitalSearchTool(api_key=settings.google_maps_api_key)
    tool_registry.register(hospital_tool)
    
    # Initialize agent
    logger.info("Initializing chat agent...")
    db_service = DatabaseService(SessionMaker())
    agent = ChatAgent(settings.google_api_key, db_service, tool_registry)
    
    # Initialize background task manager
    logger.info("Initializing background task manager...")
    task_manager = BackgroundTaskManager(db_service)
    
    logger.info("Server startup complete!")
    
    yield
    
    # Shutdown
    if task_manager:
        task_manager.shutdown()
    logger.info("Server shutdown complete")

app = FastAPI(title="Gemini + Langraph Chatbot", lifespan=lifespan)

# Add profiling middleware
app.add_middleware(ProfilingMiddleware)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get DB session
def get_db():
    session = SessionMaker()
    try:
        yield DatabaseService(session)
    finally:
        session.close()

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "chatbot-api",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: DatabaseService = Depends(get_db)):
    """Main chat endpoint powered by Gemini + Langraph"""
    try:
        response = await agent.chat(request.message, request.session_id)
        return ChatResponse(
            response=response,
            session_id=request.session_id,
            timestamp=datetime.now()
        )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversations/{session_id}", response_model=ConversationsResponse)
async def get_conversations(session_id: str, db: DatabaseService = Depends(get_db)):
    """Get all conversations for a session"""
    conversations = db.get_all_conversations(session_id)
    return ConversationsResponse(
        session_id=session_id,
        conversations=[
            ConversationItem(
                role=conv.role,
                content=conv.content,
                timestamp=conv.timestamp
            )
            for conv in conversations
        ],
        count=len(conversations)
    )

@app.get("/user/profile/{session_id}", response_model=UserProfile)
async def get_user_profile(session_id: str, db: DatabaseService = Depends(get_db)):
    """Get user profile"""
    user = db.get_or_create_user(session_id)
    return UserProfile(
        session_id=session_id,
        name=user.name,
        email=user.email
    )

@app.put("/user/profile/{session_id}", response_model=UserProfile)
async def update_user_profile(
    session_id: str,
    profile: UserProfileUpdate,
    db: DatabaseService = Depends(get_db)
):
    """Update user profile"""
    user = db.update_user_profile(session_id, profile.name, profile.email)
    return UserProfile(
        session_id=session_id,
        name=user.name,
        email=user.email
    )

@app.get("/user/memory/{session_id}", response_model=MemoryResponse)
async def get_user_memory(session_id: str, db: DatabaseService = Depends(get_db)):
    """Get user's long-term memory"""
    memories = db.get_all_long_term_memories(session_id)
    return MemoryResponse(
        session_id=session_id,
        memories=memories
    )

@app.post("/user/memory/{session_id}")
async def set_user_memory(
    session_id: str,
    memory: LongTermMemory,
    db: DatabaseService = Depends(get_db)
):
    """Set a long-term memory for user"""
    db.set_long_term_memory(session_id, memory.key, memory.value)
    return {"status": "success", "key": memory.key}

@app.post("/tools/hospitals")
async def search_hospitals(request: HospitalSearchRequest):
    """Search for nearby hospitals"""
    settings = get_settings()
    tool = HospitalSearchTool(api_key=settings.google_maps_api_key)
    result = await tool.execute(
        latitude=request.latitude,
        longitude=request.longitude,
        place=request.place,
        radius=request.radius
    )
    return result

@app.post("/tasks/schedule", response_model=BackgroundTaskResponse)
async def schedule_background_task(request: BackgroundTaskRequest):
    """Schedule a background task"""
    task_id = task_manager.schedule_task(
        request.session_id,
        request.task_type,
        request.description
    )
    task = task_manager.get_task_status(task_id)
    return BackgroundTaskResponse(
        task_id=task.task_id,
        status=task.status,
        description=task.description,
        created_at=task.created_at
    )

@app.get("/tasks/status/{task_id}")
async def get_task_status(task_id: str):
    """Get status of a background task"""
    task = task_manager.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "task_id": task.task_id,
        "status": task.status,
        "description": task.description,
        "result": task.result,
        "created_at": task.created_at,
        "completed_at": task.completed_at
    }

@app.get("/sessions", response_model=SessionsResponse)
async def get_all_sessions(db: DatabaseService = Depends(get_db)):
    """Get all sessions with metadata"""
    sessions = db.get_all_sessions()
    return SessionsResponse(
        sessions=[
            SessionItem(
                session_id=s["session_id"],
                name=s["name"],
                created_at=s["created_at"],
                message_count=s["message_count"]
            )
            for s in sessions
        ],
        count=len(sessions)
    )

@app.get("/metrics/performance")
async def get_performance_metrics():
    """Get performance metrics"""
    return performance_tracker.get_stats()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)
