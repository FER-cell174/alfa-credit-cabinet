import { useCallback, useEffect, useState } from "react";
import { api, rub, User } from "./api";
import { History, OfferBlock, StatusBadge, Tracker } from "./Tracker";

const SOURCE_NAMES: Record<string, string> = { egrul: "ЕГРЮЛ/ЕГРИП", fns: "ФНС «Прозрачный бизнес»", bki: "Бюро кредитных историй" };
const CHECK_STATUS: Record<string, string> = { ok: "Ответ получен", timeout: "Не ответил (таймаут)", not_found: "Не найдено" };

export default function Bank({ user }: { user: User }) {
  const [tab, setTab] = useState<"all" | "intake" | "review" | "admin">("review");
  const [openId, setOpenId] = useState<number | null>(null);
  if (openId != null) return <Card id={openId} user={user} onBack={() => setOpenId(null)} />;
  return (
    <>
      <Stats />
      <div className="tabs" role="tablist">
        <button className="tab" role="tab" aria-selected={tab === "review"} onClick={() => setTab("review")}>Ручной разбор</button>
        <button className="tab" role="tab" aria-selected={tab === "intake"} onClick={() => setTab("intake")}>Проверка и запросы данных</button>
        <button className="tab" role="tab" aria-selected={tab === "all"} onClick={() => setTab("all")}>Все заявки</button>
        {user.role === "admin" && <button className="tab" role="tab" aria-selected={tab === "admin"} onClick={() => setTab("admin")}>Журнал аудита</button>}
      </div>
      {tab === "admin" ? <Audit /> : <Queue key={tab} queue={tab} onOpen={setOpenId} />}
    </>
  );
}

function Stats() {
  const [s, setS] = useState<any>(null);
  useEffect(() => { api("GET", "/api/admin/stats").then(setS).catch(() => {}); }, []);
  if (!s) return null;
  return (
    <div className="grid">
      <div className="card"><span className="muted">В работе</span><span className="big">{s.in_progress}</span></div>
      {s.by_status.filter((x: any) => x.count > 0).map((x: any) => (
        <div className="card" key={x.status}><span className="muted">{x.label}</span><span className="big">{x.count}</span></div>
      ))}
    </div>
  );
}

