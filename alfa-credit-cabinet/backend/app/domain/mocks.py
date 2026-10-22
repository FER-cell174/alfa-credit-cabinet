"""Смоделированные внешние источники: ЕГРЮЛ/ЕГРИП, ФНС «Прозрачный бизнес», БКИ.

Поведение определяется ИНН. Все данные синтетические. Реальные сервисы банка
и государства не вызываются.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta


class MockNotFound(Exception):
    pass


class MockTimeout(Exception):
    pass


# inn -> описание сценария
SCENARIOS: dict[str, dict] = {
    "7701000001": dict(name="ООО «Север-Строй»", age_years=8, egrul="active", fns="clean", bki="clean", obligations=0,
                       note="Стабильный бизнес, чистая история → автоодобрение"),
    "7701000002": dict(name="ООО «Ромашка-Опт»", age_years=1.5, egrul="active", fns="clean", bki="short_history", obligations=0,
                       note="Молодой бизнес, запрос выше лимита → другие условия"),
    "7701000003": dict(name="ИП Тестов А. А.", age_years=3, egrul="active", fns="clean", bki="clean", obligations=0,
                       note="Если не указать выручку → нужны данные"),
    "7701000004": dict(name="ООО «Гранит-Сервис»", age_years=2.5, egrul="active", fns="tax_debt", bki="overdue_30", obligations=100_000,
                       note="Смешанные сигналы риска → ручной разбор"),
    "7701000005": dict(name="ООО «Лотос-Трейд»", age_years=4, egrul="active", fns="clean", bki="overdue_90", obligations=250_000,
                       note="Просрочка 90+ в БКИ → отказ по стоп-фактору"),
    "7701000006": dict(name="ООО «Вектор-Логистика»", age_years=5, egrul="liquidating", fns="clean", bki="clean", obligations=0,
                       note="Ликвидация в ЕГРЮЛ → отказ по стоп-фактору"),
    "7701000007": dict(name="ООО «Тайм-Аут»", age_years=6, egrul="active", fns="clean", bki="timeout", obligations=0,
                       note="БКИ не отвечает → ручной разбор, заявка не теряется"),
}


def valid_inn(inn: str) -> bool:
    return inn.isdigit() and len(inn) in (10, 12)


def _scenario(inn: str) -> dict:
    if inn in SCENARIOS:
        return SCENARIOS[inn]
    if not valid_inn(inn):
        raise MockNotFound(inn)
    h = int(hashlib.sha256(inn.encode()).hexdigest(), 16)
    return dict(name=f"ООО «Компания {inn[-4:]}»", age_years=2 + h % 8, egrul="active", fns="clean",
                bki="clean", obligations=0, note="Типовая компания без сигналов риска")


def egrul(inn: str, today: date | None = None) -> dict:
    sc = _scenario(inn)
    today = today or date.today()
    reg = today - timedelta(days=int(sc["age_years"] * 365.25))
    return {
        "inn": inn,
        "name": sc["name"],
        "ogrn": "1" + inn.rjust(12, "0")[-12:],
        "okved": "46.90",
        "status": sc["egrul"],  # active | liquidating | bankrupt
        "registration_date": reg.isoformat(),
        "address": "г. Москва (синтетический адрес)",
    }


def fns(inn: str) -> dict:
    sc = _scenario(inn)
    return {
        "inn": inn,
        "status": sc["fns"],  # clean | tax_debt | unreliable
        "tax_debt": sc["fns"] == "tax_debt",
        "unreliable_data": sc["fns"] == "unreliable",
    }


def bki(inn: str) -> dict:
    sc = _scenario(inn)
    if sc["bki"] == "timeout":
        raise MockTimeout("БКИ не ответило вовремя")
    return {
        "inn": inn,
        "status": sc["bki"],  # clean | short_history | overdue_30 | overdue_90
        "monthly_obligations": sc["obligations"],
    }


def demo_companies() -> list[dict]:
    return [{"inn": inn, "name": s["name"], "note": s["note"]} for inn, s in SCENARIOS.items()]
