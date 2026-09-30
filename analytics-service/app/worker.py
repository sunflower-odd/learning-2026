"""Читает stream событий и строит «смотрели вместе» для рекомендаций."""

import asyncio
import logging
import os
import socket

from redis.exceptions import ResponseError

from app import db
from app.db import redis

GROUP = "recommender"
CONSUMER = os.getenv("CONSUMER_NAME", socket.gethostname())
BATCH = 100
CLAIM_IDLE_MS = 60_000  # забираем сообщения, зависшие у упавших воркеров
CO_HISTORY = 20
CO_LIMIT = 500

log = logging.getLogger("worker")


async def ensure_group() -> None:
    try:
        await redis.xgroup_create(db.EVENTS_STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


async def claim_stale() -> None:
    start = "0-0"
    while True:
        start = (await redis.xautoclaim(db.EVENTS_STREAM, GROUP, CONSUMER, CLAIM_IDLE_MS, start, count=BATCH))[0]
        if start == "0-0":
            return


async def handle(fields: dict) -> None:
    if fields["type"] == "rate" and int(fields["rating"]) < 4:
        return
    item = fields["item_id"]
    history = await redis.zrevrange(db.user_seen(fields["user_id"]), 0, CO_HISTORY)
    others = [i for i in history if i != item]
    if not others:
        return
    pipe = redis.pipeline(transaction=False)
    for other in others:
        pipe.zincrby(db.co_items(item), 1, other)
        pipe.zincrby(db.co_items(other), 1, item)
        pipe.zremrangebyrank(db.co_items(other), 0, -CO_LIMIT - 1)
    pipe.zremrangebyrank(db.co_items(item), 0, -CO_LIMIT - 1)
    await pipe.execute()


async def run() -> None:
    await ensure_group()
    await claim_stale()
    last_id = "0"  # сначала свои неподтверждённые сообщения, потом новые
    log.info("consumer %s started", CONSUMER)
    while True:
        resp = await redis.xreadgroup(GROUP, CONSUMER, {db.EVENTS_STREAM: last_id}, count=BATCH, block=5000)
        messages = resp[0][1] if resp else []
        if not messages:
            last_id = ">"
            continue
        for _, fields in messages:
            await handle(fields)
        await redis.xack(db.EVENTS_STREAM, GROUP, *(msg_id for msg_id, _ in messages))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
