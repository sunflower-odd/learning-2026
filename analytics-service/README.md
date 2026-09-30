# Real-Time Analytics and Recommendation Service

FastAPI + Redis. API принимает события (`view`, `click`, `rate`), сразу обновляет счётчики и рейтинги, а воркеры
через Redis Streams строят данные для рекомендаций.

## Как требования ложатся на Redis

| Требование                   | Реализация                                                                                    |
|------------------------------|-----------------------------------------------------------------------------------------------|
| Счётчики просмотров/кликов   | `HINCRBY item:{id}:stats` — атомарный инкремент                                               |
| Рейтинги товаров             | Lua-скрипт: оценка пользователя в `item:{id}:ratings`, сумма и количество — в `stats`; повторная оценка заменяет старую |
| Последние действия           | `LPUSH` + `LTRIM user:{id}:recent` (50 последних)                                             |
| Топы и отчёты                | Sorted set по часам `top:{type}:YYYYMMDDHH`, окно N часов — `ZUNIONSTORE`, кэш на 60 с       |
| Очередь событий              | Stream `events`, consumer group `recommender`, `XAUTOCLAIM` забирает сообщения упавших воркеров |
| Рекомендации                 | Co-occurrence «смотрели вместе» в `co:{item}` (sorted set); не хватает — добивается трендами |
| Минимальная задержка         | Все записи по событию — один pipeline, один round trip; `/events/batch` до 1000 событий       |
| Персистентность              | AOF `appendfsync everysec` + RDB-снапшоты в `./data`; при сбое теряется не больше ~1 с (для нуля — `always`) |
| Масштабирование              | API stateless, воркеры масштабируются репликами; ключи с hash tags `{...}` готовы к Redis Cluster |

## Запуск

```bash
uv sync
docker compose up --build
```

Swagger: http://localhost:8000/docs

## Пример

```bash
curl -X POST localhost:8000/events -H 'Content-Type: application/json' \
  -d '{"user_id": "u1", "item_id": "i1", "type": "view"}'
curl -X POST localhost:8000/events -H 'Content-Type: application/json' \
  -d '{"user_id": "u1", "item_id": "i1", "type": "rate", "rating": 5}'
curl localhost:8000/items/i1/stats
curl localhost:8000/users/u1/recent
curl localhost:8000/users/u1/recommendations
curl 'localhost:8000/reports/top?event=view&hours=24'
```
