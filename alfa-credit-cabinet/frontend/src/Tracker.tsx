import { rub } from "./api";

// Основной путь заявки; статусы вне пути (нужны данные, ручной разбор) показываются на текущем шаге
const STEPS = [
  { key: "submitted", label: "Подана" },
  { key: "checking", label: "Проверка" },
  { key: "enrichment", label: "Обогащение" },
  { key: "scoring", label: "Скоринг" },
  { key: "decision", label: "Решение" },
  { key: "result", label: "Результат" },
];

function currentIndex(status: string): number {
  switch (status) {
    case "draft": return -1;
    case "submitted": return 0;
    case "checking": case "needs_data": return 1;
    case "enrichment": return 2;
    case "scoring": return 3;
    case "decision": case "manual_review": return 4;
    default: return 5;
  }
}

export function StatusBadge({ status, label }: { status: string; label: string }) {
  return <span className={`badge ${status}`}>{label}</span>;
}

export function Tracker({ status }: { status: string }) {
  const cur = currentIndex(status);
  return (
    <div className="steps" role="list" aria-label="Этапы рассмотрения заявки">
      {STEPS.map((s, i) => (
        <div key={s.key} role="listitem" className={`step ${i < cur ? "done" : i === cur ? "current" : ""}`}
          aria-current={i === cur ? "step" : undefined}>
          <div className="bar" />
          <span>{s.label}</span>
        </div>
      ))}
    </div>
  );
}

export function History({ items }: { items: any[] }) {
  return (
    <ul className="timeline">
      {items.map((h, i) => (
        <li key={i}>
          <b>{h.to_label}</b>{" "}
          <span className="muted">
            {new Date(h.at).toLocaleString("ru-RU")} · {h.actor === "system" ? "система" : h.actor}
          </span>
          {h.reason && <div className="soft">{h.reason}</div>}
        </li>
      ))}
    </ul>
  );
}

export function OfferBlock({ offer }: { offer: any }) {
  if (!offer) return null;
  return (
    <div className="card">
      <h3>Условия оферты</h3>
      <div className="row" style={{ gap: 32 }}>
        <div><div className="muted">Сумма</div><div className="big">{rub(offer.amount)}</div></div>
        <div><div className="muted">Срок</div><div className="big">{offer.term_months} мес.</div></div>
        <div><div className="muted">Ставка</div><div className="big">{offer.rate}%</div></div>
      </div>
    </div>
  );
}
