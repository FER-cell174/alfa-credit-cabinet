"""Адаптеры внешних источников. Контракт: запрос по ИНН → нормализованный ответ.

MOCKS_URL не задан — вызываем моки в процессе. Задан — ходим по HTTP в сервис моков
(в Docker Compose). Заменить мок реальным сервисом = заменить реализацию здесь.
"""
from .config import MOCKS_URL
from .domain import mocks
from .domain.pipeline import Fetcher


def _http_fetcher(source: str) -> Fetcher:
    import httpx

    def fetch(inn: str) -> dict:
        try:
            r = httpx.get(f"{MOCKS_URL}/{source}/{inn}", timeout=3.0)
        except httpx.TimeoutException:
            raise mocks.MockTimeout(f"{source}: таймаут")
        if r.status_code == 504:
            raise mocks.MockTimeout(f"{source}: источник не ответил")
        if r.status_code == 404:
            raise mocks.MockNotFound(inn)
        r.raise_for_status()
        return r.json()

    return fetch


def get_fetchers() -> dict[str, Fetcher]:
    if MOCKS_URL:
        return {s: _http_fetcher(s) for s in ("egrul", "fns", "bki")}
    return {"egrul": mocks.egrul, "fns": mocks.fns, "bki": mocks.bki}
