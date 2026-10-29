import type { ExecutionStatus, WorkflowStatus } from "../api/types";

export const executionStatus: Record<ExecutionStatus, { label: string; tone: string; icon: string }> = {
  pending: { label: "Queued", tone: "wait", icon: "◌" },
  running: { label: "Running", tone: "wait", icon: "◐" },
  success: { label: "Succeeded", tone: "ok", icon: "✓" },
  failed: { label: "Failed", tone: "bad", icon: "✕" },
  skipped: { label: "Skipped", tone: "mute", icon: "–" },
};

export const workflowStatus: Record<WorkflowStatus, { label: string; tone: string; icon: string }> = {
  active: { label: "Active", tone: "ok", icon: "●" },
  disabled: { label: "Disabled", tone: "mute", icon: "○" },
  archived: { label: "Archived", tone: "mute", icon: "▭" },
};

export const sourceLabel: Record<string, string> = {
  webhook: "Webhook",
  manual: "Manual run",
  demo: "Guided demo",
  retry: "Retry",
  system: "System event",
};
