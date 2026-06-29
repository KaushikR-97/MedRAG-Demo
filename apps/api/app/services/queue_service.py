from redis import Redis
from rq import Queue

from app.core.config import settings


class QueueService:
    def __init__(self, name: str = "medrag") -> None:
        try:
            self.redis = Redis.from_url(settings.redis_url)
            self.queue = Queue(name, connection=self.redis)
        except Exception:
            self.redis = None
            self.queue = None

    def enqueue(self, func, *args, **kwargs) -> str:
        if settings.is_non_prod or self.queue is None:
            import threading
            t = threading.Thread(target=func, args=args, kwargs=kwargs)
            t.start()
            return f"local-thread-{t.ident}"
        job = self.queue.enqueue(func, *args, **kwargs)
        return job.id
