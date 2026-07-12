from services.collection_metrics_service import CollectionMetricsService


class Store:
    def collection_metrics(self):
        return {
            "runs_running": 2,
            "candidates_discovered": 10,
            "artifacts_fetched": 8,
            "documents_normalized": 7,
            "documents_accepted": 5,
            "browser_artifacts": 1,
            "blocked_artifacts": 2,
            "not_modified_artifacts": 3,
        }


def test_metrics_are_rendered_as_prometheus_text():
    text = CollectionMetricsService(Store()).render_prometheus()
    assert "insightforge_collection_candidates_discovered 10" in text
    assert "insightforge_collection_documents_accepted 5" in text
    assert text.endswith("\n")
