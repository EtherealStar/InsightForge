"""统一日志配置"""
import logging
import sys
import os
import structlog


def setup_logging(level: str = "INFO", log_file: str | None = None):
    # 根据环境变量 LOG_FORMAT 决定日志格式：json 或 console
    log_format = os.environ.get("LOG_FORMAT", "console").lower()
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # shared_processors 供业务 logger 和标准库外来的 logger 共用
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.contextvars.merge_contextvars,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # 配置 structlog (拦截业务代码使用 structlog.get_logger 生成的日志)
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 配置标准库的 Formatter，将 structlog 事件转为最终文本
    if log_format == "json":
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )
    else:
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=True),
            foreign_pre_chain=shared_processors,
        )

    # 构造标准库 Handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    
    handlers: list[logging.Handler] = [stream_handler]
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # 接管标准库的 root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.handlers.clear()
    for h in handlers:
        root_logger.addHandler(h)

    # 降低第三方库噪音
    for lib in ("httpx", "chromadb", "httpcore", "urllib3", "psycopg2"):
        logging.getLogger(lib).setLevel(logging.WARNING)
