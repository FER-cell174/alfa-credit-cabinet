# Модель данных

Хранилище: PostgreSQL 16 (в Docker Compose) или SQLite (локальный запуск без Docker).
Таблицы создаются при старте API (`Base.metadata.create_all`). Заявка — центр модели.

```mermaid
erDiagram
    USER ||--o{ APPLICATION : создаёт
    COMPANY ||--o{ APPLICATION : "по ИНН"
    APPLICATION ||--o{ STATUS_HISTORY : "история переходов"
    APPLICATION ||--o{ DOCUMENT : содержит
    APPLICATION ||--o{ EXTERNAL_CHECK : "проверки"
    APPLICATION ||--o| SCORING_RESULT : оценка
    APPLICATION ||--o| DECISION : решение
    APPLICATION ||--o| OFFER : оферта

    USER { int id string email string role string name }
    COMPANY { int id string inn string name string ogrn string okved string registration_date string egrul_status }
    APPLICATION { int id int user_id string inn string product_code int amount int term_months string purpose int revenue int revenue_prev string status }
    STATUS_HISTORY { int id int application_id string from_status string to_status string actor string reason }
    DOCUMENT { int id int application_id string doc_type string filename }
    EXTERNAL_CHECK { int id int application_id string source string status json payload int attempts }
    SCORING_RESULT { int id int application_id int score string klass json factors json stop_factors }
    DECISION { int id int application_id string outcome json reasons string decided_by }
    OFFER { int id int application_id int amount int term_months float rate string status }
    AUDIT_LOG { int id string actor string action string entity int entity_id string detail }
```

Продукты не хранятся в БД: это конфигурация (`backend/app/domain/products.py`).
Пороги классов риска, премии к ставке и лимиты суммы — там же.

## Таблицы

- **users** — учётные записи; роль: `client`, `operator`, `analyst`, `admin`; пароль хранится как PBKDF2-хеш.
- **companies** — данные компании из ЕГРЮЛ/ЕГРИП (мок), создаются при обогащении.
- **applications** — заявка: продукт, сумма, срок, цель, выручка за два года, текущий статус, список недостающего.
- **status_history** — каждый переход: откуда, куда, кто, когда, причина.
- **documents** — метаданные приложенных документов (файлы не хранятся).
- **external_checks** — ответ каждого источника, статус (`ok`, `timeout`, `not_found`), число попыток.
- **scoring_results** — балл, класс, вклад каждого фактора и стоп-факторы.
- **decisions** — исход, причины, кто принял решение (`system` или почта аналитика).
- **offers** — условия оферты и статус принятия.
- **audit_log** — журнал действий: создание заявок, смены статусов.
