"""Автомат статусов заявки. Статус меняется только через transition_allowed()."""

STATUS_LABELS = {
    "draft": "Черновик",
    "submitted": "Подана",
    "checking": "Проверка",
    "enrichment": "Обогащение данных",
    "scoring": "Скоринг",
    "decision": "Решение",
    "approved": "Одобрена",
    "counter_offer": "Другие условия",
    "needs_data": "Нужны данные",
    "manual_review": "Ручной разбор",
    "rejected": "Отказ",
    "offer_accepted": "Оферта принята",
    "signed": "Подписана (мок)",
    "disbursed": "Выдана (мок)",
    "withdrawn": "Отозвана",
    "expired": "Истёк срок",
}

TRANSITIONS = {
    "draft": {"submitted", "withdrawn"},
    "submitted": {"checking"},
    "checking": {"needs_data", "enrichment", "rejected"},
    "needs_data": {"submitted", "withdrawn", "expired"},
    "enrichment": {"scoring", "manual_review"},
    "scoring": {"decision"},
    "decision": {"approved", "counter_offer", "manual_review", "rejected"},
    "manual_review": {"approved", "counter_offer", "rejected", "needs_data"},
    "approved": {"offer_accepted", "withdrawn", "expired"},
    "counter_offer": {"offer_accepted", "withdrawn", "expired"},
    "offer_accepted": {"signed", "withdrawn"},
    "signed": {"disbursed"},
    "rejected": set(),
    "disbursed": set(),
    "withdrawn": set(),
    "expired": set(),
}

FINAL_STATUSES = {s for s, nxt in TRANSITIONS.items() if not nxt}

# Очереди рабочего места банка
QUEUES = {
    "intake": ["checking", "needs_data"],
    "review": ["manual_review"],
}


class InvalidTransition(Exception):
    pass


def transition_allowed(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def ensure_transition(current: str, target: str) -> None:
    if not transition_allowed(current, target):
        raise InvalidTransition(
            f"Переход «{STATUS_LABELS.get(current, current)}» → "
            f"«{STATUS_LABELS.get(target, target)}» недопустим"
        )


def next_step_hint(status: str) -> str:
    """Подсказка клиенту «что дальше» для каждого статуса."""
    return {
        "draft": "Заполните заявку и отправьте её в банк.",
        "submitted": "Заявка принята, начинаем проверку.",
        "checking": "Банк проверяет полноту и корректность данных.",
        "enrichment": "Банк сверяет данные с внешними источниками.",
        "scoring": "Идёт оценка кредитного риска.",
        "decision": "Банк принимает решение.",
        "approved": "Заявка одобрена. Примите оферту, чтобы перейти к подписанию.",
        "counter_offer": "Банк готов предложить другие условия. Посмотрите их и примите оферту или отзовите заявку.",
        "needs_data": "Банку нужны дополнительные данные. Дополните заявку и отправьте её снова.",
        "manual_review": "Заявку рассматривает кредитный аналитик. От вас ничего не требуется.",
        "rejected": "Банк не может одобрить заявку. Причины указаны ниже.",
        "offer_accepted": "Оферта принята. Подпишите договор.",
        "signed": "Договор подписан. Деньги будут зачислены на счёт.",
        "disbursed": "Деньги выданы (в прототипе операция моделируется).",
        "withdrawn": "Заявка отозвана.",
        "expired": "Срок рассмотрения заявки истёк.",
    }[status]
