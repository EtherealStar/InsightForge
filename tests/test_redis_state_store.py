"""RedisStateStore behavior tests."""

from infrastructure.redis.state_store import RedisStateStore


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.streams = {}
        self.deleted = []

    def ping(self):
        return True

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        existed = key in self.values
        self.values.pop(key, None)
        self.deleted.append(key)
        return 1 if existed else 0

    def eval(self, script, numkeys, key, owner):
        if self.values.get(key) == owner:
            return self.delete(key)
        return 0

    def xadd(self, key, fields):
        self.streams.setdefault(key, []).append(fields)
        return "1-0"


class FailingRedis:
    def ping(self):
        raise RuntimeError("redis down")

    def set(self, *args, **kwargs):
        raise RuntimeError("redis down")

    def get(self, *args, **kwargs):
        raise RuntimeError("redis down")

    def delete(self, *args, **kwargs):
        raise RuntimeError("redis down")

    def eval(self, *args, **kwargs):
        raise RuntimeError("redis down")

    def xadd(self, *args, **kwargs):
        raise RuntimeError("redis down")


def test_json_task_status_event_and_idempotency():
    fake = FakeRedis()
    store = RedisStateStore(redis_url=None, client=fake)

    assert store.healthcheck() is True
    assert store.set_json("logos:cache:test", {"ok": True}, ttl_seconds=60)
    assert store.get_json("logos:cache:test") == {"ok": True}

    assert store.set_task_status("run-1", "running", {"stage": "parse"})
    assert store.get_task_status("run-1") == {
        "run_id": "run-1",
        "status": "running",
        "payload": {"stage": "parse"},
    }

    assert store.append_task_event("run-1", {"event_type": "started"})
    assert fake.streams["logos:task_events:run-1"][0]["event"]

    assert store.set_idempotency_key("logos:idempotency:file:abc", "blob-1", 60)
    assert store.get_idempotency_key("logos:idempotency:file:abc") == "blob-1"
    assert not store.set_idempotency_key("logos:idempotency:file:abc", "blob-2", 60)


def test_lock_release_requires_matching_owner():
    fake = FakeRedis()
    store = RedisStateStore(redis_url=None, client=fake)

    assert store.acquire_lock("logos:lock:pipeline", "owner-a", 30)
    assert not store.release_lock("logos:lock:pipeline", "owner-b")
    assert fake.get("logos:lock:pipeline") == "owner-a"

    assert store.release_lock("logos:lock:pipeline", "owner-a")
    assert fake.get("logos:lock:pipeline") is None


def test_redis_failures_degrade_to_false_or_none():
    store = RedisStateStore(redis_url=None, client=FailingRedis())

    assert store.healthcheck() is False
    assert store.acquire_lock("logos:lock:pipeline", "owner", 30) is False
    assert store.release_lock("logos:lock:pipeline", "owner") is False
    assert store.set_json("logos:cache:test", {"ok": True}) is False
    assert store.get_json("logos:cache:test") is None
    assert store.delete("logos:cache:test") is False
    assert store.set_task_status("run-1", "running") is False
    assert store.get_task_status("run-1") is None
    assert store.append_task_event("run-1", {"event_type": "started"}) is False
    assert store.set_idempotency_key("logos:idempotency:test", "value", 60) is False
    assert store.get_idempotency_key("logos:idempotency:test") is None
