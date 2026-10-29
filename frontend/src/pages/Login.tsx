import { useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { useAuth } from "../components/Auth";
import { DemoRibbon } from "../components/Layout";
import { useDocumentTitle } from "../lib/useDocumentTitle";

export function Login() {
  useDocumentTitle("Sign in");
  const { login, config } = useAuth();
  const [username, setUsername] = useState(config?.demo_mode ? "demo" : "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <DemoRibbon />
      <main className="login">
        <form className="login-card form" onSubmit={submit} aria-labelledby="login-title">
          <div>
            <h1 id="login-title">FlowPilot</h1>
            <p className="intro">Business workflow automation: events in, actions out, every run recorded.</p>
          </div>
          {config === null && (
            <div className="callout callout-bad" role="alert">
              Cannot reach the API. Start the backend (see README) and reload this page.
            </div>
          )}
          {error && (
            <div className="callout callout-bad" role="alert">
              {error}
            </div>
          )}
          <div className="field">
            <label htmlFor="username">Username</label>
            <input id="username" type="text" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            {config?.demo_mode && (
              <span className="hint">
                Demo account: <code>demo</code> / <code>flowpilot-demo</code> (unless you changed FLOWPILOT_DEMO_USER_PASSWORD).
              </span>
            )}
          </div>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </main>
    </>
  );
}
