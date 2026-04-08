"""统一日志配置"""
import logging
import sys


def setup_logging(level: str = "INFO", log_file: str | None = None):
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(level=level, format=fmt, handlers=handlers)
    # 降低第三方库噪音
    for lib in ("httpx", "chromadb", "httpcore", "urllib3"):
        logging.getLogger(lib).setLevel(logging.WARNING)
