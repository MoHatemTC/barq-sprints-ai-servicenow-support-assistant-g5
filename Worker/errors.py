class RetryableError(Exception):
    """
    Error that represents a temporary failure.

    Celery should retry the task when this error occurs.
    """
    pass


class PermanentError(Exception):
    """
    Error that represents a permanent failure.

    The task should not be retried and should go directly
    to the Dead-Letter Queue.
    """
    pass