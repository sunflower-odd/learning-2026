import json
import os

from pymemcache.client.base import Client

client = Client(
    (os.getenv("MEMCACHED_HOST", "localhost"), int(os.getenv("MEMCACHED_PORT", "11211"))),
    connect_timeout=0.1,
    timeout=0.1,
)


def get_or_set(key: str, ttl: int, loader) -> tuple[object, bool]:
    """Возвращает (value, hit): значение из кэша или из loader() при промахе."""
    cached = client.get(key)
    if cached is not None:
        return json.loads(cached), True    # HIT → данные из кэша
    value = loader()                       # MISS → идём в БД
    if value is not None:                  # «не найдено» не кэшируем
        client.set(key, json.dumps(value), expire=ttl)
    return value, False


def delete(*keys: str) -> None:
    for key in keys:
        client.delete(key)