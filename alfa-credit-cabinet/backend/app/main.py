from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import adapters, services
from .config import SEED_ON_START
from .db import Base, SessionLocal, engine, get_db
from .domain import mocks
from .domain.products import PRODUCTS, PRODUCTS_BY_CODE
from .domain.statemachine import FINAL_STATUSES, QUEUES, STATUS_LABELS, TRANSITIONS
from .models import Application, AuditLog, Document, StatusHistory, User
from .security import current_user, make_token, require_roles, verify_password
from .seed import seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    if SEED_ON_START:
        with SessionLocal() as db:
            seed(db)
    yield


app = FastAPI(
    title="Умный кредитный кабинет предпринимателя",
    version="1.0.0",
    description="API прототипа цифрового кредитного конвейера для малого и микробизнеса. Все данные синтетические.",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

BANK_ROLES = ("operator", "analyst", "admin")


# ---------- Схемы ----------

class LoginIn(BaseModel):
    email: str
    password: str


class ApplicationIn(BaseModel):
    product_code: str | None = None
    inn: str | None = None
    company_name: str | None = None
    amount: int | None = Field(default=None, gt=0)
    term_months: int | None = Field(default=None, gt=0)
    purpose: str | None = None
    revenue: int | None = Field(default=None, ge=0)
    revenue_prev: int | None = Field(default=None, ge=0)


class DocumentIn(BaseModel):
    doc_type: str
    filename: str


class RequestDataIn(BaseModel):
    comment: str


class DecisionIn(BaseModel):
    outcome: str  # approved | counter_offer | rejected
    reason: str
    amount: int | None = None
    rate: float | None = None


# ---------- Служебное ----------

@app.get("/api/health", tags=["service"])
def health():
    return {"status": "ok"}


@app.get("/api/demo/companies", tags=["service"], summary="Тестовые компании и ожидаемые исходы")
def demo_companies():
    return mocks.demo_companies()


# ---------- Вход ----------

@app.post("/api/auth/login", tags=["auth"])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Неверная почта или пароль")
    return dict(token=make_token(user), user=dict(id=user.id, name=user.name, role=user.role, email=user.email))


@app.get("/api/me", tags=["auth"])
def me(user: User = Depends(current_user)):
    return dict(id=user.id, name=user.name, role=user.role, email=user.email)


# ---------- Продукты и компании ----------

@app.get("/api/products", tags=["catalog"])
def products(user: User = Depends(current_user)):
    return PRODUCTS


@app.get("/api/companies/lookup", tags=["catalog"], summary="Данные компании по ИНН (ЕГРЮЛ/ЕГРИП, мок)")
def company_lookup(inn: str, user: User = Depends(current_user)):
    try:
        return adapters.get_fetchers()["egrul"](inn)
    except mocks.MockNotFound:
        raise HTTPException(404, "Компания с таким ИНН не найдена")
    except mocks.MockTimeout:
        raise HTTPException(504, "Сервис ЕГРЮЛ не ответил, введите данные вручную")


# ---------- Заявки (клиент) ----------

def _apply(app_obj: Application, body: ApplicationIn):
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "product_code" and value and value not in PRODUCTS_BY_CODE:
            raise HTTPException(422, "Неизвестный продукт")
        setattr(app_obj, field, value)


@app.post("/api/applications", tags=["applications"], status_code=201, summary="Создать черновик заявки")
def create_application(body: ApplicationIn, db: Session = Depends(get_db), user: User = Depends(require_roles("client"))):
    a = Application(user_id=user.id, status="draft")
    _apply(a, body)
    db.add(a)
    db.flush()
    services.audit(db, user.email, "create", "application", a.id)
    db.add(StatusHistory(application_id=a.id, from_status=None, to_status="draft", actor=user.email))
    db.commit()
    return services.application_view(a, user.role)


@app.put("/api/applications/{app_id}", tags=["applications"], summary="Изменить черновик или дополнить заявку")
def update_application(app_id: int, body: ApplicationIn, db: Session = Depends(get_db),
                       user: User = Depends(require_roles("client"))):
    a = services.own_application(db, app_id, user)
    if a.status not in ("draft", "needs_data"):
        raise HTTPException(409, "Заявку можно менять только в черновике или когда банк запросил данные")
    _apply(a, body)
    db.commit()
    return services.application_view(a, user.role)


@app.post("/api/applications/{app_id}/submit", tags=["applications"], summary="Отправить заявку в банк")
def submit_application(app_id: int, background: BackgroundTasks, db: Session = Depends(get_db),
                       user: User = Depends(require_roles("client"))):
    a = services.own_application(db, app_id, user)
    if services.submit_application(db, a, user.email):
        background.add_task(services.run_pipeline, a.id)
    return services.application_view(a, user.role)


@app.post("/api/applications/{app_id}/documents", tags=["applications"], status_code=201,
          summary="Зафиксировать приложенный документ (метаданные)")
def add_document(app_id: int, body: DocumentIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles("client"))):
    a = services.own_application(db, app_id, user)
    if a.status not in ("draft", "needs_data"):
        raise HTTPException(409, "Документы можно добавлять в черновике или по запросу банка")
    db.add(Document(application_id=a.id, doc_type=body.doc_type, filename=body.filename))
    db.commit()
    return services.application_view(a, user.role)


