"""Отдельный сервис моков внешних источников (ЕГРЮЛ/ЕГРИП, ФНС, БКИ). Все данные синтетические."""
from fastapi import FastAPI, HTTPException

from .domain import mocks

app = FastAPI(title="Моки внешних источников", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


def _call(fn, inn):
    try:
        return fn(inn)
    except mocks.MockNotFound:
        raise HTTPException(404, "Не найдено")
    except mocks.MockTimeout as e:
        raise HTTPException(504, str(e))


@app.get("/egrul/{inn}")
def egrul(inn: str):
    return _call(mocks.egrul, inn)


@app.get("/fns/{inn}")
def fns(inn: str):
    return _call(mocks.fns, inn)


@app.get("/bki/{inn}")
def bki(inn: str):
    return _call(mocks.bki, inn)
