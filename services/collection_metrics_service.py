"""从 PostgreSQL 权威状态生成 Prometheus text exposition。"""


class CollectionMetricsService:
    PREFIX = "insightforge_collection_"

    def __init__(self, collection_store):
        self.store = collection_store

    def render_prometheus(self) -> str:
        metrics = self.store.collection_metrics()
        lines = []
        for name, value in sorted(metrics.items()):
            metric = f"{self.PREFIX}{name}"
            lines.append(f"# TYPE {metric} gauge")
            lines.append(f"{metric} {int(value)}")
        return "\n".join(lines) + "\n"
