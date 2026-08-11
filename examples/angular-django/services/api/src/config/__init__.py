# Make the Celery app available whenever Django starts, so shared_task
# decorators (and anything else importing `config.celery_app`) work.
from .celery import app as celery_app

__all__ = ('celery_app',)
