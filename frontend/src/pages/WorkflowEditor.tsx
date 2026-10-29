import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { ActionConfig, Execution, Meta, Page, Workflow } from "../api/types";
import { useToast } from "../components/Toasts";
import { ErrorState, ExecutionBadge, PageHeader, Pre, Spinner, WorkflowBadge } from "../components/ui";
import { conditionValueToText, formatDateTime, parseConditionValue } from "../lib/format";
import { useApi } from "../lib/useApi";
import { useDocumentTitle } from "../lib/useDocumentTitle";

interface ConditionDraft { field: string; operator: string; valueText: string }
interface Draft {
  name: string;
  description: string;
  trigger_event: string;
  match_mode: "all" | "any";
  conditions: ConditionDraft[];
  actions: ActionConfig[];
}
type Template = Pick<Workflow, "name" | "description" | "trigger_event" | "match_mode" | "conditions" | "actions"> & { key: string };

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const blank = (): Draft => ({ name: "", description: "", trigger_event: "order.created", match_mode: "all", conditions: [], actions: [] });
const fromWorkflow = (w: Pick<Workflow, "name" | "description" | "trigger_event" | "match_mode" | "conditions" | "actions">): Draft => ({
  name: w.name, description: w.description, trigger_event: w.trigger_event, match_mode: w.match_mode,
  conditions: w.conditions.map((c) => ({ field: c.field, operator: c.operator, valueText: conditionValueToText(c.value) })),
  actions: clone(w.actions),
});

