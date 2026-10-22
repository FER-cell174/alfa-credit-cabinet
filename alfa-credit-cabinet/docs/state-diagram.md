# Диаграмма состояний заявки

Статус меняется только через автомат переходов (`backend/app/domain/statemachine.py`).
Недопустимый переход возвращает ошибку 409. Каждый переход пишется в историю статусов и журнал аудита.

```mermaid
stateDiagram-v2
    [*] --> draft: клиент создаёт заявку
    draft --> submitted: клиент отправляет
    draft --> withdrawn
    submitted --> checking: конвейер стартует
    checking --> needs_data: не хватает данных
    checking --> enrichment: данные полны
    checking --> rejected
    needs_data --> submitted: клиент дополнил заявку
    needs_data --> withdrawn
    needs_data --> expired
    enrichment --> scoring: источники опрошены
    enrichment --> manual_review: сбой обработки
    scoring --> decision
    decision --> approved: класс A, сумма в лимите
    decision --> counter_offer: класс B или сумма выше лимита
    decision --> manual_review: класс C или источник недоступен
    decision --> rejected: стоп-фактор или класс D
    manual_review --> approved: решение аналитика
    manual_review --> counter_offer: решение аналитика
    manual_review --> rejected: решение аналитика
    manual_review --> needs_data: запрос данных
    approved --> offer_accepted: клиент принимает оферту
    counter_offer --> offer_accepted
    approved --> withdrawn
    counter_offer --> withdrawn
    approved --> expired
    counter_offer --> expired
    offer_accepted --> signed: подписание (мок)
    offer_accepted --> withdrawn
    signed --> disbursed: выдача (мок)
    rejected --> [*]
    disbursed --> [*]
    withdrawn --> [*]
    expired --> [*]
```

## Статусы

| Код | Название для клиента | Что означает |
|---|---|---|
| `draft` | Черновик | Заявка заполняется, банк её ещё не видит |
| `submitted` | Подана | Заявка отправлена, ждёт запуска конвейера |
| `checking` | Проверка | Проверка полноты и корректности данных |
| `enrichment` | Обогащение данных | Опрос ЕГРЮЛ/ЕГРИП, ФНС, БКИ |
| `scoring` | Скоринг | Расчёт балла и класса риска |
| `decision` | Решение | Применение кредитной логики |
| `approved` | Одобрена | Одобрение на запрошенных условиях |
| `counter_offer` | Другие условия | Банк предлагает иную сумму, срок или ставку |
| `needs_data` | Нужны данные | Клиент должен дополнить заявку |
| `manual_review` | Ручной разбор | Заявку рассматривает аналитик |
| `rejected` | Отказ | Отказ с причинами |
| `offer_accepted` | Оферта принята | Клиент принял условия |
| `signed` | Подписана (мок) | Договор подписан, операция моделируется |
| `disbursed` | Выдана (мок) | Деньги выданы, операция моделируется |
| `withdrawn` | Отозвана | Клиент отозвал заявку |
| `expired` | Истёк срок | Срок рассмотрения вышел |

Финальные статусы: `rejected`, `disbursed`, `withdrawn`, `expired`.

Статус `expired` в прототипе предусмотрен автоматом, но автоматического истечения срока нет.
