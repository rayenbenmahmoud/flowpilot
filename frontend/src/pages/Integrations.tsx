import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { Integration } from "../api/types";
import { useToast } from "../components/Toasts";
import { ErrorState, PageHeader, Spinner } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/useApi";
import { useDocumentTitle } from "../lib/useDocumentTitle";

const TONE: Record<Integration["state"], string> = {
  simulated: "badge-wait", disabled: "badge-mute", not_configured: "badge-mute", untested: "badge-mute", connected: "badge-ok", error: "badge-bad",
};

function IntegrationCard({ item, onChanged }: { item: Integration; onChanged: () => void }) {
  const notify = useToast();
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(item.settings).map(([k, v]) => [k, String(v)])));
  const [busy, setBusy] = useState<"save" | "test" | "toggle" | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function save() {
    setBusy("save"); setError(null);
    const settings = Object.fromEntries(item.settings_schema.map((s) => [s.name, s.kind === "int" ? Number(values[s.name]) : values[s.name]]));
    try {
      await api.patch(`/integrations/${item.key}/`, { settings });
      notify("success", `${item.label}: settings saved.`);
      onChanged();
    } catch (e) { setError(e instanceof ApiError ? e : null); } finally { setBusy(null); }
  }
  async function toggle(enabled: boolean) {
    setBusy("toggle");
    try { await api.patch(`/integrations/${item.key}/`, { enabled }); onChanged(); }
    catch (e) { notify("error", e instanceof ApiError ? e.message : "Could not change the integration."); }
    finally { setBusy(null); }
  }
  async function test() {
    setBusy("test");
    try {
      const r = await api.post<{ result: { ok: boolean; mode: string; message: string } }>(`/integrations/${item.key}/test/`);
      notify(r.result.ok ? "success" : "warning", r.result.message);
      onChanged();
    } catch (e) { notify("error", e instanceof ApiError ? e.message : "The test could not run."); }
    finally { setBusy(null); }
  }

  const demo = item.mode === "demo";
  return (
    <section className="integration" aria-labelledby={`int-${item.key}`}>
      <header>
        <div><h2 id={`int-${item.key}`}>{item.label}</h2><p style={{ margin: 0, color: "var(--muted)" }}>{item.description}</p></div>
        <span className={`badge ${TONE[item.state]}`}>{item.state_label}</span>
      </header>
      {demo && <div className="callout callout-warn">Demo mode is on, so this integration is <strong>simulated</strong>. No real connection is made and it cannot be reported as connected.</div>}
      <label className="switch"><input type="checkbox" checked={item.enabled} disabled={busy !== null} onChange={(e) => void toggle(e.target.checked)} /> Integration turned on</label>
      <h3 style={{ marginTop: "1rem" }}>Credentials (set in the server environment)</h3>
      <ul className="env-list">
        {item.secrets.map((s) => <li key={s.name}><span aria-hidden="true">{s.is_set ? "✓" : "✕"}</span> <code>{s.name}</code>: {s.is_set ? "set (value hidden)" : "not set"}</li>)}
        {item.missing_env.filter((n) => !item.secrets.some((s) => s.name === n)).map((n) => <li key={n}><span aria-hidden="true">✕</span> <code>{n}</code>: not set</li>)}
      </ul>
      {error && <ErrorState error={error} />}
      {item.settings_schema.length > 0 && (
        <div className="filters">
          {item.settings_schema.map((s) => (
            <div className="field" key={s.name}>
              <label htmlFor={`${item.key}-${s.name}`}>{s.label}</label>
              <input id={`${item.key}-${s.name}`} type={s.kind === "int" ? "number" : "text"} min={s.kind === "int" ? s.minimum : undefined} max={s.kind === "int" ? s.maximum : undefined}
                style={s.kind === "email" ? { minWidth: "18rem" } : undefined} value={values[s.name] ?? ""} onChange={(e) => setValues({ ...values, [s.name]: e.target.value })} />
              {s.help && <span className="hint">{s.help}</span>}
            </div>
          ))}
          <button type="button" className="btn" disabled={busy !== null} onClick={() => void save()}>{busy === "save" ? "Saving…" : "Save settings"}</button>
        </div>
      )}
      <div className="sticky-actions">
        <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => void test()}>{busy === "test" ? "Testing…" : demo ? "Run simulated check" : "Test connection"}</button>
        <span style={{ color: "var(--muted)", fontSize: ".9rem" }}>
          {item.last_test.at ? <>Last check {formatDateTime(item.last_test.at)} ({item.last_test.mode === "demo" ? "simulated" : "live"}): {item.last_test.message}</> : "Not checked yet."}
        </span>
      </div>
    </section>
  );
}

export function Integrations() {
  useDocumentTitle("Integrations");
  const { data, error, loading, reload } = useApi(() => api.get<Integration[]>("/integrations/"), []);
  return (
    <>
      <PageHeader title="Integrations" intro="Connections to email, n8n and partner APIs. Secrets and URLs live in server environment variables and are never shown here." />
      {loading && !data && <Spinner />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data?.map((item) => <IntegrationCard key={item.key + item.last_test.at + item.enabled} item={item} onChanged={reload} />)}
    </>
  );
}
