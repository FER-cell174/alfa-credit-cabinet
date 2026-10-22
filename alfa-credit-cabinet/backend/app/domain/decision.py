"""Кредитная логика: скоринг — не решение. Итог зависит от класса риска,
стоп-факторов, лимитов и доступности проверок. Исход не бинарный."""
from __future__ import annotations

from .products import RISK_CLASSES


def _risk(klass: str) -> dict:
    return next(c for c in RISK_CLASSES if c["klass"] == klass)


def _floor_amount(value: float) -> int:
    return int(value // 10_000 * 10_000)


def decide(*, klass: str, stop_factors: list[dict], amount: float, term_months: int,
           revenue: float, base_rate: float, min_amount: float, unavailable_sources: list[str]) -> dict:
    """Возвращает {outcome, reasons[{code,text}], offer|None}.

    outcome: approved | counter_offer | manual_review | rejected
    """
    if stop_factors:
        return dict(outcome="rejected", reasons=list(stop_factors), offer=None)

    if unavailable_sources:
        names = ", ".join(unavailable_sources)
        return dict(outcome="manual_review", offer=None,
                    reasons=[dict(code="source_unavailable",
                                  text=f"Внешний источник не ответил ({names}): решение передано аналитику")])

    risk = _risk(klass)

    if klass == "D":
        return dict(outcome="rejected", offer=None,
                    reasons=[dict(code="score_low", text="Оценка кредитного риска ниже допустимого порога")])

    if klass == "C":
        return dict(outcome="manual_review", offer=None,
                    reasons=[dict(code="class_c", text="Оценка риска в пограничной зоне: нужен разбор аналитиком")])

    limit = _floor_amount(revenue * risk["revenue_limit"])
    rate = round(base_rate + risk["premium"], 2)

    if klass == "A" and amount <= limit:
        return dict(outcome="approved", reasons=[dict(code="approved_a", text="Заявка одобрена на запрошенных условиях")],
                    offer=dict(amount=int(amount), term_months=term_months, rate=rate))

    reasons = []
    offer_amount = int(min(amount, limit))
    if offer_amount < min_amount:
        return dict(outcome="rejected", offer=None,
                    reasons=[dict(code="limit_too_low",
                                  text="Допустимая сумма по вашей выручке ниже минимальной для продукта")])
    if offer_amount < amount:
        reasons.append(dict(code="amount_limit",
                            text=f"Запрошенная сумма превышает {int(risk['revenue_limit'] * 100)}% годовой выручки, "
                                 f"допустимая — {offer_amount:,} ₽".replace(",", " ")))
    if risk["premium"]:
        reasons.append(dict(code="rate_premium",
                            text=f"К ставке продукта добавлена премия за риск {risk['premium']:g} п.п."))
    return dict(outcome="counter_offer", reasons=reasons,
                offer=dict(amount=offer_amount, term_months=term_months, rate=rate))
