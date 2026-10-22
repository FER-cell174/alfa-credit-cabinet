"""Прозрачная балльная модель: 100 баллов, у каждого фактора виден вклад.

Веса и пороги — допущения MVP, не калибровались на реальных данных.
"""
from __future__ import annotations

from datetime import date

from .calc import annuity_payment
from .products import class_for_score


def _age_years(registration_date: str, today: date) -> float:
    reg = date.fromisoformat(registration_date)
    return (today - reg).days / 365.25


def _pick(value: float, steps: list[tuple[float, int]], default: int) -> int:
    """steps: [(верхняя граница, баллы), ...] по возрастанию границ."""
    for bound, pts in steps:
        if value < bound:
            return pts
    return default


def compute_score(*, amount: float, term_months: int, revenue: float, revenue_prev: float,
                  base_rate: float, egrul: dict | None, fns: dict | None, bki: dict | None,
                  today: date | None = None) -> dict:
    today = today or date.today()
    factors: list[dict] = []
    stops: list[dict] = []

    # 1. Возраст бизнеса, до 15
    if egrul:
        age = _age_years(egrul["registration_date"], today)
        pts = _pick(age, [(0.5, 0), (1, 4), (2, 8), (5, 11)], 15)
        factors.append(dict(key="business_age", label="Возраст бизнеса", points=pts, max=15,
                            note=f"{age:.1f} лет"))
    else:
        factors.append(dict(key="business_age", label="Возраст бизнеса", points=0, max=15, note="нет данных"))

    # 2. Динамика выручки, до 20
    growth = (revenue - revenue_prev) / revenue_prev if revenue_prev > 0 else 0.0
    pts = _pick(growth, [(-0.10, 0), (0.0, 6), (0.10, 12), (0.30, 16)], 20)
    factors.append(dict(key="revenue_growth", label="Динамика выручки", points=pts, max=20,
                        note=f"{growth * 100:+.0f}% к прошлому году"))

    # 3. Долговая нагрузка, до 25: (платёж по заявке + текущие обязательства) / месячная выручка
    payment = annuity_payment(amount, base_rate, term_months)
    obligations = (bki or {}).get("monthly_obligations", 0) or 0
    monthly_revenue = revenue / 12 if revenue > 0 else 0
    load = (payment + obligations) / monthly_revenue if monthly_revenue > 0 else 9.99
    pts = _pick(load, [(0.10, 25), (0.25, 19), (0.45, 14), (0.70, 7)], 0)
    factors.append(dict(key="debt_load", label="Долговая нагрузка", points=pts, max=25,
                        note=f"платежи = {load * 100:.0f}% месячной выручки"))

    # 4. Кредитная история, до 25
    hist = (bki or {}).get("status")
    hist_pts = {"clean": 25, "short_history": 17, "overdue_30": 8, "overdue_90": 0}.get(hist, 0)
    hist_note = {"clean": "без просрочек", "short_history": "короткая история",
                 "overdue_30": "просрочка до 30 дней", "overdue_90": "просрочка 90+ дней"}.get(hist, "нет данных")
    factors.append(dict(key="credit_history", label="Кредитная история", points=hist_pts, max=25, note=hist_note))

    # 5. Статус и налоговая дисциплина, до 10
    tax_pts = 10
    tax_note = "без замечаний"
    if fns:
        if fns.get("unreliable_data"):
            tax_pts, tax_note = 0, "недостоверные сведения"
        elif fns.get("tax_debt"):
            tax_pts, tax_note = 4, "есть налоговая задолженность"
    elif not egrul:
        tax_pts, tax_note = 0, "нет данных"
    factors.append(dict(key="tax_status", label="Статус и налоговая дисциплина", points=tax_pts, max=10, note=tax_note))

    # 6. Сумма к выручке, до 5
    ratio = amount / revenue if revenue > 0 else 9.99
    pts = 5 if ratio <= 0.15 else 2 if ratio <= 0.30 else 0
    factors.append(dict(key="amount_to_revenue", label="Сумма к выручке", points=pts, max=5,
                        note=f"{ratio * 100:.0f}% годовой выручки"))

    # Стоп-факторы — отказ независимо от балла
    if egrul and egrul.get("status") in ("liquidating", "bankrupt"):
        stops.append(dict(code="company_liquidating", text="Компания находится в процессе ликвидации или банкротства"))
    if hist == "overdue_90":
        stops.append(dict(code="overdue_90", text="В кредитной истории есть просрочка более 90 дней"))

    score = sum(f["points"] for f in factors)
    klass = class_for_score(score)
    return dict(score=score, klass=klass["klass"], factors=factors, stop_factors=stops,
                monthly_payment=round(payment), load=round(load, 3))
