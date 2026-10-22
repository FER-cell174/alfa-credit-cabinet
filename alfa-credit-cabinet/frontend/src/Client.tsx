import { useCallback, useEffect, useState } from "react";
import { annuity, api, rub, TRANSIENT } from "./api";
import { History, OfferBlock, StatusBadge, Tracker } from "./Tracker";

type Product = {
  code: string; name: string; purpose: string; min_amount: number; max_amount: number;
  min_term: number; max_term: number; base_rate: number; condition: string;
};

export default function Client() {
  const [tab, setTab] = useState<"catalog" | "apps">("catalog");
  const [wizard, setWizard] = useState<{ product?: Product; amount?: number; term?: number; app?: any } | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  if (wizard) {
    return (
      <Wizard {...wizard}
        onCancel={() => setWizard(null)}
        onDone={(id) => { setWizard(null); setOpenId(id); setTab("apps"); }} />
    );
  }
  if (openId != null) {
    return <ApplicationPage id={openId} onBack={() => setOpenId(null)} onEdit={(app) => setWizard({ app })} />;
  }
  return (
    <>
      <div className="tabs" role="tablist">
        <button className="tab" role="tab" aria-selected={tab === "catalog"} onClick={() => setTab("catalog")}>Подобрать кредит</button>
        <button className="tab" role="tab" aria-selected={tab === "apps"} onClick={() => setTab("apps")}>Мои заявки</button>
      </div>
      {tab === "catalog"
        ? <Catalog onApply={(product, amount, term) => setWizard({ product, amount, term })} />
        : <MyApplications onOpen={setOpenId} />}
    </>
  );
}

function Catalog({ onApply }: { onApply: (p: Product, amount: number, term: number) => void }) {
  const [products, setProducts] = useState<Product[]>([]);
  useEffect(() => { api("GET", "/api/products").then(setProducts).catch(() => {}); }, []);
  return (
    <>
      <div><h1>Какой кредит нужен вашему бизнесу</h1>
        <p className="soft">Выберите продукт и прикиньте платёж. Итоговую ставку банк назовёт после проверки заявки.</p></div>
      <div className="grid">
        {products.map((p) => <ProductCard key={p.code} p={p} onApply={onApply} />)}
      </div>
    </>
  );
}

function ProductCard({ p, onApply }: { p: Product; onApply: (p: Product, a: number, t: number) => void }) {
  const [amount, setAmount] = useState(Math.min(Math.max(1_000_000, p.min_amount), p.max_amount));
  const [term, setTerm] = useState(Math.min(Math.max(12, p.min_term), p.max_term));
  const ok = amount >= p.min_amount && amount <= p.max_amount && term >= p.min_term && term <= p.max_term;
  return (
    <div className="card">
      <h2>{p.name}</h2>
      <p className="soft">{p.purpose}</p>
      <p className="muted">От {rub(p.min_amount)} до {rub(p.max_amount)} · {p.min_term}–{p.max_term} мес. · от {p.base_rate}% · {p.condition}</p>
      <label>Сумма, ₽
        <input type="number" value={amount} min={p.min_amount} max={p.max_amount} step={100000}
          onChange={(e) => setAmount(Number(e.target.value))} />
      </label>
      <label>Срок, месяцев
        <input type="number" value={term} min={p.min_term} max={p.max_term} onChange={(e) => setTerm(Number(e.target.value))} />
      </label>
      {ok
        ? <div className="notice">Примерный платёж по ставке {p.base_rate}%: <b>{rub(annuity(amount, p.base_rate, term))}</b> в месяц</div>
        : <div className="warn">Сумма и срок должны быть в пределах продукта</div>}
      <button className="btn red" disabled={!ok} onClick={() => onApply(p, amount, term)}>Подать заявку</button>
    </div>
  );
}

