import pytest

from core.config import AppConfig
from core.exceptions import StructuredExtractionError
from core.factory import create_structured_extraction_client
from infrastructure.structured_extraction_client import parse_json_object_response


def test_parse_json_object_response_accepts_plain_object():
    assert parse_json_object_response('{"facts": []}', "facts") == {"facts": []}


def test_parse_json_object_response_accepts_fenced_object():
    text = '```json\n{"facts": [{"id": 1}]}\n```'

    assert parse_json_object_response(text, "facts") == {"facts": [{"id": 1}]}


def test_parse_json_object_response_rejects_non_object():
    with pytest.raises(StructuredExtractionError):
        parse_json_object_response('[{"id": 1}]', "facts")


def test_parse_json_object_response_rejects_bad_json():
    with pytest.raises(StructuredExtractionError):
        parse_json_object_response("not json", "facts")


def test_structured_extraction_factory_uses_independent_config(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import core.factory as factory

    monkeypatch.setattr(
        factory,
        "create_llm_client",
        lambda config: (_ for _ in ()).throw(AssertionError("must not use main llm")),
    )
    monkeypatch.setattr(
        "infrastructure.structured_extraction_client.OpenAICompatibleStructuredExtractionClient",
        FakeClient,
    )

    config = AppConfig(
        llm_api_key="main-key",
        llm_base_url="https://main.example",
        llm_model="main-model",
        structured_extraction_api_key="structured-key",
        structured_extraction_base_url="https://structured.example",
        structured_extraction_model="structured-model",
        structured_extraction_temperature=0.2,
        structured_extraction_max_tokens=1234,
    )

    create_structured_extraction_client(config)

    assert captured == {
        "api_key": "structured-key",
        "base_url": "https://structured.example",
        "model": "structured-model",
        "max_tokens": 1234,
        "default_temperature": 0.2,
    }
