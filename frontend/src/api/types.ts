export type WorkflowStatus = "active" | "disabled" | "archived";
export type ExecutionStatus = "pending" | "running" | "success" | "failed" | "skipped";

export interface Condition {
  field: string;
  operator: string;
  value?: unknown;
}
export interface ActionConfig {
  type: string;
  config: Record<string, unknown>;
}
export interface Workflow {
  id: string;
  name: string;
  description: string;
  template_key: string;
  trigger_event: string;
  match_mode: "all" | "any";
  conditions: Condition[];
  actions: ActionConfig[];
  status: WorkflowStatus;
  version: number;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  runs_total: number;
  runs_success: number;
  runs_failed: number;
  last_run_at: string | null;
  last_status: ExecutionStatus | null;
}
export type WorkflowInput = Pick<
  Workflow,
  "name" | "description" | "trigger_event" | "match_mode" | "conditions" | "actions"
>;

export interface Execution {
  id: string;
  workflow: string;
  workflow_name: string;
  event_type: string;
  status: ExecutionStatus;
  source: string;
  attempt: number;
  input_summary: string;
  error_code: string;
  error_message: string;
  retryable: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
}
export interface ExecutionLog {
  id: number;
  level: "info" | "warning" | "error";
  step: string;
  message: string;
  created_at: string;
}
export interface ExecutionDetail extends Execution {
  root_id: string;
  workflow_version: number;
  idempotency_key: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  logs: ExecutionLog[];
  retry_of: string | null;
  retried_by: string | null;
  can_retry: boolean;
  retry_blocked_reason: string | null;
}
export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
export interface Dashboard {
  workflows: { total: number; active: number; disabled: number; archived: number };
  executions: { total: number; success: number; failed: number; skipped: number; in_progress: number };
  last_24h: { success: number; failed: number };
  success_rate: number | null;
  needs_attention: number;
  daily: { date: string; success: number; failed: number; other: number }[];
  recent: Execution[];
}
export interface Notification {
  id: number;
  kind: "notification" | "alert";
  severity: "info" | "warning" | "error";
  title: string;
  body: string;
  execution: string | null;
  created_at: string;
}
export interface OutboxMessage {
  id: number;
  to_address: string;
  subject: string;
  body: string;
  mode: string;
  status: string;
  execution: string | null;
  created_at: string;
}
export interface TicketAssignment {
  id: number;
  ticket_id: string;
  subject: string;
  priority: string;
  category: string;
  assignee: string;
  team: string;
  matched_rule: string;
  execution: string | null;
  created_at: string;
}
export interface Integration {
  key: string;
  label: string;
  description: string;
  enabled: boolean;
  mode: "demo" | "live";
  state: "simulated" | "disabled" | "not_configured" | "untested" | "connected" | "error";
  state_label: string;
  missing_env: string[];
  secrets: { name: string; is_set: boolean }[];
  settings: Record<string, string | number>;
  settings_schema: { name: string; label: string; kind: "int" | "email"; minimum: number; maximum: number; help: string }[];
  last_test: { at: string | null; ok: boolean | null; mode: string; message: string };
}
export interface EventField {
  name: string;
  type: string;
  required: boolean;
  choices?: string[];
}
export interface Meta {
  events: { key: string; label: string; description: string; reserved: boolean; fields: EventField[]; sample: Record<string, unknown> }[];
  operators: { key: string; label: string }[];
  actions: { type: string; label: string; description: string; required: string[]; example: Record<string, unknown> }[];
  templates: { key: string; name: string; description: string; trigger_event: string }[];
}
export interface Scenario {
  key: string;
  title: string;
  event: string;
  explain: string;
  expect: string;
}
export interface ScenarioRun {
  scenario: string;
  event: string;
  idempotency_key: string;
  runs: { label: string; executions: (Execution & { duplicate: boolean })[] }[];
}
export interface AppConfig {
  app: string;
  version: string;
  demo_mode: boolean;
}
