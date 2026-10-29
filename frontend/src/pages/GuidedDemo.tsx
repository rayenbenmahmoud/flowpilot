import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { Execution, Scenario, ScenarioRun } from "../api/types";
import { useToast } from "../components/Toasts";
import { ConfirmDialog, ErrorState, ExecutionBadge, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../lib/useApi";
import { useDocumentTitle } from "../lib/useDocumentTitle";

export function GuidedDemo() {
  useDocumentTitle("Guided demo");
  const notify = useToast();
  const { data, error, loading, reload } = useApi(() => api.get<Scenario[]>("/demo/scenarios/"), []);
  const [results, setResults] = useState<Record<string, ScenarioRun>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  // With a Celery worker, runs start out Queued. Refresh them until they reach a final state.
  useEffect(() => {
    const inFlight = Object.values(results)
      .flatMap((r) => r.runs.flatMap((x) => x.executions))
      .filter((e) => e.status === "pending" || e.status === "running");
    if (inFlight.length === 0) return;
    const timer = window.setTimeout(async () => {
      const fresh = await Promise.all(inFlight.map((e) => api.get<Execution>(`/executions/${e.id}/`).catch(() => null)));
      const byId = new Map(fresh.filter((e): e is Execution => e !== null).map((e) => [e.id, e]));
      setResults((previous) =>
        Object.fromEntries(
          Object.entries(previous).map(([key, run]) => [
            key,
            { ...run, runs: run.runs.map((x) => ({ ...x, executions: x.executions.map((e) => (byId.has(e.id) ? { ...e, ...byId.get(e.id)! } : e)) })) },
          ]),
        ),
      );
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [results]);

  async function run(key: string) {
    setBusy(key);
    try {
      const result = await api.post<ScenarioRun>(`/demo/scenarios/${key}/run/`);
      setResults((r) => ({ ...r, [key]: result }));
    } catch (e) {
      notify("error", e instanceof ApiError ? e.message : "The scenario could not run.");
    } finally { setBusy(null); }
  }
  async function reset() {
    setConfirmReset(false);
    try {
      await api.post("/demo/reset/");
      setResults({});
      notify("success", "Demo data reset to the starting state.");
    } catch (e) { notify("error", e instanceof ApiError ? e.message : "Reset failed."); }
  }

  return (
    <>
      <PageHeader title="Guided demo" intro="Send sample events through the real engine, then look at what each workflow did. Everything here is simulated." actions={<button type="button" className="btn" onClick={() => setConfirmReset(true)}>Reset demo data</button>} />
      {loading && !data && <Spinner />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <ol className="steps">
          {data.map((s) => {
            const result = results[s.key];
            const all = result?.runs.flatMap((r) => r.executions) ?? [];
            return (
              <li key={s.key}>
                <h2>{s.title}</h2>
                <p style={{ margin: ".25rem 0" }}>{s.explain}</p>
                <p className="expect">Expect: {s.expect}</p>
                <button type="button" className="btn btn-primary btn-small" disabled={busy !== null} onClick={() => void run(s.key)}>{busy === s.key ? "Running…" : "Send this event"}</button>
                {result && (
                  <div className="result" role="status">
                    {all.length === 0 && <div className="callout callout-warn">No active workflow listens to <code>{result.event}</code>. Enable one on the <Link to="/workflows">Workflows</Link> page.</div>}
                    {result.runs.map((run) => (
                      <div key={run.label}>
                        <strong>{run.label}</strong>
                        <ul>
                          {run.executions.map((e) => (
                            <li key={e.id}>
                              <ExecutionBadge status={e.status} /> {e.workflow_name}{" "}
                              {e.duplicate && <span className="badge badge-mute">Duplicate: not run again</span>}{" "}
                              <Link to={`/executions/${e.id}`}>Open run</Link>
                              {e.status === "failed" && <span className="sub"> {e.error_message}</span>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                    {all.length > 0 && <p><Link to="/outputs">See the outputs</Link></p>}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
      <section className="panel" style={{ marginTop: "2rem" }} aria-labelledby="hook-h">
        <h2 id="hook-h">Send a signed webhook from your terminal</h2>
        <p>The steps above call the engine directly. To exercise the public webhook (signature check, rate limit, duplicate detection), run this from the repository root. The secret comes from your environment, never from the browser.</p>
        <pre className="json">{`export FLOWPILOT_WEBHOOK_SECRET=<the value from your .env>
python backend/scripts/send_webhook.py order.created \\
  '{"order_id":"ORD-9001","total":64.9,"event_id":"my-first-event"}'
# run the same command again: the second call answers "duplicate": true`}</pre>
      </section>
      <ConfirmDialog open={confirmReset} title="Reset demo data?" confirmLabel="Reset everything" onCancel={() => setConfirmReset(false)} onConfirm={() => void reset()}>
        <p>This deletes all workflows, executions and outputs, including any you created, and restores the sample data.</p>
      </ConfirmDialog>
    </>
  );
}
