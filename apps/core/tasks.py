import logging

logger = logging.getLogger(__name__)


def ping(message: str = "pong") -> str:
    """Smoke-test task: proves the worker picks up and runs queued jobs.

    Queue it with: django_q.tasks.async_task("apps.core.tasks.ping")
    """
    logger.info("ping task ran: %s", message)
    return message


def publish_scheduled():
    """Publish pages whose «go live» time has passed (CMS-2 scheduled publishing).

    Runs every minute via a Django-Q2 schedule (content migration 0004).
    """
    from django.core.management import call_command

    call_command("publish_scheduled")
