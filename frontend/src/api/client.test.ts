import { ApiError, api, buildQuery, describeDetails, tokenStore } from "./client";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

const respond = (status: number, body: unknown) =>
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body === null ? null : JSON.stringify(body), { status }));

describe("buildQuery", () => {
  it("skips empty values and repeats arrays", () => {
    expect(buildQuery({ q: "", status: ["failed", "success"], page: 2, none: undefined })).toBe("?status=failed&status=success&page=2");
    expect(buildQuery({})).toBe("");
  });
});

describe("request", () => {
  it("sends the token as an Authorization header", async () => {
    tokenStore.set("abc123");
    const spy = respond(200, { ok: true });
    await api.get("/dashboard/");
    const headers = spy.mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Token abc123");
    expect(spy.mock.calls[0][0]).toBe("/api/v1/dashboard/");
  });

  it("turns the API error envelope into an ApiError", async () => {
    respond(409, { error: { code: "already_retried", message: "This execution has already been retried." } });
    await expect(api.post("/executions/1/retry/")).rejects.toMatchObject({ status: 409, code: "already_retried", message: "This execution has already been retried." });
  });

  it("explains network failures", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.get("/config/")).rejects.toThrow(/Is the backend running/);
  });

  it("handles 204 and non-JSON responses", async () => {
    respond(204, null);
    await expect(api.post("/auth/logout/")).resolves.toBeUndefined();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("<html>oops</html>", { status: 502 }));
    await expect(api.get("/x/")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("describeDetails", () => {
  it("flattens field errors into readable lines", () => {
    expect(describeDetails({ actions: ["Action #1: 'subject' is required."], non_field_errors: ["Bad"] })).toEqual(["actions: Action #1: 'subject' is required.", "Bad"]);
    expect(describeDetails(undefined)).toEqual([]);
  });
});
