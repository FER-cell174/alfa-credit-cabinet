"""Сервисный слой: смена статусов, конвейер обработки заявки, действия клиента и банка."""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import adapters
from .db import SessionLocal
from .domain.pipeline import enrich, evaluate, validate
from .domain.products import PRODUCTS_BY_CODE
from .domain.statemachine import STATUS_LABELS, InvalidTransition, ensure_transition, next_step_hint
from .models import (Application, AuditLog, Company, Decision, ExternalCheck, Offer, ScoringResult, StatusHistory, User)

log = logging.getLogger("pipeline")


def audit(db: Session, actor: str, action: str, entity: str, entity_id: int | None, detail: str | None = None):
    db.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=entity_id, detail=detail))


def change_status(db: Session, app: Application, to: str, actor: str, reason: str | None = None) -> None:
    """Единственное место, где меняется статус. Каждый переход пишется в историю и аудит."""
    try:
        ensure_transition(app.status, to)
    except InvalidTransition as e:
        raise HTTPException(409, str(e))
    db.add(StatusHistory(application_id=app.id, from_status=app.status, to_status=to, actor=actor, reason=reason))
    audit(db, actor, "status_change", "application", app.id, f"{app.status} -> {to}")
    app.status = to


def app_data(app: Application) -> dict:
    return dict(product_code=app.product_code, amount=app.amount, term_months=app.term_months, purpose=app.purpose,
                inn=app.inn, revenue=app.revenue, revenue_prev=app.revenue_prev, company_name=app.company_name)


# ---------- Клиент ----------

def own_application(db: Session, app_id: int, user: User) -> Application:
    app = db.get(Application, app_id)
    if not app or (user.role == "client" and app.user_id != user.id):
        raise HTTPException(404, "Заявка не найдена")
    return app


def submit_application(db: Session, app: Application, actor: str) -> bool:
    """Отправка заявки. Повторный вызов на уже отправленной заявке ничего не меняет (идемпотентно).
    Возвращает True, если конвейер нужно запустить."""
    if app.status not in ("draft", "needs_data"):
        return False
    product = PRODUCTS_BY_CODE.get(app.product_code or "")
    v = validate(app_data(app), product)
    if v["errors"]:
        raise HTTPException(422, "; ".join(v["errors"]))
    change_status(db, app, "submitted", actor)
    app.missing = None
    db.commit()
    return True


def withdraw(db: Session, app: Application, actor: str) -> None:
    change_status(db, app, "withdrawn", actor)
    db.commit()


def accept_offer(db: Session, app: Application, actor: str) -> None:
    if app.status not in ("approved", "counter_offer") or not app.offer:
        raise HTTPException(409, "Для этой заявки нет оферты, которую можно принять")
    change_status(db, app, "offer_accepted", actor)
    app.offer.status = "accepted"
    db.commit()


def sign_and_disburse(db: Session, app: Application, actor: str) -> None:
    """Подписание и выдача моделируются: реальных операций нет."""
    change_status(db, app, "signed", actor, "Подписание договора (мок)")
    change_status(db, app, "disbursed", "system", "Зачисление средств (мок)")
    db.commit()


# ---------- Конвейер ----------

def run_pipeline(app_id: int) -> None:
    """Фоновая обработка отправленной заявки. Безопасна для повторного запуска."""
    db = SessionLocal()
    try:
        app = db.get(Application, app_id)
        if not app or app.status != "submitted":
            return
        _pipeline(db, app)
    except Exception:  # сбой конвейера не должен терять заявку: отправляем на ручной разбор
        log.exception("pipeline failed for application %s", app_id)
        db.rollback()
        app = db.get(Application, app_id)
        if app and app.status in ("submitted", "checking", "enrichment", "scoring", "decision"):
            _fail_to_manual(db, app)
    finally:
        db.close()


def _fail_to_manual(db: Session, app: Application) -> None:
    # Из промежуточных статусов в ручной разбор ведут только enrichment и decision
    if app.status == "submitted":
        change_status(db, app, "checking", "system")
    if app.status == "checking":
        change_status(db, app, "enrichment", "system")
    if app.status == "enrichment":
        change_status(db, app, "manual_review", "system", "Сбой обработки: заявка передана аналитику")
    elif app.status == "scoring":
        change_status(db, app, "decision", "system")
    if app.status == "decision":
        change_status(db, app, "manual_review", "system", "Сбой обработки: заявка передана аналитику")
    db.commit()


