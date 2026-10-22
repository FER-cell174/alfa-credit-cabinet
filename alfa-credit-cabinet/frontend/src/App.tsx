import { FormEvent, useEffect, useState } from "react";
import { api, setToken, getToken, User } from "./api";
import Client from "./Client";
import Bank from "./Bank";

const DEMO = [
  { label: "Клиент", email: "client@demo.test", password: "client123" },
  { label: "Оператор банка", email: "operator@demo.test", password: "operator123" },
  { label: "Кредитный аналитик", email: "analyst@demo.test", password: "analyst123" },
  { label: "Администратор", email: "admin@demo.test", password: "admin123" },
];

const ROLE_LABEL: Record<string, string> = {
  client: "клиент", operator: "оператор приёма", analyst: "кредитный аналитик", admin: "администратор",
};

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    api<User>("GET", "/api/me").then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);

  const logout = () => { setToken(null); setUser(null); };
  if (!ready) return null;
  if (!user) return <Login onLogin={setUser} />;

  return (
    <>
      <header className="topbar">
        <div className="inner">
          <span className="brand">Умный кредитный кабинет</span>
          <span className="who">{user.name} · {ROLE_LABEL[user.role]}</span>
          <button className="btn ghost" style={{ color: "#f4f6f8", borderColor: "#4a5468" }} onClick={logout}>Выйти</button>
        </div>
      </header>
      <main className="wrap">{user.role === "client" ? <Client /> : <Bank user={user} />}</main>
    </>
  );
}

function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const doLogin = async (e: string, p: string) => {
    setError("");
    try {
      const r = await api<{ token: string; user: User }>("POST", "/api/auth/login", { email: e, password: p });
      setToken(r.token);
      onLogin(r.user);
    } catch (err: any) { setError(err.message); }
  };
  const submit = (ev: FormEvent) => { ev.preventDefault(); doLogin(email, password); };

  return (
    <main className="wrap" style={{ maxWidth: 520, paddingTop: 64 }}>
      <div>
        <h1>Умный кредитный кабинет</h1>
        <p className="soft">Прототип кредитного конвейера для малого и микробизнеса. Все данные синтетические.</p>
      </div>
      <form className="card" onSubmit={submit}>
        <h2>Вход</h2>
        <label>Почта<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></label>
        <label>Пароль<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
        {error && <div className="error" role="alert">{error}</div>}
        <div><button className="btn red" type="submit">Войти</button></div>
      </form>
      <div className="card">
        <h3>Демо-доступ</h3>
        <p className="muted">Нажмите, чтобы войти тестовой учётной записью:</p>
        <div className="row">
          {DEMO.map((d) => <button key={d.email} className="chip" onClick={() => doLogin(d.email, d.password)}>{d.label}</button>)}
        </div>
      </div>
    </main>
  );
}
