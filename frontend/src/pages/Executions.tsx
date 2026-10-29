import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { Execution, ExecutionDetail, Page, Workflow } from "../api/types";
import { useToast } from "../components/Toasts";
import { EmptyState, ErrorState, ExecutionBadge, PageHeader, Pre, Spinner } from "../components/ui";
import { formatDateTime, formatDuration, shortId } from "../lib/format";
import { sourceLabel } from "../lib/status";
import { useApi } from "../lib/useApi";
import { useDocumentTitle } from "../lib/useDocumentTitle";

const inFlight = (s: string) => s === "pending" || s === "running";

export function Executions() {
  useDocumentTitle("Executions");
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const status = params.get("status") ?? "";
  const workflow = params.get("workflow") ?? "";
  const dateFrom = params.get("date_from") ?? "";
  const dateTo = params.get("date_to") ?? "";
  const page = Number(params.get("page") ?? "1") || 1;
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };
  const workflows = useApi(() => api.get<Page<Workflow>>("/workflows/", { page_size: 100 }), []);
  const { data, error, loading, reload } = useApi(
    () => api.get<Page<Execution>>("/executions/", { q, status, workflow, date_from: dateFrom, date_to: dateTo, page }),
    [q, status, workflow, dateFrom, dateTo, page],
  );
  const active = data?.results.some((e) => inFlight(e.status));
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(reload, 2000);
    return () => window.clearInterval(timer);
  }, [active, reload]);

  return (
    <>
      <PageHeader title="Executions" intro="Every workflow run, newest first. Open one to see its logs, input and error details." />
      <form className="filters" role="search" onSubmit={(e) => e.preventDefault()}>
        <div className="field"><label htmlFor="ex-q">Search</label><input id="ex-q" type="search" value={q} placeholder="Input, error, key or ID" onChange={(e) => set("q", e.target.value)} /></div>
        <div className="field"><label htmlFor="ex-wf">Workflow</label>
          <select id="ex-wf" value={workflow} onChange={(e) => set("workflow", e.target.value)}>
            <option value="">All workflows</option>
            {workflows.data?.results.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select></div>
        <div className="field"><label htmlFor="ex-st">Status</label>
          <select id="ex-st" value={status} onChange={(e) => set("status", e.target.value)}>
            <option value="">Any status</option><option value="success">Succeeded</option><option value="failed">Failed</option>
            <option value="skipped">Skipped</option><option value="pending">Queued</option><option value="running">Running</option>
          </select></div>
        <div className="field"><label htmlFor="ex-from">From date</label><input id="ex-from" type="date" value={dateFrom} onChange={(e) => set("date_from", e.target.value)} /></div>
        <div className="field"><label htmlFor="ex-to">To date</label><input id="ex-to" type="date" value={dateTo} onChange={(e) => set("date_to", e.target.value)} /></div>
        {(q || status || workflow || dateFrom || dateTo) && <button type="button" className="btn" onClick={() => setParams({}, { replace: true })}>Clear filters</button>}
      </form>
      <p className="hint" style={{ color: "var(--muted)", fontSize: ".85rem" }}>Dates are UTC.</p>
      {loading && !data && <Spinner />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.results.length === 0 && <EmptyState title="No executions match">Try clearing a filter, or run an event from the guided demo.</EmptyState>}
      {data && data.results.length > 0 && (
        <>
          <div className="table-wrap">
            <table>
              <caption className="sr-only">Workflow executions ({data.count} total)</caption>
              <thead><tr><th>Status</th><th>Workflow</th><th className="hide-sm">Input</th><th>Started</th><th className="num hide-sm">Duration</th><th className="hide-sm">Source</th></tr></thead>
              <tbody>
                {data.results.map((e) => (
                  <tr key={e.id}>
                    <td><ExecutionBadge status={e.status} /></td>
                    <td><Link to={`/executions/${e.id}`}>{e.workflow_name}</Link>
                      <span className="sub">{e.attempt > 1 ? `Attempt ${e.attempt} · ` : ""}{e.status === "failed" ? e.error_message : shortId(e.id)}</span></td>
                    <td className="hide-sm">{e.input_summary}</td>
                    <td>{formatDateTime(e.created_at)}</td>
                    <td className="num hide-sm">{formatDuration(e.duration_ms)}</td>
                    <td className="hide-sm">{sourceLabel[e.source] ?? e.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <span>{data.count} executions</span>
            <button type="button" className="btn btn-small" disabled={!data.previous} onClick={() => set("page", String(page - 1))}>Previous</button>
            <span>Page {page}</span>
            <button type="button" className="btn btn-small" disabled={!data.next} onClick={() => set("page", String(page + 1))}>Next</button>
          </div>
        </>
      )}
    </>
  );
}

export function ExecutionView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const notify = useToast();
  const { data, error, loading, reload } = useApi(() => api.get<ExecutionDetail>(`/executions/${id}/`), [id]);
  const [retrying, setRetrying] = useState(false);
  useDocumentTitle(data ? `${data.workflow_name} run` : "Execution");
  const running = data ? inFlight(data.status) : false;
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(reload, 1500);
    return () => window.clearInterval(timer);
  }, [running, reload]);

  async function retry() {
    setRetrying(true);
    try {
      const next = await api.post<Execution>(`/executions/${id}/retry/`);
      notify("success", `Retry started as attempt ${next.attempt}.`);
      navigate(`/executions/${next.id}`);
    } catch (e) {
      notify("error", e instanceof ApiError ? e.message : "The retry could not be started.");
      reload();
    } finally {
      setRetrying(false);
    }
  }

  if (loading && !data) return <Spinner />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <>
      <PageHeader title={data.workflow_name} intro={<>Execution <code>{shortId(data.id)}</code>, attempt {data.attempt}. <Link to="/executions">Back to executions</Link></>}
        actions={<ExecutionBadge status={data.status} />} />
      {data.status === "failed" && (
        <div className="callout callout-bad" role="alert">
          <strong>{data.error_message}</strong>
          <p style={{ margin: ".4rem 0 .6rem" }}>
            Error code <code>{data.error_code}</code>.{" "}
            {data.retryable ? "This looks temporary, so a retry may work." : "This looks permanent. Fix the cause (data or configuration) before retrying."}
          </p>
          <button type="button" className="btn btn-primary" disabled={!data.can_retry || retrying} onClick={() => void retry()}>{retrying ? "Starting retry…" : "Retry this execution"}</button>
          {!data.can_retry && data.retry_blocked_reason && <p style={{ marginTop: ".5rem" }}>{data.retry_blocked_reason}</p>}
          {data.retried_by && <p style={{ marginTop: ".5rem" }}>Retried in <Link to={`/executions/${data.retried_by}`}>attempt {data.attempt + 1}</Link>.</p>}
        </div>
      )}
      <div className="two-col">
        <section className="panel" aria-labelledby="sum-h">
          <h2 id="sum-h">Summary</h2>
          <dl className="kv">
            <dt>Workflow</dt><dd><Link to={`/workflows/${data.workflow}`}>{data.workflow_name}</Link> (v{data.workflow_version})</dd>
            <dt>Input</dt><dd>{data.input_summary || "–"}</dd>
            <dt>Event</dt><dd><code>{data.event_type}</code></dd>
            <dt>Source</dt><dd>{sourceLabel[data.source] ?? data.source}</dd>
            <dt>Started</dt><dd>{formatDateTime(data.started_at ?? data.created_at)}</dd>
            <dt>Duration</dt><dd>{formatDuration(data.duration_ms)}</dd>
            <dt>Attempt</dt><dd>{data.attempt}{data.retry_of && <> (retry of <Link to={`/executions/${data.retry_of}`}>{shortId(data.retry_of)}</Link>)</>}</dd>
            <dt>Idempotency key</dt><dd><code>{data.idempotency_key || "none"}</code></dd>
          </dl>
        </section>
        <section className="panel" aria-labelledby="log-h">
          <h2 id="log-h">Log</h2>
          <ol className="logs">
            {data.logs.map((l) => (
              <li key={l.id}>
                <time dateTime={l.created_at}>{new Date(l.created_at).toLocaleTimeString()}</time>
                <span className={`lvl lvl-${l.level}`}>{l.level}</span>
                <span>{l.message}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>
      <section style={{ marginTop: "1.5rem" }} aria-labelledby="in-h">
        <h2 id="in-h" style={{ marginBottom: ".5rem" }}>Input data</h2>
        <Pre value={data.payload} />
        <p className="hint" style={{ color: "var(--muted)", fontSize: ".85rem", marginTop: ".4rem" }}>Values stored under secret-looking keys (password, token, api_key…) are masked before saving.</p>
      </section>
      {Object.keys(data.result).length > 0 && (
        <section style={{ marginTop: "1.5rem" }} aria-labelledby="res-h">
          <h2 id="res-h" style={{ marginBottom: ".5rem" }}>Result</h2>
          <Pre value={data.result} />
        </section>
      )}
    </>
  );
}
