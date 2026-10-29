import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Meta, Page, Workflow } from "../api/types";
import { useToast } from "../components/Toasts";
import { ConfirmDialog, EmptyState, ErrorState, PageHeader, Spinner, WorkflowBadge } from "../components/ui";
import { timeAgo } from "../lib/format";
import { useApi } from "../lib/useApi";
import { useDocumentTitle } from "../lib/useDocumentTitle";
import { ApiError } from "../api/client";

export function Workflows() {
  useDocumentTitle("Workflows");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [pendingArchive, setPendingArchive] = useState<Workflow | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const notify = useToast();
  const navigate = useNavigate();
  const meta = useApi(() => api.get<Meta>("/meta/"), []);
  const { data, error, loading, reload } = useApi(
    () => api.get<Page<Workflow>>("/workflows/", { q, status, page_size: 100 }),
    [q, status],
  );

  const eventLabel = (key: string) => meta.data?.events.find((e) => e.key === key)?.label ?? key;
  const actionLabel = (type: string) => meta.data?.actions.find((a) => a.type === type)?.label ?? type;

  async function act(workflow: Workflow, verb: "enable" | "disable" | "archive" | "restore", done: string) {
    setBusyId(workflow.id);
    try {
      await api.post(`/workflows/${workflow.id}/${verb}/`);
      notify("success", `${workflow.name}: ${done}`);
      reload();
    } catch (e) {
      notify("error", e instanceof ApiError ? e.message : "The change could not be saved.");
    } finally {
      setBusyId(null);
      setPendingArchive(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Workflows"
        intro="Each workflow listens for one event, checks its rules, then runs its actions in order."
        actions={<button type="button" className="btn btn-primary" onClick={() => navigate("/workflows/new")}>New workflow</button>}
      />
      <form className="filters" role="search" onSubmit={(e) => e.preventDefault()}>
        <div className="field">
          <label htmlFor="wf-q">Search workflows</label>
          <input id="wf-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or description" />
        </div>
        <div className="field">
          <label htmlFor="wf-status">Status</label>
          <select id="wf-status" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="disabled">Disabled</option>
            <option value="archived">Archived</option>
          </select>
        </div>
      </form>
      {loading && !data && <Spinner />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.results.length === 0 && (
        <EmptyState title={q || status ? "No workflows match" : "No workflows yet"}>
          {q || status ? "Clear the search or status filter." : "Create one from a template to get started."}
        </EmptyState>
      )}
      {data && data.results.length > 0 && (
        <ul className="strips">
          {data.results.map((w) => {
            const cls = w.status === "active" ? (w.last_status === "failed" ? "is-failing" : "is-active") : `is-${w.status}`;
            const busy = busyId === w.id;
            return (
              <li key={w.id} className={`strip ${cls}`}>
                <div>
                  <h2><Link to={`/workflows/${w.id}`}>{w.name}</Link></h2>
                  <p className="meta">{w.description || "No description."}</p>
                </div>
                <dl className="flow" style={{ margin: 0 }}>
                  <div><dt>When: </dt><dd>{eventLabel(w.trigger_event)}</dd></div>
                  <div><dt>Rules: </dt><dd>{w.conditions.length === 0 ? "always runs" : `${w.conditions.length} condition${w.conditions.length > 1 ? "s" : ""} (${w.match_mode === "all" ? "all" : "any"} must match)`}</dd></div>
                  <div><dt>Then: </dt><dd>{w.actions.map((a) => actionLabel(a.type)).join(", ")}</dd></div>
                </dl>
                <div>
                  <div className="strip-status">
                    <WorkflowBadge status={w.status} />
                    <span className="meta" style={{ margin: 0 }}>{w.runs_total} runs, {w.runs_failed} failed · last {timeAgo(w.last_run_at)}</span>
                  </div>
                  <div className="strip-actions">
                    <Link className="btn btn-small" to={`/workflows/${w.id}`}>{w.status === "archived" ? "View" : "Edit"}</Link>
                    {w.status === "disabled" && <button type="button" className="btn btn-small" disabled={busy} onClick={() => void act(w, "enable", "enabled")}>Enable</button>}
                    {w.status === "active" && <button type="button" className="btn btn-small" disabled={busy} onClick={() => void act(w, "disable", "disabled")}>Disable</button>}
                    {w.status !== "archived" && <button type="button" className="btn btn-small" disabled={busy} onClick={() => setPendingArchive(w)}>Archive</button>}
                    {w.status === "archived" && <button type="button" className="btn btn-small" disabled={busy} onClick={() => void act(w, "restore", "restored as disabled")}>Restore</button>}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <ConfirmDialog
        open={pendingArchive !== null}
        title={`Archive “${pendingArchive?.name ?? ""}”?`}
        confirmLabel="Archive workflow"
        onCancel={() => setPendingArchive(null)}
        onConfirm={() => pendingArchive && void act(pendingArchive, "archive", "archived")}
      >
        <p>It stops running and cannot be edited. Its execution history stays. You can restore it later (it comes back disabled).</p>
      </ConfirmDialog>
    </>
  );
}
