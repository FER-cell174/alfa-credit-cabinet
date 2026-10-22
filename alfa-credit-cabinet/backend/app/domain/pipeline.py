"""Шаги конвейера как чистые функции. Хранение и смена статусов — в слое сервиса."""
from __future__ import annotations

import re
from datetime import date
from typing import Callable

from . import mocks
from .decision import decide
from .scoring import compute_score

FIELD_LABELS = {
    "product_code": "Кредитный продукт",
    "amount": "Сумма кредита",
    "term_months": "Срок кредита",
    "purpose": "Цель кредита",
    "inn": "ИНН компании",
    "revenue": "Выручка за последний год",
    "revenue_prev": "Выручка за предыдущий год",
}

Fetcher = Callable[[str], dict]
DEFAULT_FETCHERS: dict[str, Fetcher] = {"egrul": mocks.egrul, "fns": mocks.fns, "bki": mocks.bki}


def validate(data: dict, product: dict | None) -> dict:
    """Проверка полноты и корректности. Возвращает {missing: [...], errors: [...]}"""
    missing, errors = [], []
    for field in ("product_code", "amount", "term_months", "purpose", "inn", "revenue", "revenue_prev"):
        v = data.get(field)
        if v in (None, "") or (field in ("revenue",) and not v):
            missing.append(field)
    inn = data.get("inn")
    if inn and not mocks.valid_inn(str(inn)):
        errors.append("ИНН должен состоять из 10 или 12 цифр")
    if product:
        a, t = data.get("amount"), data.get("term_months")
        if a and not (product["min_amount"] <= a <= product["max_amount"]):
            errors.append(f"Сумма для продукта «{product['name']}» — от {product['min_amount']:,} до {product['max_amount']:,} ₽".replace(",", " "))
        if t and not (product["min_term"] <= t <= product["max_term"]):
            errors.append(f"Срок для продукта «{product['name']}» — от {product['min_term']} до {product['max_term']} мес.")
    return dict(missing=missing, errors=errors, missing_labels=[FIELD_LABELS[m] for m in missing])


def enrich(inn: str, fetchers: dict[str, Fetcher] | None = None, retries: int = 2) -> dict:
    """Опрашивает источники. Таймаут повторяется; при исчерпании попыток источник считается недоступным."""
    fetchers = fetchers or DEFAULT_FETCHERS
    result: dict[str, dict] = {}
    for source, fn in fetchers.items():
        attempts, payload, status, error = 0, None, "ok", None
        while True:
            attempts += 1
            try:
                payload = fn(inn)
                break
            except mocks.MockNotFound:
                status, error = "not_found", "Не найдено"
                break
            except mocks.MockTimeout as e:
                if attempts > retries:
                    status, error = "timeout", str(e)
                    break
        result[source] = dict(source=source, status=status, payload=payload, error=error, attempts=attempts)
    return result


def _norm(name: str) -> str:
    return re.sub(r"[\s«»\"'.]|ооо|ип|ао|пао", "", name.lower())


def evaluate(data: dict, product: dict, checks: dict, today: date | None = None) -> dict:
    """Скоринг + решение по результатам проверок."""
    egrul = checks["egrul"]["payload"]
    fns = checks["fns"]["payload"]
    bki = checks["bki"]["payload"]
    unavailable = [s for s, c in checks.items() if c["status"] == "timeout"]

    scoring = compute_score(
        amount=data["amount"], term_months=data["term_months"], revenue=data["revenue"],
        revenue_prev=data["revenue_prev"], base_rate=product["base_rate"],
        egrul=egrul, fns=fns, bki=bki, today=today)

    if checks["egrul"]["status"] == "not_found":
        scoring["stop_factors"].append(dict(code="company_not_found", text="Компания не найдена в ЕГРЮЛ/ЕГРИП"))
    elif egrul and data.get("company_name") and _norm(data["company_name"]) != _norm(egrul["name"]):
        scoring["stop_factors"].append(dict(code="company_data_mismatch",
                                            text="Название компании в заявке расходится с данными ЕГРЮЛ"))

    decision = decide(klass=scoring["klass"], stop_factors=scoring["stop_factors"], amount=data["amount"],
                      term_months=data["term_months"], revenue=data["revenue"], base_rate=product["base_rate"],
                      min_amount=product["min_amount"], unavailable_sources=unavailable)
    return dict(scoring=scoring, decision=decision)
