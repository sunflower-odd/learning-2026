import os

from redis.asyncio import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis = Redis.from_url(REDIS_URL, decode_responses=True)

EVENTS_STREAM = "events"
STREAM_MAXLEN = 1_000_000


# Hash tags {...} кладут связанные ключи в один слот Redis Cluster.
def item_stats(item_id: str) -> str:
    return f"item:{{{item_id}}}:stats"


def item_ratings(item_id: str) -> str:
    return f"item:{{{item_id}}}:ratings"


def user_recent(user_id: str) -> str:
    return f"user:{{{user_id}}}:recent"


def user_seen(user_id: str) -> str:
    return f"user:{{{user_id}}}:seen"


def co_items(item_id: str) -> str:
    return f"co:{item_id}"


def top_bucket(event_type: str, hour: str) -> str:
    return f"top:{{{event_type}}}:{hour}"


def top_window(event_type: str, hours: int) -> str:
    return f"top:{{{event_type}}}:last{hours}h"
