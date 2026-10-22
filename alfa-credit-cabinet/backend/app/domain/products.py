"""Кредитные продукты — это конфигурация, а не код. Все условия синтетические."""

PRODUCTS = [
    dict(code="working_capital", name="Оборотный кредит",
         purpose="Закупки, зарплаты, кассовые разрывы",
         min_amount=300_000, max_amount=15_000_000, min_term=3, max_term=24, base_rate=18.0,
         condition="Без залога до 3 млн ₽"),
    dict(code="investment", name="Инвестиционный кредит",
         purpose="Оборудование, запуск нового направления",
         min_amount=1_000_000, max_amount=50_000_000, min_term=12, max_term=60, base_rate=16.0,
         condition="Залог обязателен"),
    dict(code="overdraft", name="Овердрафт",
         purpose="Краткосрочные разрывы на счёте",
         min_amount=100_000, max_amount=5_000_000, min_term=1, max_term=12, base_rate=20.0,
         condition="Транши до 30 дней"),
]

PRODUCTS_BY_CODE = {p["code"]: p for p in PRODUCTS}

# Классы риска: нижняя граница балла, премия к ставке (п.п.), лимит суммы как доля годовой выручки
RISK_CLASSES = [
    dict(klass="A", min_score=75, premium=0.0, revenue_limit=0.40),
    dict(klass="B", min_score=55, premium=3.0, revenue_limit=0.25),
    dict(klass="C", min_score=40, premium=6.0, revenue_limit=0.15),
    dict(klass="D", min_score=0, premium=None, revenue_limit=0.0),
]


def class_for_score(score: int) -> dict:
    for c in RISK_CLASSES:
        if score >= c["min_score"]:
            return c
    return RISK_CLASSES[-1]