/** One action: typed inputs for text settings, JSON boxes for structured ones (e.g. routing rules). */
function ActionEditor({ action, meta, index, onChange, onRemove, disabled }: {
  action: ActionConfig; meta: Meta; index: number; disabled: boolean;
  onChange: (next: ActionConfig) => void; onRemove: () => void;
}) {
  const spec = meta.actions.find((a) => a.type === action.type);
  const [jsonErrors, setJsonErrors] = useState<Record<string, string>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const keys = Array.from(new Set([...Object.keys(spec?.example ?? {}), ...Object.keys(action.config)]));

  return (
    <div className="action-box">
      <header>
        <h3>Action {index + 1}</h3>
        <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
          <div className="field">
            <label htmlFor={`type-${index}`} className="sr-only">Action {index + 1} type</label>
            <select id={`type-${index}`} value={action.type} disabled={disabled} onChange={(e) => {
              const next = meta.actions.find((a) => a.type === e.target.value);
              setDrafts({}); setJsonErrors({});
              onChange({ type: e.target.value, config: clone(next?.example ?? {}) });
            }}>
              {meta.actions.map((a) => <option key={a.type} value={a.type}>{a.label}</option>)}
            </select>
          </div>
          <button type="button" className="btn btn-small" disabled={disabled} onClick={onRemove}>Remove action {index + 1}</button>
        </div>
      </header>
      {spec && <p className="hint" style={{ color: "var(--muted)", fontSize: ".88rem" }}>{spec.description} Use {"{{ payload.field }}"} to insert event data; add {"| default:text"} for optional fields.</p>}
      <div style={{ display: "grid", gap: ".7rem" }}>
        {keys.map((key) => {
          const value = action.config[key] ?? spec?.example[key];
          const id = `a${index}-${key}`;
          const required = spec?.required.includes(key);
          if (typeof value === "string" || value === undefined) {
            const long = key === "body";
            return (
              <div className="field" key={key}>
                <label htmlFor={id}>{key}{required ? "" : " (optional)"}</label>
                {long ? (
                  <textarea id={id} value={String(action.config[key] ?? "")} disabled={disabled} onChange={(e) => onChange({ ...action, config: { ...action.config, [key]: e.target.value } })} />
                ) : (
                  <input id={id} type="text" value={String(action.config[key] ?? "")} disabled={disabled} onChange={(e) => onChange({ ...action, config: { ...action.config, [key]: e.target.value } })} />
                )}
              </div>
            );
          }
          const text = drafts[key] ?? JSON.stringify(action.config[key] ?? value, null, 2);
          return (
            <div className="field" key={key}>
              <label htmlFor={id}>{key} (JSON)</label>
              <textarea id={id} className="mono" rows={8} value={text} disabled={disabled} aria-invalid={Boolean(jsonErrors[key])} onChange={(e) => {
                setDrafts({ ...drafts, [key]: e.target.value });
                try {
                  const parsed: unknown = JSON.parse(e.target.value);
                  setJsonErrors({ ...jsonErrors, [key]: "" });
                  onChange({ ...action, config: { ...action.config, [key]: parsed } });
                } catch {
                  setJsonErrors({ ...jsonErrors, [key]: "This is not valid JSON yet. The last valid value is kept." });
                }
              }} />
              {jsonErrors[key] && <span className="error-text" role="alert">{jsonErrors[key]}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function WorkflowEditor() {
  const { id } = useParams();
  const isNew = !id;
  const navigate = useNavigate();
  const notify = useToast();
  const meta = useApi(() => api.get<Meta>("/meta/"), []);
  const templates = useApi(() => (isNew ? api.get<Template[]>("/workflows/templates/") : Promise.resolve([] as Template[])), [isNew]);
  const existing = useApi(() => (id ? api.get<Workflow>(`/workflows/${id}/`) : Promise.resolve(null)), [id]);
  const recent = useApi(() => (id ? api.get<Page<Execution>>("/executions/", { workflow: id, page_size: 5 }) : Promise.resolve(null)), [id]);
  const [draft, setDraft] = useState<Draft>(blank);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<ApiError | null>(null);
  const [saving, setSaving] = useState(false);
  const [testText, setTestText] = useState("");
  const [testResult, setTestResult] = useState<Execution | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

  useDocumentTitle(isNew ? "New workflow" : existing.data?.name ?? "Workflow");

  useEffect(() => {
    if (existing.data && loadedFor !== existing.data.id + existing.data.version) {
      setDraft(fromWorkflow(existing.data));
      setLoadedFor(existing.data.id + existing.data.version);
    }
  }, [existing.data, loadedFor]);

  const workflow = existing.data;
  const archived = workflow?.status === "archived";
  const eventSpec = meta.data?.events.find((e) => e.key === draft.trigger_event);

  // Pre-fill the test payload from the *saved* workflow's trigger event (not the form's initial blank state).
  const savedEvent = meta.data?.events.find((e) => e.key === workflow?.trigger_event);
  useEffect(() => {
    if (savedEvent) setTestText(JSON.stringify(savedEvent.sample, null, 2));
  }, [savedEvent]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setSaveError(null);
    const body = {
      name: draft.name, description: draft.description, trigger_event: draft.trigger_event, match_mode: draft.match_mode,
      conditions: draft.conditions.map((c) => ({
        field: c.field.trim(), operator: c.operator,
        ...(c.operator === "exists" || c.operator === "not_exists" ? {} : { value: parseConditionValue(c.operator, c.valueText) }),
      })),
      actions: draft.actions.map((a) => ({ type: a.type, config: Object.fromEntries(Object.entries(a.config).filter(([, v]) => v !== "")) })),
    };
    try {
      const saved = isNew ? await api.post<Workflow>("/workflows/", body) : await api.patch<Workflow>(`/workflows/${id}/`, body);
      notify("success", isNew ? "Workflow created. It starts disabled; enable it when you are ready." : "Workflow saved.");
      if (isNew) navigate(`/workflows/${saved.id}`);
      else { existing.reload(); setLoadedFor(null); }
    } catch (e) {
      setSaveError(e instanceof ApiError ? e : new ApiError(0, "error", "Could not save the workflow."));
    } finally {
      setSaving(false);
    }
  }

  // A test run may start Queued when a Celery worker is used; refresh until it finishes.
  useEffect(() => {
    if (!testResult || (testResult.status !== "pending" && testResult.status !== "running")) return;
    const timer = window.setTimeout(() => {
      api.get<Execution>(`/executions/${testResult.id}/`).then(setTestResult).catch(() => undefined);
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [testResult]);

  async function runTest() {
    setTesting(true); setTestError(null); setTestResult(null);
    try {
      const payload = JSON.parse(testText) as unknown;
      const result = await api.post<Execution>(`/workflows/${id}/run/`, { payload }, { "Idempotency-Key": crypto.randomUUID() });
      setTestResult(result);
      recent.reload();
    } catch (e) {
      if (e instanceof SyntaxError) setTestError("The test payload is not valid JSON.");
      else if (e instanceof ApiError) setTestError([e.message, ...Object.values(e.details ?? {}).flat().map(String)].join(" "));
      else setTestError("The test run failed.");
    } finally {
      setTesting(false);
    }
  }

  if (!isNew && existing.loading && !workflow) return <Spinner />;
  if (!isNew && existing.error) return <ErrorState error={existing.error} onRetry={existing.reload} />;
  if (!meta.data) return meta.error ? <ErrorState error={meta.error} onRetry={meta.reload} /> : <Spinner />;
  const m = meta.data;
  const disabled = archived || saving;

  return (
    <>
      <PageHeader
        title={isNew ? "New workflow" : draft.name || "Workflow"}
        intro={isNew ? "Start from a template or build your own." : <>Version {workflow?.version}. Last changed {formatDateTime(workflow?.updated_at)}. <Link to="/workflows">Back to workflows</Link></>}
        actions={workflow && <WorkflowBadge status={workflow.status} />}
      />
      {archived && <div className="callout callout-warn">This workflow is archived and read-only. Restore it from the Workflows page to edit it.</div>}
      {isNew && (templates.data?.length ?? 0) > 0 && (
        <div className="panel">
          <h2>Start from a template</h2>
          <div className="field">
            <label htmlFor="tpl">Template</label>
            <select id="tpl" defaultValue="" onChange={(e) => {
              const t = templates.data?.find((x) => x.key === e.target.value);
              setDraft(t ? fromWorkflow(t) : blank());
            }}>
              <option value="">Blank workflow</option>
              {templates.data?.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
            </select>
            <span className="hint">Copies the template into this form. You can change anything before saving.</span>
          </div>
        </div>
      )}
      <form className="form" onSubmit={save} style={{ marginTop: "1rem" }}>
        {saveError && <ErrorState error={saveError} />}
        <div className="panel">
          <h2>Basics</h2>
          <div className="form">
            <div className="field">
              <label htmlFor="wf-name">Name</label>
              <input id="wf-name" type="text" value={draft.name} disabled={disabled} required maxLength={120} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="wf-desc">Description (optional)</label>
              <textarea id="wf-desc" value={draft.description} disabled={disabled} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
            </div>
          </div>
        </div>

        <div className="panel">
          <h2>Trigger</h2>
          <div className="field">
            <label htmlFor="wf-event">Run when this event arrives</label>
            <select id="wf-event" value={draft.trigger_event} disabled={disabled} onChange={(e) => setDraft({ ...draft, trigger_event: e.target.value })}>
              {m.events.map((ev) => <option key={ev.key} value={ev.key}>{ev.label}{ev.reserved ? " (sent by FlowPilot itself)" : ""}</option>)}
            </select>
            {eventSpec && (
              <span className="hint">
                {eventSpec.description} Fields: {eventSpec.fields.map((f) => `${f.name}${f.required ? "" : "?"}`).join(", ")}
              </span>
            )}
          </div>
        </div>

        <div className="panel">
          <h2>Rules</h2>
          <p className="hint" style={{ color: "var(--muted)" }}>Optional. With no rules the workflow runs for every event. Field names are the event fields above.</p>
          {draft.conditions.length > 1 && (
            <fieldset style={{ marginBottom: ".75rem" }}>
              <legend>When there are several rules</legend>
              <div className="radio-row">
                {(["all", "any"] as const).map((mode) => (
                  <label key={mode}>
                    <input type="radio" name="match" checked={draft.match_mode === mode} disabled={disabled} onChange={() => setDraft({ ...draft, match_mode: mode })} />
                    {mode === "all" ? "All must match" : "Any may match"}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <datalist id="field-names">{eventSpec?.fields.map((f) => <option key={f.name} value={f.name} />)}</datalist>
          {draft.conditions.map((c, i) => {
            const update = (patch: Partial<ConditionDraft>) => setDraft({ ...draft, conditions: draft.conditions.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
            const noValue = c.operator === "exists" || c.operator === "not_exists";
            return (
              <div className="row" key={i}>
                <div className="field"><label htmlFor={`cf-${i}`}>Rule {i + 1} field</label><input id={`cf-${i}`} type="text" list="field-names" value={c.field} disabled={disabled} onChange={(e) => update({ field: e.target.value })} /></div>
                <div className="field"><label htmlFor={`co-${i}`}>Rule {i + 1} condition</label>
                  <select id={`co-${i}`} value={c.operator} disabled={disabled} onChange={(e) => update({ operator: e.target.value })}>
                    {m.operators.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
                  </select></div>
                <div className="field"><label htmlFor={`cv-${i}`}>Rule {i + 1} value</label><input id={`cv-${i}`} type="text" value={noValue ? "" : c.valueText} disabled={disabled || noValue} placeholder={c.operator === "in" ? "a, b, c" : "e.g. 100 or {{ payload.reorder_level }}"} onChange={(e) => update({ valueText: e.target.value })} /></div>
                <button type="button" className="btn btn-small" disabled={disabled} onClick={() => setDraft({ ...draft, conditions: draft.conditions.filter((_, j) => j !== i) })}>Remove rule {i + 1}</button>
              </div>
            );
          })}
          <button type="button" className="btn btn-small" disabled={disabled} onClick={() => setDraft({ ...draft, conditions: [...draft.conditions, { field: "", operator: "eq", valueText: "" }] })}>Add rule</button>
        </div>

        <div className="panel">
          <h2>Actions</h2>
          <p className="hint" style={{ color: "var(--muted)" }}>Run in order. If one fails, the run stops and can be retried; steps that already finished are not repeated.</p>
          {draft.actions.map((a, i) => (
            <ActionEditor key={i} action={a} meta={m} index={i} disabled={disabled}
              onChange={(next) => setDraft({ ...draft, actions: draft.actions.map((x, j) => (j === i ? next : x)) })}
              onRemove={() => setDraft({ ...draft, actions: draft.actions.filter((_, j) => j !== i) })} />
          ))}
          <button type="button" className="btn btn-small" disabled={disabled} onClick={() => setDraft({ ...draft, actions: [...draft.actions, { type: m.actions[0].type, config: clone(m.actions[0].example) }] })}>Add action</button>
        </div>

        <div className="sticky-actions">
          <button type="submit" className="btn btn-primary" disabled={disabled}>{saving ? "Saving…" : isNew ? "Create workflow" : "Save changes"}</button>
          <Link className="btn" to="/workflows">Cancel</Link>
        </div>
      </form>

      {workflow && (
        <>
          <section className="panel" style={{ marginTop: "2rem", maxWidth: "52rem" }} aria-labelledby="test-h">
            <h2 id="test-h">Test run</h2>
            {workflow.status !== "active" ? (
              <p>Enable this workflow to run it with a test payload.</p>
            ) : (
              <>
                <p>Runs only this workflow once, with the event data below. In demo mode nothing real is sent.</p>
                <div className="field">
                  <label htmlFor="test-payload">Event data (JSON)</label>
                  <textarea id="test-payload" className="mono" rows={8} value={testText} onChange={(e) => setTestText(e.target.value)} />
                </div>
                <p style={{ marginTop: ".75rem" }}><button type="button" className="btn btn-primary" disabled={testing} onClick={() => void runTest()}>{testing ? "Running…" : "Run test"}</button></p>
              </>
            )}
            {testError && <div className="callout callout-bad" role="alert">{testError}</div>}
            {testResult && (
              <div className="callout callout-info" role="status">
                <ExecutionBadge status={testResult.status} /> {testResult.error_message || testResult.input_summary}{" "}
                <Link to={`/executions/${testResult.id}`}>Open execution</Link>
              </div>
            )}
          </section>
          <section style={{ maxWidth: "52rem" }} aria-labelledby="hist-h">
            <div className="section-head"><h2 id="hist-h">Recent runs</h2><Link to={`/executions?workflow=${workflow.id}`}>All runs of this workflow</Link></div>
            {recent.data && recent.data.results.length === 0 && <p>No runs yet.</p>}
            {recent.data && recent.data.results.length > 0 && (
              <div className="table-wrap"><table>
                <caption className="sr-only">Recent runs of this workflow</caption>
                <thead><tr><th>Status</th><th>Input</th><th>Started</th></tr></thead>
                <tbody>{recent.data.results.map((e) => (
                  <tr key={e.id}><td><ExecutionBadge status={e.status} /></td><td><Link to={`/executions/${e.id}`}>{e.input_summary || "Event"}</Link></td><td>{formatDateTime(e.created_at)}</td></tr>
                ))}</tbody>
              </table></div>
            )}
            {workflow.actions.length > 0 && <details style={{ marginTop: "1rem" }}><summary>Stored configuration (JSON)</summary><Pre value={{ conditions: workflow.conditions, actions: workflow.actions }} /></details>}
          </section>
        </>
      )}
    </>
  );
}
