import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Dashboard as DashboardData } from "../api/types";
import { EmptyState, ErrorState, ExecutionBadge, PageHeader, Spinner } from "../components/ui";
import { formatDateTime, formatDuration, timeAgo } from "../lib/format";
import { useApi } from "../lib/useApi";
import { useDocumentTitle } from "../lib/useDocumentTitle";

function Runway({ daily }: { daily: DashboardData["daily"] }) {
  const max = Math.max(1, ...daily.map((d) => d.success + d.failed + d.other));
  const width = 340;
  const height = 200;
  const slot = width / daily.length;
  const barWidth = Math.min(32, slot - 12);
  const scale = (height - 34) / max;
  return (
    <>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Executions per day for the last seven days, split into succeeded, failed and other">
        {daily.map((d, i) => {
          const x = i * slot + (slot - barWidth) / 2;
          let y = height - 22;
          const parts: [number, string][] = [[d.success, "#17794F"], [d.failed, "#B3261E"], [d.other, "#9AA8BA"]];
          return (
            <g key={d.date}>
              {parts.map(([count, color]) => {
                if (!count) return null;
                const h = count * scale;
                y -= h;
                return <rect key={color} x={x} y={y} width={barWidth} height={h} fill={color} />;
              })}
              <text x={x + barWidth / 2} y={height - 6} textAnchor="middle" fontSize="12" fill="#53647A">
                {new Date(d.date + "T00:00:00").toLocaleDateString(undefined, { weekday: "short" })}
              </text>
            </g>
          );
        })}
        <line x1="0" x2={width} y1={height - 22} y2={height - 22} stroke="#D3DAE3" />
      </svg>
      <div className="legend" aria-hidden="true">
        <span><span className="swatch" style={{ background: "#17794F" }} />Succeeded</span>
        <span><span className="swatch" style={{ background: "#B3261E" }} />Failed</span>
        <span><span className="swatch" style={{ background: "#9AA8BA" }} />Skipped or in progress</span>
      </div>
      <table className="sr-only">
        <caption>Executions per day, last seven days</caption>
        <thead><tr><th>Day</th><th>Succeeded</th><th>Failed</th><th>Other</th></tr></thead>
        <tbody>
          {daily.map((d) => (
            <tr key={d.date}><td>{d.date}</td><td>{d.success}</td><td>{d.failed}</td><td>{d.other}</td></tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export function Dashboard() {
  useDocumentTitle("Dashboard");
  const { data, error, loading, reload } = useApi(() => api.get<DashboardData>("/dashboard/"), []);
  return (
    <>
      <PageHeader
        title="Dashboard"
        intro="What is running, what worked, and what needs a person."
        actions={<button type="button" className="btn" onClick={reload}>Refresh</button>}
      />
      {loading && !data && <Spinner />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <>
          <section aria-label="Key figures">
            <div className="figures">
              <div className="figure"><span className="num">{data.workflows.total}</span><span className="lbl">Workflows ({data.workflows.archived} archived)</span></div>
              <div className="figure"><span className="num">{data.workflows.active}</span><span className="lbl">Active workflows</span></div>
              <div className="figure is-ok"><span className="num">{data.executions.success}</span><span className="lbl">Successful runs ({data.last_24h.success} in 24 h)</span></div>
              <div className="figure is-bad"><span className="num">{data.executions.failed}</span><span className="lbl">Failed runs ({data.last_24h.failed} in 24 h)</span></div>
            </div>
          </section>

          {data.needs_attention > 0 && (
            <div className="callout callout-warn" style={{ marginTop: "1rem" }}>
              <strong>{data.needs_attention} failed {data.needs_attention === 1 ? "run has" : "runs have"} not been retried.</strong>{" "}
              <Link to="/executions?status=failed">Review failed executions</Link>
            </div>
          )}

          {data.executions.total === 0 ? (
            <section>
              <EmptyState title="No executions yet">
                Run a sample event from the <Link to="/demo">guided demo</Link> to see workflows work.
              </EmptyState>
            </section>
          ) : (
            <div className="two-col" style={{ marginTop: "1.5rem" }}>
              <section aria-labelledby="recent-h">
                <div className="section-head">
                  <h2 id="recent-h">Recent executions</h2>
                  <Link to="/executions">All executions</Link>
                </div>
                <div className="table-wrap">
                  <table>
                    <caption className="sr-only">Most recent workflow executions</caption>
                    <thead><tr><th>Status</th><th>Workflow</th><th className="hide-sm">Started</th><th className="num hide-sm">Duration</th></tr></thead>
                    <tbody>
                      {data.recent.map((e) => (
                        <tr key={e.id}>
                          <td><ExecutionBadge status={e.status} /></td>
                          <td><Link to={`/executions/${e.id}`}>{e.workflow_name}</Link><span className="sub">{e.input_summary}</span></td>
                          <td className="hide-sm" title={formatDateTime(e.created_at)}>{timeAgo(e.created_at)}</td>
                          <td className="num hide-sm">{formatDuration(e.duration_ms)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section aria-labelledby="runway-h">
                <div className="section-head"><h2 id="runway-h">Last 7 days</h2></div>
                <div className="runway">
                  <Runway daily={data.daily} />
                  <p className="hint" style={{ marginTop: ".5rem", fontSize: ".85rem", color: "var(--muted)" }}>
                    {data.success_rate === null ? "No finished runs yet." : `${data.success_rate}% of finished runs succeeded (skipped runs excluded).`}
                  </p>
                </div>
              </section>
            </div>
          )}
        </>
      )}
    </>
  );
}
