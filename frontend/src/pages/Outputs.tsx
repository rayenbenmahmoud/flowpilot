import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Notification, OutboxMessage, Page, TicketAssignment } from "../api/types";
import { EmptyState, ErrorState, PageHeader, Spinner } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { useApi } from "../lib/useApi";
import { useDocumentTitle } from "../lib/useDocumentTitle";

type Tab = "mail" | "notes" | "tickets";

function ExecLink({ id }: { id: string | null }) {
  return id ? <Link to={`/executions/${id}`}>View run</Link> : <>–</>;
}

export function Outputs() {
  useDocumentTitle("Outputs");
  const [tab, setTab] = useState<Tab>("mail");
  const mail = useApi(() => api.get<Page<OutboxMessage>>("/outbox/"), []);
  const notes = useApi(() => api.get<Page<Notification>>("/notifications/"), []);
  const tickets = useApi(() => api.get<Page<TicketAssignment>>("/assignments/"), []);
  const tabs: [Tab, string][] = [["mail", "Mailbox"], ["notes", "Notifications and alerts"], ["tickets", "Ticket assignments"]];
  const current = tab === "mail" ? mail : tab === "notes" ? notes : tickets;

  return (
    <>
      <PageHeader title="Outputs" intro="What workflows produced. In demo mode the mailbox holds simulated emails: nothing was sent to a real inbox." />
      <div className="tabs" role="tablist" aria-label="Output type">
        {tabs.map(([key, label]) => (
          <button key={key} type="button" role="tab" id={`tab-${key}`} aria-selected={tab === key} aria-controls="outputs-panel" onClick={() => setTab(key)}>{label}</button>
        ))}
      </div>
      <div id="outputs-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {current.loading && !current.data && <Spinner />}
        {current.error && <ErrorState error={current.error} onRetry={current.reload} />}
        {tab === "mail" && mail.data && (mail.data.results.length === 0 ? <EmptyState title="The mailbox is empty">Run “Register a new customer” in the guided demo.</EmptyState> : (
          <div className="table-wrap"><table>
            <caption className="sr-only">Emails handled by the email adapter</caption>
            <thead><tr><th>To</th><th>Subject</th><th>Mode</th><th>When</th><th>Run</th></tr></thead>
            <tbody>{mail.data.results.map((m) => (
              <tr key={m.id}><td>{m.to_address}</td><td>{m.subject}<details><summary>Show message</summary><p style={{ whiteSpace: "pre-wrap" }}>{m.body}</p></details></td>
                <td><span className={`badge ${m.mode === "demo" ? "badge-wait" : "badge-ok"}`}>{m.mode === "demo" ? "Simulated" : "Sent"}</span></td>
                <td>{formatDateTime(m.created_at)}</td><td><ExecLink id={m.execution} /></td></tr>
            ))}</tbody>
          </table></div>
        ))}
        {tab === "notes" && notes.data && (notes.data.results.length === 0 ? <EmptyState title="No notifications yet" /> : (
          <div className="table-wrap"><table>
            <caption className="sr-only">Internal notifications and alerts</caption>
            <thead><tr><th>Type</th><th>Message</th><th>When</th><th>Run</th></tr></thead>
            <tbody>{notes.data.results.map((n) => (
              <tr key={n.id}>
                <td><span className={`badge ${n.severity === "error" ? "badge-bad" : n.severity === "warning" ? "badge-wait" : "badge-mute"}`}>{n.kind === "alert" ? "Alert" : "Notice"} · {n.severity}</span></td>
                <td><strong>{n.title}</strong><span className="sub">{n.body}</span></td>
                <td>{formatDateTime(n.created_at)}</td><td><ExecLink id={n.execution} /></td>
              </tr>
            ))}</tbody>
          </table></div>
        ))}
        {tab === "tickets" && tickets.data && (tickets.data.results.length === 0 ? <EmptyState title="No tickets assigned yet" /> : (
          <div className="table-wrap"><table>
            <caption className="sr-only">Support tickets and who they were assigned to</caption>
            <thead><tr><th>Ticket</th><th>Assigned to</th><th>Why</th><th className="hide-sm">When</th><th>Run</th></tr></thead>
            <tbody>{tickets.data.results.map((t) => (
              <tr key={t.id}><td><strong>{t.ticket_id}</strong> <span className="badge badge-mute">{t.priority}</span><span className="sub">{t.subject}</span></td>
                <td>{t.assignee}<span className="sub">{t.team}</span></td><td>{t.matched_rule}</td>
                <td className="hide-sm">{formatDateTime(t.created_at)}</td><td><ExecLink id={t.execution} /></td></tr>
            ))}</tbody>
          </table></div>
        ))}
      </div>
    </>
  );
}
