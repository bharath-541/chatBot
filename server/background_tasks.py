from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
from db_service import DatabaseService
import logging
import uuid

logger = logging.getLogger(__name__)

class BackgroundTaskManager:
    def __init__(self, db_service: DatabaseService):
        self.scheduler = BackgroundScheduler()
        self.db_service = db_service
        self.scheduler.start()
        logger.info("Background task scheduler started")
    
    def schedule_task(self, session_id: str, task_type: str, description: str, delay_seconds: int = 10) -> str:
        """Schedule a background task"""
        task_id = str(uuid.uuid4())
        
        # Create task in database
        self.db_service.create_background_task(session_id, task_id, task_type, description)
        
        # Schedule execution
        run_time = datetime.now() + timedelta(seconds=delay_seconds)
        self.scheduler.add_job(
            self._execute_task,
            trigger=DateTrigger(run_date=run_time),
            args=[task_id, task_type, description],
            id=task_id
        )
        
        logger.info(f"Scheduled task {task_id} to run at {run_time}")
        return task_id
    
    def _execute_task(self, task_id: str, task_type: str, description: str):
        """Execute the background task"""
        logger.info(f"Executing background task: {task_id}")
        
        try:
            # Update status to running
            self.db_service.update_task_status(task_id, "running")
            
            # Simulate task execution
            if task_type == "research":
                result = f"Completed research on: {description}"
            elif task_type == "analysis":
                result = f"Completed analysis of: {description}"
            else:
                result = f"Completed task: {description}"
            
            # Update status to completed
            self.db_service.update_task_status(task_id, "completed", result)
            
            # Send notification
            self._send_notification(task_id, result)
            
            logger.info(f"Task {task_id} completed successfully")
        
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self.db_service.update_task_status(task_id, "failed", str(e))
    
    def _send_notification(self, task_id: str, result: str):
        """Send notification (mocked to console)"""
        logger.info(f"""
        ================================
        NOTIFICATION: Task Completed
        ================================
        Task ID: {task_id}
        Status: Completed
        Result: {result}
        Time: {datetime.now()}
        ================================
        """)
    
    def get_task_status(self, task_id: str):
        """Get status of a background task"""
        return self.db_service.get_task(task_id)
    
    def shutdown(self):
        """Shutdown the scheduler"""
        self.scheduler.shutdown()
        logger.info("Background task scheduler shut down")
