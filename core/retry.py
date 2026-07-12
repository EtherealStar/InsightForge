"""重试与降级工具"""
import functools
import asyncio
import inspect
import time
import structlog

logger = structlog.get_logger(__name__)


def with_retry(
    max_retries: int = 3,
    backoff_base: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """指数退避重试装饰器"""

    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        if attempt == max_retries:
                            raise
                        wait = backoff_base ** attempt
                        logger.warning(
                            "异步调用重试",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            function=func.__name__,
                            error=str(e),
                            wait_seconds=wait,
                        )
                        await asyncio.sleep(wait)
            return async_wrapper

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