function Queue({ queue, onOpen }: { queue: string; onOpen: (id: number) => void }) {
  const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => { api("GET", `/api/applications?queue=${queue}`).then(setRows).catch(() => setRows([])); }, [queue]);
  if (!rows) return <p className="muted">Загружаем очередь…</p>;
  if (rows.length === 0) return <div className="card"><h2>В очереди пусто</h2><p className="soft">Новые заявки появятся здесь после отправки клиентами.</p></div>;
  return (
    <table>
      <thead><tr><th>№</th><th>Компания</th><th>Продукт</th><th>Сумма</th><th>Статус</th><th>Обновлена</th></tr></thead>
      <tbody>
        {rows.map((a) => (
          <tr key={a.id} className="clickable" onClick={() => onOpen(a.id)}>
            <td>{a.id}</td><td>{a.company_name || a.inn || "—"}</td><td>{a.product_name ?? "—"}</td><td>{rub(a.amount)}</td>
            <td><StatusBadge status={a.status} label={a.status_label} /></td>
            <td className="muted">{new Date(a.updated_at).toLocaleString("ru-RU")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Audit() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { api("GET", "/api/admin/audit").then(setRows).catch(() => {}); }, []);
  return (
    <table>
      <thead><tr><th>Время</th><th>Кто</th><th>Действие</th><th>Объект</th><th>Детали</th></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}><td className="muted">{new Date(r.at).toLocaleString("ru-RU")}</td><td>{r.actor}</td><td>{r.action}</td>
            <td>{r.entity} № {r.entity_id}</td><td>{r.detail}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

function Card({ id, user, onBack }: { id: number; user: User; onBack: () => void }) {
  const [a, setA] = useState<any>(null);
  const [error, setError] = useState("");
  const [comment, setComment] = useState("");
  const [d, setD] = useState({ outcome: "approved", reason: "", amount: "", rate: "" });
  const load = useCallback(() => api("GET", `/api/applications/${id}`).then(setA).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);
  if (!a) return <p className="muted">{error || "Загружаем заявку…"}</p>;

  const run = async (fn: () => Promise<any>) => {
    setError("");
    try { setA(await fn()); setComment(""); } catch (e: any) { setError(e.message); }
  };
  const canRequest = ["operator", "analyst"].includes(user.role) && ["checking", "manual_review"].includes(a.status);
  const canDecide = user.role === "analyst" && a.status === "manual_review";
  const sc = a.scoring;

  return (
    <>
      <div className="row spread">
        <button className="btn ghost" onClick={onBack}>← К очередям</button>
        <StatusBadge status={a.status} label={a.status_label} />
      </div>
      <h1>Заявка № {a.id}: {a.company_name || a.inn}</h1>
      <div className="card"><Tracker status={a.status} />
        <p className="soft">{a.product_name} · {rub(a.amount)} на {a.term_months} мес. · цель: {a.purpose || "—"}</p>
        <p className="soft">Выручка: {rub(a.revenue)} (в прошлом году {rub(a.revenue_prev)}) · ИНН {a.inn}</p>
      </div>

      <div className="grid">
        <div className="card">
          <h3>Внешние проверки</h3>
          {a.checks.length === 0 && <p className="muted">Проверки ещё не выполнялись</p>}
          {a.checks.map((c: any) => (
            <div key={c.source}>
              <b>{SOURCE_NAMES[c.source]}</b>: {CHECK_STATUS[c.status]}
              {c.attempts > 1 && <span className="muted"> · попыток: {c.attempts}</span>}
              {c.payload && <div className="muted">{Object.entries(c.payload).filter(([k]) => k !== "inn").map(([k, v]) => `${k}: ${v}`).join(" · ")}</div>}
            </div>
          ))}
        </div>
        <div className="card">
          <h3>Скоринг</h3>
          {!sc && <p className="muted">Скоринг ещё не рассчитан</p>}
          {sc && (<>
            <div className="row" style={{ gap: 24 }}>
              <div><div className="muted">Балл</div><div className="big">{sc.score} / 100</div></div>
              <div><div className="muted">Класс риска</div><div className="big">{sc.klass}</div></div>
            </div>
            {sc.factors.map((f: any) => (
              <div key={f.key}>
                <div className="row spread"><span>{f.label}</span><b>{f.points} / {f.max}</b></div>
                <div className="row"><div className="meter"><div style={{ width: `${(f.points / f.max) * 100}%` }} /></div></div>
                <span className="muted">{f.note}</span>
              </div>
            ))}
            {sc.stop_factors.length > 0 && (
              <div className="error"><b>Стоп-факторы:</b><ul>{sc.stop_factors.map((s: any) => <li key={s.code}>{s.text}</li>)}</ul></div>
            )}
          </>)}
        </div>
      </div>

      {a.reasons.length > 0 && (
        <div className="card"><h3>Рекомендация системы и причины</h3>
          <ul>{a.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
          {a.decided_by && <span className="muted">Решение принял: {a.decided_by === "system" ? "система" : a.decided_by}</span>}
        </div>
      )}
      <OfferBlock offer={a.offer} />
      {error && <div className="error" role="alert">{error}</div>}

      {canRequest && (
        <div className="card">
          <h3>Запросить данные у клиента</h3>
          <label>Что нужно клиенту добавить
            <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <div><button className="btn" disabled={!comment.trim()}
            onClick={() => run(() => api("POST", `/api/applications/${id}/request-data`, { comment }))}>Запросить данные</button></div>
        </div>
      )}
      {canDecide && (
        <div className="card">
          <h3>Решение аналитика</h3>
          <label>Исход
            <select value={d.outcome} onChange={(e) => setD({ ...d, outcome: e.target.value })}>
              <option value="approved">Одобрить на запрошенных условиях</option>
              <option value="counter_offer">Предложить другие условия</option>
              <option value="rejected">Отказать</option>
            </select>
          </label>
          {d.outcome !== "rejected" && (
            <div className="row">
              <label>Сумма, ₽<input type="number" placeholder={String(a.amount)} value={d.amount} onChange={(e) => setD({ ...d, amount: e.target.value })} /></label>
              <label>Ставка, %<input type="number" step="0.5" value={d.rate} onChange={(e) => setD({ ...d, rate: e.target.value })} /></label>
            </div>
          )}
          <label>Причина (обязательно, её увидит клиент)
            <textarea rows={2} value={d.reason} onChange={(e) => setD({ ...d, reason: e.target.value })} />
          </label>
          <div><button className="btn red" disabled={!d.reason.trim()}
            onClick={() => run(() => api("POST", `/api/applications/${id}/decision`, {
              outcome: d.outcome, reason: d.reason,
              amount: d.amount ? Number(d.amount) : null, rate: d.rate ? Number(d.rate) : null,
            }))}>Принять решение</button></div>
        </div>
      )}
      <div className="card"><h3>История статусов</h3><History items={a.history} /></div>
    </>
  );
}
