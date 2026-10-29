export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "–";
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  return seconds < 60 ? `${seconds.toFixed(1)} s` : `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
}

export function timeAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "never";
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

/** Turn what a person typed in a rule's value box into the JSON value the API expects. */
export function parseConditionValue(operator: string, text: string): unknown {
  const trimmed = text.trim();
  if (operator === "in" || operator === "not_in") {
    return trimmed
      .split(",")
      .map((part) => parseScalar(part.trim()))
      .filter((part) => part !== "");
  }
  return parseScalar(trimmed);
}

function parseScalar(text: string): string | number {
  return text !== "" && !text.startsWith("{{") && Number.isFinite(Number(text)) ? Number(text) : text;
}

export function conditionValueToText(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  return value === undefined || value === null ? "" : String(value);
}
