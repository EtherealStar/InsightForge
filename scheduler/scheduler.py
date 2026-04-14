"""
独立进程运行的定时调度器（支持配置热重载）。
启动方式：python -m scheduler.scheduler

- 每次任务执行前自动 reload .env，获取最新组件
- 定期检查调度参数变更，动态 reschedule 任务
- RSS 源列表每次 Pipeline 执行时重新读取
"""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from core.config_manager import get_config_manager
from core.logging import setup_logging
from infrastructure.collector import NewsCollector
from services.pipeline_service import PipelineService
from services.brief_service import BriefService

logger = logging.getLogger(__name__)

# 全局 scheduler 引用，供 config_check 使用
_scheduler: BlockingScheduler | None = None


# ======================================================================
# 定时任务函数
# ======================================================================

def run_pipeline():
    """定时任务：执行抓取 → 存储 → 向量化（每次用最新配置）"""
    logger.info("=== Pipeline 开始 ===")
    mgr = get_config_manager()
    mgr.reload()  # 拉取最新 .env 配置

    from delivery.api.settings_router import _load_feeds, _load_sites

    config = mgr.config
    config.rss_feeds = _load_feeds()
    collector = NewsCollector(config)

    crawl_sites = _load_sites()
    web_crawler = None
    if crawl_sites:
        from infrastructure.web_crawler import WebCrawler
        web_crawler = WebCrawler()

    service = PipelineService(
        collector, mgr.article_store, mgr.vector_store, mgr.embedding_client,
        web_crawler=web_crawler,
        crawl_sites=crawl_sites,
    )
    result = service.run()
    logger.info(f"Pipeline 完成: {result}")


def run_daily_brief():
    """定时任务：生成日报（每次用最新 LLM 配置）"""
    logger.info("=== 日报生成开始 ===")
    mgr = get_config_manager()
    mgr.reload()

    service = BriefService(
        mgr.article_store, mgr.llm_client, mgr.config.output_path
    )
    brief = service.generate(hours=24)
    logger.info(f"日报已生成：{brief.generated_at}")

    # 自动推送（如果已启用）
    try:
        from services.webhook_service import WebhookService
        webhook_service = WebhookService()
        if webhook_service.get_auto_push():
            push_results = webhook_service.broadcast(brief.content_markdown)
            push_ok = sum(1 for r in push_results if r["status"] == "ok")
            logger.info(f"自动推送: {push_ok}/{len(push_results)} 个渠道成功")
    except Exception as push_err:
        logger.warning(f"自动推送异常（不影响日报生成）: {push_err}")


def run_cleanup():
    """定时任务：清理旧文章（每次读取最新保留天数）"""
    mgr = get_config_manager()
    mgr.reload()
    retention_days = mgr.config.article_retention_days
    deleted = mgr.article_store.cleanup_old_articles(retention_days)
    logger.info(f"清理完成，删除 {deleted} 篇旧文章")


def check_schedule_config():
    """
    定期检查调度参数是否变更，若有变化则 reschedule 对应任务。
    该任务自身每 5 分钟运行一次。
    """
    global _scheduler
    if _scheduler is None:
        return

    mgr = get_config_manager()
    old_config = mgr.config
    result = mgr.reload()

    if not result.get("changed"):
        return

    new_config = mgr.config
    changed_fields = set(result.get("fields", []))

    # 检查 Pipeline 间隔是否变化
    if "fetch_interval_hours" in changed_fields:
        new_hours = new_config.fetch_interval_hours
        try:
            _scheduler.reschedule_job(
                "pipeline", trigger="interval", hours=new_hours,
            )
            logger.info(f"✅ Pipeline 间隔已动态调整为 {new_hours}h")
        except Exception as e:
            logger.error(f"reschedule pipeline 失败: {e}")

    # 检查日报生成时间是否变化
    if "daily_brief_hour" in changed_fields:
        new_hour = new_config.daily_brief_hour
        try:
            _scheduler.reschedule_job(
                "daily_brief", trigger="cron", hour=new_hour,
            )
            logger.info(f"✅ 日报生成时间已动态调整为每天 {new_hour}:00")
        except Exception as e:
            logger.error(f"reschedule daily_brief 失败: {e}")

    if changed_fields - {"fetch_interval_hours", "daily_brief_hour"}:
        logger.info(
            f"配置已热重载 (v{result['version']}): "
            f"变更={result['fields']}, 重建组件={result.get('rebuilt', [])}"
        )


# ======================================================================
# 主入口
# ======================================================================

def main():
    global _scheduler

    mgr = get_config_manager()
    config = mgr.config
    setup_logging(config.log_level)

    # 启动时执行一次抓取
    logger.info("=== 系统启动自动抓取 ===")
    try:
        run_pipeline()
    except Exception as e:
        logger.error(f"启动抓取失败（调度器继续运行）: {e}")

    # 设置定时任务
    _scheduler = BlockingScheduler()

    _scheduler.add_job(
        run_pipeline,
        "interval",
        hours=config.fetch_interval_hours,
        id="pipeline",
    )
    _scheduler.add_job(
        run_daily_brief,
        "cron",
        hour=config.daily_brief_hour,
        id="daily_brief",
    )
    _scheduler.add_job(
        run_cleanup,
        "cron",
        day_of_week="sun",
        hour=3,
        id="weekly_cleanup",
    )
    # 每 5 分钟检查一次配置是否变更，动态调整调度
    _scheduler.add_job(
        check_schedule_config,
        "interval",
        minutes=5,
        id="config_check",
    )

    logger.info(
        f"调度器启动 — Pipeline 间隔 {config.fetch_interval_hours}h，"
        f"日报时间 每天 {config.daily_brief_hour}:00，"
        f"配置检查间隔 5min"
    )
    _scheduler.start()


if __name__ == "__main__":
    main()