function MyApplications({ onOpen }: { onOpen: (id: number) => void }) {
  const [apps, setApps] = useState<any[] | null>(null);
  useEffect(() => { api("GET", "/api/applications").then(setApps).catch(() => setApps([])); }, []);
  if (!apps) return <p className="muted">Загружаем заявки…</p>;
  if (apps.length === 0) return <div className="card"><h2>Заявок пока нет</h2><p className="soft">Выберите кредит на вкладке «Подобрать кредит» и подайте первую заявку.</p></div>;
  return (
    <table>
      <thead><tr><th>№</th><th>Продукт</th><th>Сумма</th><th>Статус</th></tr></thead>
      <tbody>
        {apps.map((a) => (
          <tr key={a.id} className="clickable" onClick={() => onOpen(a.id)}>
            <td>{a.id}</td><td>{a.product_name ?? "—"}</td><td>{rub(a.amount)}</td>
            <td><StatusBadge status={a.status} label={a.status_label} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------- Мастер заявки ----------

function Wizard({ product, amount, term, app, onCancel, onDone }: {
  product?: Product; amount?: number; term?: number; app?: any; onCancel: () => void; onDone: (id: number) => void;
}) {
  const [products, setProducts] = useState<Product[]>([]);
  const [demo, setDemo] = useState<any[]>([]);
  const [step, setStep] = useState(0);
  const [id, setId] = useState<number | null>(app?.id ?? null);
  const [f, setF] = useState({
    product_code: app?.product_code ?? product?.code ?? "",
    inn: app?.inn ?? "", company_name: app?.company_name ?? "",
    amount: app?.amount ?? amount ?? 0, term_months: app?.term_months ?? term ?? 12,
    purpose: app?.purpose ?? "", revenue: app?.revenue ?? "", revenue_prev: app?.revenue_prev ?? "",
  });
  const [docs, setDocs] = useState<any[]>(app?.documents ?? []);
  const [docType, setDocType] = useState("Устав");
  const [docName, setDocName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [lookupMsg, setLookupMsg] = useState("");

  useEffect(() => {
    api("GET", "/api/products").then(setProducts).catch(() => {});
    api("GET", "/api/demo/companies").then(setDemo).catch(() => {});
  }, []);

  const set = (k: string, v: any) => setF((s) => ({ ...s, [k]: v }));
  const num = (v: any) => (v === "" || v == null ? null : Number(v));
  const payload = () => ({ ...f, revenue: num(f.revenue), revenue_prev: num(f.revenue_prev), amount: num(f.amount), term_months: num(f.term_months) });

  const save = async (): Promise<number> => {
    if (id == null) {
      const a = await api("POST", "/api/applications", payload());
      setId(a.id);
      return a.id;
    }
    await api("PUT", `/api/applications/${id}`, payload());
    return id;
  };

  const lookup = async () => {
    setLookupMsg(""); setError("");
    try {
      const c = await api("GET", `/api/companies/lookup?inn=${encodeURIComponent(f.inn)}`);
      set("company_name", c.name);
      setLookupMsg(`Нашли: ${c.name}`);
    } catch (e: any) { setError(e.message); }
  };

  const next = async () => {
    setError(""); setBusy(true);
    try { await save(); setStep((s) => s + 1); } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const addDoc = async () => {
    if (!docName.trim()) return;
    setError("");
    try {
      const aid = await save();
      const a = await api("POST", `/api/applications/${aid}/documents`, { doc_type: docType, filename: docName.trim() });
      setDocs(a.documents); setDocName("");
    } catch (e: any) { setError(e.message); }
  };

  const submit = async () => {
    setError(""); setBusy(true);
    try {
      const aid = await save();
      await api("POST", `/api/applications/${aid}/submit`);
      onDone(aid);
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const p = products.find((x) => x.code === f.product_code);
  const titles = ["Компания", "Финансы", "Параметры кредита", "Документы и отправка"];

  return (
    <>
      <div className="row spread">
        <h1>{app ? `Дополнение заявки № ${app.id}` : "Новая заявка"}</h1>
        <button className="btn ghost" onClick={onCancel}>Закрыть</button>
      </div>
      {app?.missing?.length > 0 && (
        <div className="warn"><b>Банк просит дополнить:</b> {app.missing.join("; ")}</div>
      )}
      <div className="steps" role="list">
        {titles.map((t, i) => (
          <div key={t} role="listitem" className={`step ${i < step ? "done" : i === step ? "current" : ""}`}>
            <div className="bar" /><span>{t}</span>
          </div>
        ))}
      </div>
      <div className="card">
        {step === 0 && (<>
          <h2>Ваша компания</h2>
          <label>ИНН (10 или 12 цифр)
            <input value={f.inn} inputMode="numeric" onChange={(e) => set("inn", e.target.value.trim())} />
            <span className="hint">Название подтянется из ЕГРЮЛ/ЕГРИП (в прототипе — из мока)</span>
          </label>
          <div className="row">
            <button className="btn ghost" onClick={lookup} disabled={!f.inn}>Найти компанию</button>
            {lookupMsg && <span className="notice">{lookupMsg}</span>}
          </div>
          <label>Название компании
            <input value={f.company_name} onChange={(e) => set("company_name", e.target.value)} />
          </label>
          {demo.length > 0 && (<div>
            <p className="muted">Тестовые компании для проверки — нажмите, чтобы подставить:</p>
            <div className="row" style={{ marginTop: 8 }}>
              {demo.map((d) => (
                <button key={d.inn} className="chip" title={d.note}
                  onClick={() => { set("inn", d.inn); set("company_name", d.name); }}>{d.name}</button>
              ))}
            </div>
          </div>)}
        </>)}
        {step === 1 && (<>
          <h2>Финансовые показатели</h2>
          <label>Выручка за последний год, ₽
            <input type="number" value={f.revenue} onChange={(e) => set("revenue", e.target.value)} />
          </label>
          <label>Выручка за предыдущий год, ₽
            <input type="number" value={f.revenue_prev} onChange={(e) => set("revenue_prev", e.target.value)} />
            <span className="hint">По ним банк оценит динамику бизнеса</span>
          </label>
        </>)}
        {step === 2 && (<>
          <h2>Параметры кредита</h2>
          <label>Продукт
            <select value={f.product_code} onChange={(e) => set("product_code", e.target.value)}>
              <option value="">Выберите продукт</option>
              {products.map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}
            </select>
          </label>
          <label>Сумма, ₽
            <input type="number" value={f.amount} onChange={(e) => set("amount", e.target.value)} />
            {p && <span className="hint">От {rub(p.min_amount)} до {rub(p.max_amount)}</span>}
          </label>
          <label>Срок, месяцев
            <input type="number" value={f.term_months} onChange={(e) => set("term_months", e.target.value)} />
            {p && <span className="hint">От {p.min_term} до {p.max_term}</span>}
          </label>
          <label>На что нужны деньги
            <input value={f.purpose} onChange={(e) => set("purpose", e.target.value)} />
          </label>
        </>)}
        {step === 3 && (<>
          <h2>Документы и отправка</h2>
          <p className="soft">В прототипе фиксируется факт приложенного документа, файлы не загружаются.</p>
          <div className="row">
            <select value={docType} onChange={(e) => setDocType(e.target.value)} aria-label="Тип документа">
              {["Устав", "Бухгалтерская отчётность", "Договор аренды", "Другое"].map((t) => <option key={t}>{t}</option>)}
            </select>
            <input placeholder="Название файла" value={docName} onChange={(e) => setDocName(e.target.value)} aria-label="Название файла" />
            <button className="btn ghost" onClick={addDoc} disabled={!docName.trim()}>Приложить</button>
          </div>
          {docs.length > 0 && <ul>{docs.map((d) => <li key={d.id}>{d.doc_type}: {d.filename}</li>)}</ul>}
          <div className="notice">
            <b>Проверьте заявку:</b> {f.company_name || f.inn} · {p?.name ?? "продукт не выбран"} · {rub(num(f.amount))} на {f.term_months} мес.
          </div>
        </>)}
        {error && <div className="error" role="alert">{error}</div>}
        <div className="row spread">
          <button className="btn ghost" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>Назад</button>
          {step < 3
            ? <button className="btn" disabled={busy} onClick={next}>Далее</button>
            : <button className="btn red" disabled={busy} onClick={submit}>Отправить в банк</button>}
        </div>
      </div>
    </>
  );
}

// ---------- Страница заявки ----------

function ApplicationPage({ id, onBack, onEdit }: { id: number; onBack: () => void; onEdit: (a: any) => void }) {
  const [a, setA] = useState<any>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => api("GET", `/api/applications/${id}`).then(setA).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);
  // Пока банк обрабатывает заявку, обновляем статус без перезагрузки страницы
  useEffect(() => {
    if (!a || !TRANSIENT.includes(a.status)) return;
    const t = setInterval(load, 1200);
    return () => clearInterval(t);
  }, [a, load]);

  const act = async (path: string) => {
    setError("");
    try { setA(await api("POST", `/api/applications/${id}/${path}`)); } catch (e: any) { setError(e.message); }
  };

  if (!a) return <p className="muted">{error || "Загружаем заявку…"}</p>;
  const canWithdraw = ["draft", "needs_data", "approved", "counter_offer", "offer_accepted"].includes(a.status);
  return (
    <>
      <div className="row spread">
        <button className="btn ghost" onClick={onBack}>← К заявкам</button>
        <StatusBadge status={a.status} label={a.status_label} />
      </div>
      <h1>Заявка № {a.id}: {a.product_name}</h1>
      <p className="soft">{a.company_name || a.inn} · {rub(a.amount)} на {a.term_months} мес.</p>
      <div className="card">
        <Tracker status={a.status} />
        <div className="notice"><b>Что дальше:</b> {a.next_step}</div>
        {a.status === "needs_data" && a.missing.length > 0 && (
          <div className="warn">
            <b>Банку нужно:</b>
            <ul>{a.missing.map((m: string, i: number) => <li key={i}>{m}</li>)}</ul>
            <button className="btn" onClick={() => onEdit(a)}>Дополнить заявку</button>
          </div>
        )}
        {a.reasons.length > 0 && ["approved", "counter_offer", "rejected", "manual_review"].includes(a.status) && (
          <div><b>{a.status === "rejected" ? "Причины отказа" : "Почему так"}</b>
            <ul>{a.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></div>
        )}
      </div>
      {["approved", "counter_offer", "offer_accepted", "signed", "disbursed"].includes(a.status) && <OfferBlock offer={a.offer} />}
      {error && <div className="error" role="alert">{error}</div>}
      <div className="row">
        {["approved", "counter_offer"].includes(a.status) && <button className="btn red" onClick={() => act("accept-offer")}>Принять оферту</button>}
        {a.status === "offer_accepted" && <button className="btn red" onClick={() => act("sign")}>Подписать договор</button>}
        {canWithdraw && a.status !== "draft" && <button className="btn ghost" onClick={() => act("withdraw")}>Отозвать заявку</button>}
        {a.status === "draft" && <button className="btn" onClick={() => onEdit(a)}>Продолжить заполнение</button>}
      </div>
      <div className="card"><h3>История заявки</h3><History items={a.history} /></div>
    </>
  );
}