def _pipeline(db: Session, app: Application) -> None:
    product = PRODUCTS_BY_CODE[app.product_code]
    data = app_data(app)

    # 1. Проверка полноты и корректности
    change_status(db, app, "checking", "system")
    v = validate(data, product)
    if v["missing"] or v["errors"]:
        app.missing = v["missing_labels"] + v["errors"]
        change_status(db, app, "needs_data", "system", "Не хватает данных: " + "; ".join(app.missing))
        db.commit()
        return
    db.commit()

    # 2. Обогащение данными из источников
    change_status(db, app, "enrichment", "system")
    checks = enrich(app.inn, adapters.get_fetchers())
    app.checks.clear()
    for c in checks.values():
        app.checks.append(ExternalCheck(source=c["source"], status=c["status"], payload=c["payload"],
                                        error=c["error"], attempts=c["attempts"]))
    egrul = checks["egrul"]["payload"]
    if egrul:
        company = db.query(Company).filter_by(inn=app.inn).one_or_none() or Company(inn=app.inn, name=egrul["name"])
        company.name, company.ogrn, company.okved = egrul["name"], egrul["ogrn"], egrul["okved"]
        company.registration_date, company.egrul_status = egrul["registration_date"], egrul["status"]
        db.add(company)
        db.flush()
        app.company_id = company.id
    db.commit()

    # 3. Скоринг
    change_status(db, app, "scoring", "system")
    result = evaluate(data, product, checks)
    sc = result["scoring"]
    if app.scoring:
        db.delete(app.scoring)
        db.flush()
    app.scoring = ScoringResult(score=sc["score"], klass=sc["klass"], factors=sc["factors"],
                                stop_factors=sc["stop_factors"])
    db.commit()

    # 4. Решение
    change_status(db, app, "decision", "system")
    d = result["decision"]
    if app.decision:
        db.delete(app.decision)
        db.flush()
    app.decision = Decision(outcome=d["outcome"], reasons=d["reasons"], decided_by="system")
    if app.offer:
        db.delete(app.offer)
        db.flush()
    if d["offer"]:
        app.offer = Offer(**d["offer"])
    reason = "; ".join(r["text"] for r in d["reasons"])
    change_status(db, app, d["outcome"], "system", reason)
    db.commit()


# ---------- Банк ----------

def request_data(db: Session, app: Application, actor: str, comment: str) -> None:
    if not comment.strip():
        raise HTTPException(422, "Опишите, какие данные нужны клиенту")
    app.missing = [comment.strip()]
    change_status(db, app, "needs_data", actor, comment.strip())
    db.commit()


def analyst_decision(db: Session, app: Application, actor: str, outcome: str, reason: str,
                     amount: int | None, rate: float | None) -> None:
    if app.status != "manual_review":
        raise HTTPException(409, "Решение принимается только по заявкам в ручном разборе")
    if outcome not in ("approved", "counter_offer", "rejected"):
        raise HTTPException(422, "Недопустимый исход решения")
    if not reason.strip():
        raise HTTPException(422, "Причина решения обязательна")
    product = PRODUCTS_BY_CODE[app.product_code]
    if outcome != "rejected":
        offer_amount = amount or app.amount
        if not (product["min_amount"] <= offer_amount <= product["max_amount"]):
            raise HTTPException(422, "Сумма вне допустимых пределов продукта")
        offer_rate = rate if rate is not None else product["base_rate"]
        if app.offer:
            db.delete(app.offer)
            db.flush()
        app.offer = Offer(amount=offer_amount, term_months=app.term_months, rate=offer_rate)
    if app.decision:
        db.delete(app.decision)
        db.flush()
    app.decision = Decision(outcome=outcome, reasons=[dict(code="analyst", text=reason.strip())], decided_by=actor)
    change_status(db, app, outcome, actor, reason.strip())
    db.commit()


# ---------- Представления ----------

def client_reasons(app: Application) -> list[str]:
    if app.decision:
        return [r["text"] for r in app.decision.reasons]
    return []


def application_view(app: Application, role: str, db: Session | None = None) -> dict:
    product = PRODUCTS_BY_CODE.get(app.product_code or "")
    view = dict(
        id=app.id, status=app.status, status_label=STATUS_LABELS[app.status], next_step=next_step_hint(app.status),
        product_code=app.product_code, product_name=product["name"] if product else None,
        inn=app.inn, company_name=app.company_name, amount=app.amount, term_months=app.term_months,
        purpose=app.purpose, revenue=app.revenue, revenue_prev=app.revenue_prev, missing=app.missing or [],
        created_at=app.created_at.isoformat(), updated_at=app.updated_at.isoformat(),
        reasons=client_reasons(app),
        offer=dict(amount=app.offer.amount, term_months=app.offer.term_months, rate=app.offer.rate,
                   status=app.offer.status) if app.offer else None,
        documents=[dict(id=d.id, doc_type=d.doc_type, filename=d.filename) for d in app.documents],
        history=[dict(from_status=h.from_status, to_status=h.to_status,
                      to_label=STATUS_LABELS[h.to_status], actor=h.actor, reason=h.reason, at=h.at.isoformat())
                 for h in app.history],
    )
    if role != "client":
        view["checks"] = [dict(source=c.source, status=c.status, payload=c.payload, error=c.error,
                               attempts=c.attempts, at=c.at.isoformat()) for c in app.checks]
        view["scoring"] = dict(score=app.scoring.score, klass=app.scoring.klass, factors=app.scoring.factors,
                               stop_factors=app.scoring.stop_factors) if app.scoring else None
        view["decided_by"] = app.decision.decided_by if app.decision else None
    return view
