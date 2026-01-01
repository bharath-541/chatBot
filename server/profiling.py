from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ProfilingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Start timing
        start_time = time.time()
        start_datetime = datetime.now()
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        duration_ms = duration * 1000
        
        # Log profiling data
        logger.info(f"""
        ===== REQUEST PROFILE =====
        Path: {request.method} {request.url.path}
        Duration: {duration_ms:.2f}ms
        Status: {response.status_code}
        Timestamp: {start_datetime.isoformat()}
        ===========================
        """)
        
        # Track performance metrics
        performance_tracker.add_request(
            request.url.path,
            request.method,
            duration,
            response.status_code
        )
        
        # Add custom header with timing
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"
        
        return response

class PerformanceTracker:
    def __init__(self):
        self.requests = []
    
    def add_request(self, path: str, method: str, duration: float, status: int):
        self.requests.append({
            "path": path,
            "method": method,
            "duration_ms": duration * 1000,
            "status": status,
            "timestamp": datetime.now()
        })
    
    def get_stats(self):
        if not self.requests:
            return {
                "total_requests": 0,
                "avg_duration_ms": 0,
                "p95_duration_ms": 0,
                "p99_duration_ms": 0
            }
        
        durations = sorted([r["duration_ms"] for r in self.requests])
        total = len(durations)
        
        return {
            "total_requests": total,
            "avg_duration_ms": sum(durations) / total,
            "p95_duration_ms": durations[int(total * 0.95)] if total > 0 else 0,
            "p99_duration_ms": durations[int(total * 0.99)] if total > 0 else 0,
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations)
        }

# Global tracker
performance_tracker = PerformanceTracker()
