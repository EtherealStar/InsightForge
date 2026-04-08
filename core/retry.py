"""重试与降级工具"""
import functools
import time
import logging

logger = logging.getLogger(__name__)


def with_retry(
    max_retries: int = 3,
    backoff_base: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """指数退避重试装饰器"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        raise
                    wait = backoff_base ** attempt
                    logger.warning(
                        f"重试 {attempt + 1}/{max_retries} "
                        f"{func.__name__}: {e}, 等待 {wait:.1f}s"
                    )
                    time.sleep(wait)

        return wrapper

    return decorator
