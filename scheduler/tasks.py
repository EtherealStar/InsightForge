import structlog
from datetime import datetime
import redis
from celery import shared_task

from core.config_manager import get_config_manager
from core.source_config import load_feeds, load_sites
from infrastructure.collector import NewsCollector
from services.pipeline_service import PipelineService
from services.brief_service import BriefService

logger = structlog.get_logger(__name__)

def get_redis_client():
    config = get_config_manager().config
    return redis.Redis.from_url(config.celery_broker_url, decode_responses=True)

@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def run_pipeline_task(self, manual=False):
    """
    执行抓取 → 存储 → AI 摘要 → 向量化
    被 Beat 高频调用（每 5 分钟），内部通过 Redis 检查距离上次运行是否超过设定间隔。
    也可通过异步 API 直接触发（直接触发时将绕过频率检查，或至少会执行）。
    为了支持手动强制触发，我们通过 task 的 kwargs 判断。这里如果是由 beat 触发，会进行拦截；手动触发强制执行。
    """
    mgr = get_config_manager()
    mgr.reload()
    config = mgr.config
    
    r = get_redis_client()
    last_run_str = r.get("logos:last_pipeline_run")
    
    # 简单的判定：如果是定时任务调用的（无参），我们检查间隔
    
    if not manual and last_run_str:
        last_run = datetime.fromisoformat(last_run_str)
        elapsed_hours = (datetime.now() - last_run).total_seconds() / 3600.0
        if elapsed_hours < config.fetch_interval_hours:
            logger.info(f"Pipeline skipped. Elapsed {elapsed_hours:.2f}h < interval {config.fetch_interval_hours}h")
            return "Skipped"

    logger.info("=== Pipeline 开始 ===")
    
    from services.summary_service import SummaryService
    
    config.rss_feeds = load_feeds()
    collector = NewsCollector(config)
    
    crawl_sites = load_sites()
    web_crawler = None
    if crawl_sites:
        from infrastructure.web_crawler import WebCrawler
        web_crawler = WebCrawler()

    summary_service = None
    if mgr.summary_llm_client:
        summary_service = SummaryService(
            llm_client=mgr.summary_llm_client,
            article_store=mgr.article_store,
            batch_size=config.summary_batch_size,
        )

    service = PipelineService(
        collector, mgr.article_store, mgr.vector_store, mgr.embedding_client,
        chunking_service=mgr.chunking_service,
        web_crawler=web_crawler,
        crawl_sites=crawl_sites,
        markdown_output_path=config.markdown_output_path,
        summary_service=summary_service,
    )
    result = service.run()
    
    r.set("logos:last_pipeline_run", datetime.now().isoformat())
    logger.info(f"Pipeline 完成: {result}")
    return result

@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def run_daily_brief_task(self, manual=False):
    """
    执行日报生成并推送。
    同样被 Beat 高频调用，内部检查是否到达今天生成的时机或者满足间隔时间。
    """
    mgr = get_config_manager()
    mgr.reload()
    config = mgr.config
    
    r = get_redis_client()
    last_run_str = r.get("logos:last_daily_brief_run")
    last_run = datetime.fromisoformat(last_run_str) if last_run_str else None
    
    now = datetime.now()
    should_run = False
    
    if manual:
        should_run = True
    else:
        if config.brief_mode == "interval":
            if not last_run:
                should_run = True
            else:
                elapsed_hours = (now - last_run).total_seconds() / 3600.0
                if elapsed_hours >= config.brief_interval_hours:
                    should_run = True
        else:
            # 每日模式：大于设定的 target hour，且今天还没执行过
            if now.hour >= config.daily_brief_hour:
                if not last_run or last_run.date() < now.date():
                    should_run = True

    if not should_run:
        return "Skipped"

    logger.info("=== 日报生成开始 ===")
    service = BriefService(mgr.article_store, mgr.llm_client, config.output_path)
    brief = service.generate(hours=config.brief_fetch_hours)
    
    r.set("logos:last_daily_brief_run", now.isoformat())
    logger.info(f"日报已生成：{brief.generated_at}")

    try:
        webhook_service = mgr.webhook_service
        if webhook_service.get_auto_push():
            push_results = webhook_service.broadcast(brief.content_markdown)
            push_ok = sum(1 for res in push_results if res["status"] == "ok")
            logger.info(f"自动推送: {push_ok}/{len(push_results)} 个渠道成功")
    except Exception as push_err:
        logger.warning(f"自动推送异常: {push_err}")
        
    return {"generated_at": brief.generated_at, "status": "success"}

@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def run_cleanup_task(self):
    """定期清理过期的文章。由 Celery Beat 按照 crontab(weekly) 调用"""
    mgr = get_config_manager()
    mgr.reload()
    retention_days = mgr.config.article_retention_days
    deleted = mgr.article_store.cleanup_old_articles(retention_days)
    logger.info(f"清理完成，删除 {deleted} 篇旧文章")
    return deleted
