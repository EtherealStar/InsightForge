"""
独立进程运行的定时调度器。
启动方式：python -m scheduler.scheduler
不与 Streamlit 进程耦合。
"""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from core.config import AppConfig
from core.logging import setup_logging
from core.factory import (
    create_article_store,
    create_vector_store,
    create_llm_client,
    create_embedding_client,
)
from infrastructure.collector import NewsCollector
from services.pipeline_service import PipelineService
from services.brief_service import BriefService

logger = logging.getLogger(__name__)


def run_pipeline(pipeline_service: PipelineService):
    """定时任务：执行抓取 → 存储 → 向量化"""
    logger.info("=== Pipeline 开始 ===")
    result = pipeline_service.run()
    logger.info(f"Pipeline 完成: {result}")


def run_daily_brief(brief_service: BriefService):
    """定时任务：生成日报"""
    logger.info("=== 日报生成开始 ===")
    brief = brief_service.generate(hours=24)
    logger.info(f"日报已生成：{brief.generated_at}")


def run_cleanup(article_store, retention_days: int):
    """定时任务：清理旧文章"""
    deleted = article_store.cleanup_old_articles(retention_days)
    logger.info(f"清理完成，删除 {deleted} 篇旧文章")


def main():
    config = AppConfig()
    setup_logging(config.log_level)

    from delivery.api.settings_router import _load_feeds, _load_sites
    config.rss_feeds = _load_feeds()

    article_store = create_article_store(config)
    vector_store = create_vector_store(config)
    llm_client = create_llm_client(config)
    embedding_client = create_embedding_client(config)
    collector = NewsCollector(config)

    crawl_sites = _load_sites()
    web_crawler = None
    if crawl_sites:
        from infrastructure.web_crawler import WebCrawler
        web_crawler = WebCrawler()

    pipeline_service = PipelineService(
        collector, article_store, vector_store, embedding_client,
        web_crawler=web_crawler,
        crawl_sites=crawl_sites,
    )
    brief_service = BriefService(
        article_store, llm_client, config.output_path
    )

    # 启动时仅执行一次抓取与存储
    logger.info("=== 系统启动自动抓取 ===")
    pipeline_service.fetch_and_store()

    # 设置定时任务
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_pipeline,
        "interval",
        hours=config.fetch_interval_hours,
        args=[pipeline_service],
        id="pipeline",
    )
    scheduler.add_job(
        run_daily_brief,
        "cron",
        hour=config.daily_brief_hour,
        args=[brief_service],
        id="daily_brief",
    )
    scheduler.add_job(
        run_cleanup,
        "cron",
        day_of_week="sun",
        hour=3,
        args=[article_store, config.article_retention_days],
        id="weekly_cleanup",
    )

    logger.info(
        f"调度器启动 — Pipeline 间隔 {config.fetch_interval_hours}h，"
        f"日报时间 每天 {config.daily_brief_hour}:00"
    )
    scheduler.start()


if __name__ == "__main__":
    main()
