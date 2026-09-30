from typing import Annotated

from fastapi import Body, FastAPI, Path, Query

from app import analytics
from app.db import redis
from app.models import ID_PATTERN, EventIn, EventType

app = FastAPI(title="Real-Time Analytics and Recommendation Service")

ItemId = Annotated[str, Path(pattern=ID_PATTERN)]
UserId = Annotated[str, Path(pattern=ID_PATTERN)]


@app.get("/health")
async def health() -> dict:
    await redis.ping()
    return {"status": "ok"}


@app.post("/events", status_code=202)
async def post_event(event: EventIn) -> dict:
    [event_id] = await analytics.record_events([event])
    return {"id": event_id}


@app.post("/events/batch", status_code=202)
async def post_events(events: Annotated[list[EventIn], Body(min_length=1, max_length=1000)]) -> dict:
    return {"ids": await analytics.record_events(events)}


@app.get("/items/{item_id}/stats")
async def get_item_stats(item_id: ItemId) -> dict:
    return await analytics.item_stats(item_id)


@app.get("/users/{user_id}/recent")
async def get_recent(user_id: UserId, limit: int = Query(20, ge=1, le=analytics.RECENT_LIMIT)) -> list[dict]:
    return await analytics.recent_actions(user_id, limit)


@app.get("/users/{user_id}/recommendations")
async def get_recommendations(user_id: UserId, limit: int = Query(10, ge=1, le=50)) -> list[dict]:
    return await analytics.recommendations(user_id, limit)


@app.get("/reports/top")
async def get_top(
    event: EventType = EventType.VIEW,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(10, ge=1, le=100),
) -> list[dict]:
    return await analytics.top_items(event, hours, limit)
