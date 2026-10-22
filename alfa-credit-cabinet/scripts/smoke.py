#!/usr/bin/env python3
"""Сквозная проверка работающего API по 7 тестовым сценариям. Только стандартная библиотека.

    python scripts/smoke.py [http://localhost:8080]

Код возврата 0 — все сценарии прошли.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
TRANSIENT = {"submitted", "checking", "enrichment", "scoring", "decision"}
failures: list[str] = []


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode()[:300]}")


def login(email, password):
    return call("POST", "/api/auth/login", dict(email=email, password=password))["token"]


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def wait_settled(app_id, token):
    for _ in range(40):
        a = call("GET", f"/api/applications/{app_id}", token=token)
        if a["status"] not in TRANSIENT:
            return a
        time.sleep(0.25)
    raise SystemExit(f"заявка {app_id} зависла в статусе {a['status']}")


def new_app(token, inn, **kw):
    body = dict(product_code="working_capital", amount=5_000_000, term_months=12, purpose="Закупка товара",
                inn=inn, revenue=14_000_000, revenue_prev=13_000_000)
    body.update(kw)
    a = call("POST", "/api/applications", body, token)
    call("POST", f"/api/applications/{a['id']}/submit", token=token)
    return a["id"]


client = login("client@demo.test", "client123")
operator = login("operator@demo.test", "operator123")
analyst = login("analyst@demo.test", "analyst123")

print("1. Север-Строй: автоодобрение, затем принятие оферты, подписание, выдача")
a = wait_settled(new_app(client, "7701000001", revenue=60_000_000, revenue_prev=50_000_000), client)
check("статус «Одобрена»", a["status"] == "approved", a["status"])
call("POST", f"/api/applications/{a['id']}/accept-offer", token=client)
a = call("POST", f"/api/applications/{a['id']}/sign", token=client)
check("статус «Выдана»", a["status"] == "disbursed", a["status"])
check("в истории есть переходы", len(a["history"]) >= 8, str(len(a["history"])))

print("2. Ромашка-Опт: другие условия")
a = wait_settled(new_app(client, "7701000002"), client)
check("статус «Другие условия»", a["status"] == "counter_offer", a["status"])
check("оферта 3,5 млн под 21%", a["offer"] and a["offer"]["amount"] == 3_500_000 and a["offer"]["rate"] == 21.0,
      str(a["offer"]))
check("причины видны клиенту", len(a["reasons"]) >= 1)

print("3. ИП Тестов: нужны данные, затем доработка")
a = wait_settled(new_app(client, "7701000003", revenue=None, revenue_prev=None), client)
check("статус «Нужны данные»", a["status"] == "needs_data", a["status"])
check("клиент видит, чего не хватает", any("Выручка" in m for m in a["missing"]), str(a["missing"]))
call("PUT", f"/api/applications/{a['id']}", dict(revenue=20_000_000, revenue_prev=18_000_000), client)
call("POST", f"/api/applications/{a['id']}/submit", token=client)
a = wait_settled(a["id"], client)
check("после доработки заявка пошла дальше", a["status"] != "needs_data", a["status"])

print("4. Гранит-Сервис: ручной разбор и решение аналитика")
a = wait_settled(new_app(client, "7701000004", revenue=20_000_000, revenue_prev=22_000_000), client)
check("статус «Ручной разбор»", a["status"] == "manual_review", a["status"])
bank = call("GET", f"/api/applications/{a['id']}", token=analyst)
check("аналитик видит скоринг 45 баллов, класс C", bank["scoring"]["score"] == 45 and bank["scoring"]["klass"] == "C",
      str(bank.get("scoring")))
check("в очереди ручного разбора", any(x["id"] == a["id"] for x in call("GET", "/api/applications?queue=review", token=analyst)))
a = call("POST", f"/api/applications/{a['id']}/decision",
         dict(outcome="counter_offer", reason="Снижаем сумму из-за налоговой задолженности", amount=3_000_000, rate=24.0),
         analyst)
check("решение аналитика применено", a["status"] == "counter_offer" and a["offer"]["amount"] == 3_000_000, a["status"])

print("5. Лотос-Трейд: отказ по стоп-фактору (просрочка 90+)")
a = wait_settled(new_app(client, "7701000005", revenue=60_000_000, revenue_prev=50_000_000), client)
check("статус «Отказ»", a["status"] == "rejected", a["status"])
check("причина понятна клиенту", any("90" in r for r in a["reasons"]), str(a["reasons"]))

print("6. Вектор-Логистика: отказ по стоп-фактору (ликвидация)")
a = wait_settled(new_app(client, "7701000006", revenue=60_000_000, revenue_prev=50_000_000), client)
check("статус «Отказ»", a["status"] == "rejected", a["status"])

print("7. Тайм-Аут: БКИ не отвечает, заявка не теряется")
a = wait_settled(new_app(client, "7701000007", revenue=60_000_000, revenue_prev=50_000_000), client)
check("статус «Ручной разбор»", a["status"] == "manual_review", a["status"])

print("Права доступа")
try:
    call("POST", "/api/applications", dict(), operator)
    check("оператор не создаёт заявки", False)
except SystemExit as e:
    check("оператор не создаёт заявки", "403" in str(e), str(e))

print()
if failures:
    print(f"ПРОВАЛЕНО: {len(failures)} — " + "; ".join(failures))
    sys.exit(1)
print("Все сценарии прошли")
