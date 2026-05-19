"""Competitor management service with fact-level intelligence links."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

import structlog

from core.protocols import (
    CompetitorStoreProtocol,
    DocumentStoreProtocol,
    IntelStoreProtocol,
)
from models.competitor import Competitor, CompetitorProduct

logger = structlog.get_logger(__name__)


class CompetitorService:
    """Competitor CRUD plus structured fact attribution and aggregation."""

    def __init__(
        self,
        competitor_store: CompetitorStoreProtocol,
        intel_store: IntelStoreProtocol,
        document_store: DocumentStoreProtocol | None = None,
    ):
        self.competitor_store = competitor_store
        self.intel_store = intel_store
        self.document_store = document_store

    def create_competitor(self, data: dict) -> Competitor:
        comp = Competitor(
            name=data["name"],
            aliases=data.get("aliases", []),
            website=data.get("website", ""),
            industry=data.get("industry", ""),
            description=data.get("description", ""),
            logo_url=data.get("logo_url", ""),
            tags=data.get("tags", []),
        )
        return self.competitor_store.save_competitor(comp)

    def update_competitor(self, competitor_id: int, data: dict) -> Competitor | None:
        comp = self.competitor_store.get_competitor(competitor_id)
        if not comp:
            return None
        for field in (
            "name",
            "aliases",
            "website",
            "industry",
            "description",
            "logo_url",
            "tags",
            "status",
        ):
            if field in data:
                setattr(comp, field, data[field])
        return self.competitor_store.save_competitor(comp)

    def get_competitor(self, competitor_id: int) -> dict | None:
        comp = self.competitor_store.get_competitor(competitor_id)
        if not comp:
            return None
        products = self.competitor_store.list_products(competitor_id)
        fact_count = len(
            self.intel_store.list_facts({"competitor_id": competitor_id}, limit=1000)
        )
        return {
            "competitor": comp,
            "products": products,
            "intel_count": fact_count,
            "fact_count": fact_count,
        }

    def list_competitors(self, status: str = "active") -> list[Competitor]:
        return self.competitor_store.list_competitors(status=status)

    def delete_competitor(self, competitor_id: int) -> None:
        self.competitor_store.delete_competitor(competitor_id)

    def add_product(self, competitor_id: int, data: dict) -> CompetitorProduct:
        product = CompetitorProduct(
            competitor_id=competitor_id,
            name=data["name"],
            description=data.get("description", ""),
            category=data.get("category", ""),
            url=data.get("url", ""),
            pricing_info=data.get("pricing_info", ""),
        )
        return self.competitor_store.save_product(product)

    def delete_product(self, product_id: int) -> None:
        self.competitor_store.delete_product(product_id)

    def get_competitor_fact_profile(
        self,
        competitor_id: int,
        filters: dict[str, Any] | None = None,
    ) -> dict | None:
        comp = self.competitor_store.get_competitor(competitor_id)
        if not comp:
            return None
        products = self.competitor_store.list_products(competitor_id)
        query = dict(filters or {})
        query["competitor_id"] = competitor_id
        facts = self.intel_store.list_facts(query, limit=query.get("limit", 50))
        by_dimension: dict[str, int] = defaultdict(int)
        by_type: dict[str, int] = defaultdict(int)
        for fact in facts:
            by_dimension[getattr(fact.dimension, "value", fact.dimension)] += 1
            by_type[getattr(fact.fact_type, "value", fact.fact_type)] += 1
        return {
            "competitor": comp,
            "products": products,
            "facts": facts,
            "aggregates": {
                "by_dimension": dict(by_dimension),
                "by_type": dict(by_type),
                "total": len(facts),
            },
        }

    def compare_competitor_facts(
        self,
        competitor_ids: list[int],
        dimensions: list[str] | None = None,
        time_window: dict[str, str] | None = None,
    ) -> dict:
        comparisons = []
        for competitor_id in competitor_ids:
            filters: dict[str, Any] = {"competitor_id": competitor_id}
            if time_window:
                filters.update(
                    {
                        "date_from": time_window.get("date_from"),
                        "date_to": time_window.get("date_to"),
                    }
                )
            if dimensions:
                dimension_rows = []
                for dimension in dimensions:
                    profile = self.get_competitor_fact_profile(
                        competitor_id, {**filters, "dimension": dimension}
                    )
                    if profile:
                        dimension_rows.append(profile)
                comparisons.append(
                    {"competitor_id": competitor_id, "dimensions": dimension_rows}
                )
            else:
                comparisons.append(self.get_competitor_fact_profile(competitor_id, filters))
        return {"competitor_ids": competitor_ids, "comparisons": comparisons}

    def get_competitor_timeline(
        self,
        competitor_id: int,
        filters: dict[str, Any] | None = None,
    ) -> dict | None:
        profile = self.get_competitor_fact_profile(competitor_id, filters)
        if not profile:
            return None
        timeline = [
            fact
            for fact in profile["facts"]
            if fact.event_date or getattr(fact.fact_kind, "value", fact.fact_kind) == "event"
        ]
        timeline.sort(
            key=lambda fact: (
                fact.event_date or date.min,
                fact.observed_at or datetime.min,
            ),
            reverse=True,
        )
        return {**profile, "timeline": timeline}

    def auto_link_documents(self, document_ids: list[str] | None = None) -> dict:
        if self.document_store is None:
            return {"linked": 0, "documents_processed": 0, "reason": "document_store_missing"}
        competitors = self.competitor_store.list_competitors()
        if not competitors:
            return {"linked": 0, "documents_processed": 0}
        if document_ids is None:
            documents = self.document_store.list_documents({"parse_status": "parsed"}, limit=100)
        else:
            documents = [
                doc
                for doc_id in document_ids
                if (doc := self.document_store.get_document(doc_id)) is not None
            ]
        linked = 0
        for document in documents:
            text = f"{document.title} {document.content[:1000]}"
            matches = [comp.id for comp in competitors if comp.id and comp.matches_name(text)]
            new_ids = sorted(set(document.competitor_ids) | set(matches))
            if new_ids != document.competitor_ids:
                document.competitor_ids = new_ids
                self.document_store.save_document(document)
                linked += len(matches)
        return {"linked": linked, "documents_processed": len(documents)}

    def auto_link_facts(self, document_ids: list[str] | None = None) -> dict:
        competitors = self.competitor_store.list_competitors()
        if not competitors:
            return {"linked": 0, "facts_processed": 0}

        filters: dict[str, Any] = {}
        if document_ids and len(document_ids) == 1:
            filters["source_document_id"] = document_ids[0]
        facts = self.intel_store.list_facts(filters, limit=1000)
        if document_ids and len(document_ids) > 1:
            doc_ids = set(document_ids)
            facts = [fact for fact in facts if fact.source_document_id in doc_ids]

        linked = 0
        for fact in facts:
            text = f"{fact.subject} {fact.object} {fact.fact_text}"
            for comp in competitors:
                if not comp.id or comp.id in fact.competitor_ids:
                    continue
                if comp.matches_name(text):
                    self.intel_store.link_fact_to_competitor(fact.id, comp.id)
                    linked += 1
            for comp in competitors:
                if not comp.id or comp.id not in fact.competitor_ids:
                    continue
                for product in self.competitor_store.list_products(comp.id):
                    if product.id and product.id not in fact.product_ids:
                        product_text = f"{product.name} {product.description}"
                        if product.name and product.name.lower() in text.lower():
                            self.intel_store.link_fact_to_product(fact.id, product.id)
                            linked += 1
        logger.info("auto_link_facts.done", facts_processed=len(facts), linked=linked)
        return {"linked": linked, "facts_processed": len(facts)}