@app.post("/api/applications/{app_id}/withdraw", tags=["applications"], summary="Отозвать заявку")
def withdraw(app_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("client"))):
    a = services.own_application(db, app_id, user)
    services.withdraw(db, a, user.email)
    return services.application_view(a, user.role)


@app.post("/api/applications/{app_id}/accept-offer", tags=["applications"], summary="Принять оферту")
def accept_offer(app_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("client"))):
    a = services.own_application(db, app_id, user)
    services.accept_offer(db, a, user.email)
    return services.application_view(a, user.role)


@app.post("/api/applications/{app_id}/sign", tags=["applications"],
          summary="Подписать договор; подписание и выдача моделируются")
def sign(app_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("client"))):
    a = services.own_application(db, app_id, user)
    services.sign_and_disburse(db, a, user.email)
    return services.application_view(a, user.role)


# ---------- Заявки (общие) ----------

@app.get("/api/applications", tags=["applications"], summary="Список заявок: свои (клиент) или очередь (банк)")
def list_applications(queue: str = Query("all", pattern="^(all|intake|review)$"), db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    q = db.query(Application)
    if user.role == "client":
        q = q.filter(Application.user_id == user.id)
    elif queue != "all":
        q = q.filter(Application.status.in_(QUEUES[queue]))
    rows = q.order_by(Application.id.desc()).all()
    return [services.application_view(a, user.role) for a in rows]


@app.get("/api/applications/{app_id}", tags=["applications"], summary="Карточка заявки")
def get_application(app_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = services.own_application(db, app_id, user)
    return services.application_view(a, user.role)


# ---------- Банк ----------

@app.post("/api/applications/{app_id}/request-data", tags=["bank"], summary="Запросить у клиента данные")
def request_data(app_id: int, body: RequestDataIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles("operator", "analyst"))):
    a = services.own_application(db, app_id, user)
    services.request_data(db, a, user.email, body.comment)
    return services.application_view(a, user.role)


@app.post("/api/applications/{app_id}/decision", tags=["bank"], summary="Решение аналитика по заявке из ручного разбора")
def decision(app_id: int, body: DecisionIn, db: Session = Depends(get_db),
             user: User = Depends(require_roles("analyst"))):
    a = services.own_application(db, app_id, user)
    services.analyst_decision(db, a, user.email, body.outcome, body.reason, body.amount, body.rate)
    return services.application_view(a, user.role)


@app.get("/api/admin/audit", tags=["bank"], summary="Журнал аудита")
def audit_log(limit: int = Query(100, le=500), db: Session = Depends(get_db),
              user: User = Depends(require_roles("admin"))):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [dict(at=r.at.isoformat(), actor=r.actor, action=r.action, entity=r.entity,
                 entity_id=r.entity_id, detail=r.detail) for r in rows]


@app.get("/api/admin/stats", tags=["bank"], summary="Загрузка очередей и воронка по статусам")
def stats(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator", "analyst"))):
    counts = {s: 0 for s in STATUS_LABELS}
    for (status,) in db.query(Application.status).all():
        counts[status] += 1
    return dict(by_status=[dict(status=s, label=STATUS_LABELS[s], count=c) for s, c in counts.items()],
                in_progress=sum(c for s, c in counts.items() if s not in FINAL_STATUSES))


@app.get("/api/meta/transitions", tags=["service"], summary="Допустимые переходы автомата статусов")
def transitions():
    return {s: sorted(t) for s, t in TRANSITIONS.items()}
