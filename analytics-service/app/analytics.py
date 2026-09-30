import json
import time
from collections import Counter
from datetime import UTC, datetime, timedelta

from app import db
from app.db import redis
from app.models import EventIn, EventType

RECENT_LIMIT = 50
SEEN_LIMIT = 200
TOP_BUCKET_TTL = int(timedelta(days=8).total_seconds())
TOP_WINDOW_TTL = 60
RECS_HISTORY = 20
RECS_PER_SEED = 50

# повторная оценка пользователя заменяет старую, а не учитывается дважды.
RATE_SCRIPT = redis.register_script("""
local old = redis.call('HGET', KEYS[1], ARGV[1])
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
if old then
  redis.call('HINCRBY', KEYS[2], 'rating_sum', tonumber(ARGV[2]) - tonumber(old))
else
  redis.call('HINCRBY', KEYS[2], 'rating_sum', ARGV[2])
  redis.call('HINCRBY', KEYS[2], 'rating_count', 1)
end
""")


def _hour(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y%m%d%H")


async def record_events(events: list[EventIn]) -> list[str]:
    ts = time.time()
    pipe = redis.pipeline(transaction=False)
    for event in events:
        fields = {"user_id": event.user_id, "item_id": event.item_id, "type": event.type, "ts": ts}
        if event.type is EventType.RATE:
            fields["rating"] = event.rating
            RATE_SCRIPT(
                keys=[db.item_ratings(event.item_id), db.item_stats(event.item_id)],
                args=[event.user_id, event.rating],
                client=pipe,
            )
        else:
            pipe.hincrby(db.item_stats(event.item_id), event.type, 1)

        pipe.lpush(db.user_recent(event.user_id), json.dumps(fields))
        pipe.ltrim(db.user_recent(event.user_id), 0, RECENT_LIMIT - 1)
        pipe.zadd(db.user_seen(event.user_id), {event.item_id: ts})
        pipe.zremrangebyrank(db.user_seen(event.user_id), 0, -SEEN_LIMIT - 1)

        bucket = db.top_bucket(event.type, _hour(ts))
        pipe.zincrby(bucket, 1, event.item_id)
        pipe.expire(bucket, TOP_BUCKET_TTL)

        pipe.xadd(db.EVENTS_STREAM, fields, maxlen=db.STREAM_MAXLEN, approximate=True)

    results = await pipe.execute()
    per_event = len(results) // len(events)
    return [results[i * per_event + per_event - 1] for i in range(len(events))]


async def item_stats(item_id: str) -> dict:
    raw = await redis.hgetall(db.item_stats(item_id))
    rating_count = int(raw.get("rating_count", 0))
    return {
        "item_id": item_id,
        "views": int(raw.get(EventType.VIEW, 0)),
        "clicks": int(raw.get(EventType.CLICK, 0)),
        "rating_count": rating_count,
        "rating_avg": round(int(raw["rating_sum"]) / rating_count, 2) if rating_count else None,
    }


async def recent_actions(user_id: str, limit: int) -> list[dict]:
    return [json.loads(a) for a in await redis.lrange(db.user_recent(user_id), 0, limit - 1)]


async def top_items(event_type: EventType, hours: int, limit: int) -> list[dict]:
    window = db.top_window(event_type, hours)
    if not await redis.exists(window):
        now = time.time()
        buckets = [db.top_bucket(event_type, _hour(now - h * 3600)) for h in range(hours)]
        pipe = redis.pipeline(transaction=False)
        pipe.zunionstore(window, buckets)
        pipe.expire(window, TOP_WINDOW_TTL)
        await pipe.execute()
    rows = await redis.zrevrange(window, 0, limit - 1, withscores=True)
    return [{"item_id": item, "count": int(score)} for item, score in rows]


async def recommendations(user_id: str, limit: int) -> list[dict]:
    """Рекомендации - подбор товаров, которые часто смотрят вместе с тем, что уже смотрел пользователь
    Если истории пользователя недостаточно - рекомендации создаются на основе существующих трендов из top_items()
    """
    seen = await redis.zrevrange(db.user_seen(user_id), 0, -1)
    seen_set = set(seen)

    scores: Counter[str] = Counter()
    if seen:
        pipe = redis.pipeline(transaction=False)
        for item in seen[:RECS_HISTORY]:
            pipe.zrevrange(db.co_items(item), 0, RECS_PER_SEED - 1, withscores=True)
        for rows in await pipe.execute():
            for item, score in rows:
                if item not in seen_set:
                    scores[item] += score

    recs = [{"item_id": i, "score": s, "reason": "also_viewed"} for i, s in scores.most_common(limit)]
    if len(recs) < limit:
        taken = seen_set | {r["item_id"] for r in recs}
        for row in await top_items(EventType.VIEW, 24, limit + len(taken)):
            if row["item_id"] not in taken:
                recs.append({"item_id": row["item_id"], "score": row["count"], "reason": "trending"})
                if len(recs) == limit:
                    break
    return recs
