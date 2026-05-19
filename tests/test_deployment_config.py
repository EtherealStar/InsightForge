from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_prod_compose_uses_explicit_app_environment():
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "x-app-env:" in compose
    assert "env_file:" not in compose
    for key in (
        "APP_ENV",
        "AUTH_ENABLED",
        "PG_DSN",
        "CELERY_BROKER_URL",
        "QDRANT_URL",
        "STRUCTURED_EXTRACTION_PROVIDER",
        "JUDGE_PROVIDER",
        "REPORT_QUALITY_AUTO_PUBLISH",
    ):
        assert f"{key}:" in compose


def test_deploy_example_has_phase3_security_and_no_legacy_summary_config():
    env_example = (ROOT / ".env.deploy.example").read_text(encoding="utf-8")

    for legacy_key in ("SUMMARY_LLM_PROVIDER", "SUMMARY_LLM_API_KEY", "SUMMARY_USE_SAME_LLM"):
        assert legacy_key not in env_example

    for key in (
        "APP_ENV=production",
        "AUTH_ENABLED=true",
        "REPORT_QUALITY_AUTO_PUBLISH=false",
        "STRUCTURED_EXTRACTION_PROVIDER=openai_compatible",
        "JUDGE_PROVIDER=openai_compatible",
        "QDRANT_URL=http://qdrant:6333",
        "CELERY_BROKER_URL=redis://:change-redis-password@redis:6379/0",
    ):
        assert key in env_example
