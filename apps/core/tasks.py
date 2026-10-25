import logging

logger = logging.getLogger(__name__)


def ping(message: str = "pong") -> str:
    """Smoke-test task: proves the worker picks up and runs queued jobs.

    Queue it with: django_q.tasks.async_task("apps.core.tasks.ping")
    """
    logger.info("ping task ran: %s", message)
    return message
