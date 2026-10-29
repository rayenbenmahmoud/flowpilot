const TOKEN_KEY = "flowpilot.token";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;
  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

// The token lives in sessionStorage: it disappears when the tab closes and is never put in a URL.
export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

type Query = Record<string, string | number | string[] | undefined | null>;

export function buildQuery(query?: Query): string {
  const params = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    (Array.isArray(value) ? value : [value]).forEach((v) => params.append(key, String(v)));
  });
  const text = params.toString();
  return text ? `?${text}` : "";
}

export async function request<T>(
  method: string,
  path: string,
  options: { body?: unknown; query?: Query; headers?: Record<string, string> } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Token ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}${buildQuery(options.query)}`, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the FlowPilot API. Is the backend running on port 8000?");
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    throw new ApiError(response.status, "bad_response", `The server returned an unexpected response (HTTP ${response.status}).`);
  }
  if (!response.ok) {
    const error = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | null)?.error;
    if (response.status === 401 && path !== "/auth/login/") onUnauthorized();
    throw new ApiError(response.status, error?.code ?? "error", error?.message ?? `Request failed (HTTP ${response.status}).`, error?.details);
  }
  return data as T;
}

export const api = {
  get: <T,>(path: string, query?: Query) => request<T>("GET", path, { query }),
  post: <T,>(path: string, body?: unknown, headers?: Record<string, string>) => request<T>("POST", path, { body, headers }),
  patch: <T,>(path: string, body?: unknown) => request<T>("PATCH", path, { body }),
  put: <T,>(path: string, body?: unknown) => request<T>("PUT", path, { body }),
};

/** Flatten an API error's `details` into readable lines, e.g. "actions: Action #1: 'subject' is required." */
export function describeDetails(details?: Record<string, unknown>): string[] {
  if (!details) return [];
  return Object.entries(details).flatMap(([field, value]) =>
    (Array.isArray(value) ? value : [value]).map((item) => {
      const text = typeof item === "string" ? item : JSON.stringify(item);
      return field === "non_field_errors" ? text : `${field}: ${text}`;
    }),
  );
}
