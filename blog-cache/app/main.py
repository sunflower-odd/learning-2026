from contextlib import asynccontextmanager
from html import escape

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app import cache, db

ARTICLE_TTL = 300
POPULAR_TTL = 60


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Создаёт таблицу и тестовые статьи при старте приложения."""
    db.init_db()
    yield


app = FastAPI(lifespan=lifespan)


class ArticleUpdate(BaseModel):
    title: str
    body: str


def article_key(article_id: int) -> str:
    """Ключ кэша для JSON статьи."""
    return f"article:{article_id}"


def article_page_key(article_id: int) -> str:
    """Ключ кэша для HTML-страницы статьи."""
    return f"page:article:{article_id}"


def x_cache(hit: bool) -> dict[str, str]:
    """Заголовок X-Cache: HIT, если данные из кэша, иначе MISS."""
    return {"X-Cache": "HIT" if hit else "MISS"}


@app.get("/articles_popular")
def read_popular_articles(response: Response):
    """Топ-10 статей по просмотрам (кэш на 60 с)."""
    articles, hit = cache.get_or_set("articles:popular", POPULAR_TTL, db.get_popular_articles)
    response.headers.update(x_cache(hit))
    return articles


@app.get("/articles/{article_id}")
def read_article(article_id: int, response: Response):
    """Статья по id: сначала из кэша, при промахе из БД."""
    article, hit = cache.get_or_set(
        article_key(article_id), ARTICLE_TTL, lambda: db.get_article(article_id)
    )
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    response.headers.update(x_cache(hit))
    return article


@app.get("/articles/{article_id}/html", response_class=HTMLResponse)
def read_article_html(article_id: int):
    """HTML-страница статьи: сначала из кэша, при промахе рендерится из БД."""

    def render() -> str | None:
        article = db.get_article(article_id)
        if article is None:
            return None
        return f"<h1>{escape(article['title'])}</h1><p>{escape(article['body'])}</p>"

    page, hit = cache.get_or_set(article_page_key(article_id), ARTICLE_TTL, render)
    if page is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return HTMLResponse(page, headers=x_cache(hit))


@app.put("/articles/{article_id}")
def update_article(article_id: int, payload: ArticleUpdate):
    """Обновляет статью в БД и удаляет её ключи из кэша."""
    article = db.update_article(article_id, payload.title, payload.body)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    cache.delete(article_key(article_id), article_page_key(article_id))
    return article
