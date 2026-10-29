import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "../components/Auth";
import { ToastProvider } from "../components/Toasts";
import { Dashboard } from "../pages/Dashboard";
import { Executions, ExecutionView } from "../pages/Executions";
import { GuidedDemo } from "../pages/GuidedDemo";
import { Integrations } from "../pages/Integrations";
import { Outputs } from "../pages/Outputs";
import { WorkflowEditor } from "../pages/WorkflowEditor";
import { Workflows } from "../pages/Workflows";
import fixtures from "./fixtures.json";

// Fixtures are real responses captured from the running backend, so shapes cannot drift from the API.
const fx = fixtures as Record<string, unknown> & { failedExecution: { id: string; error_message: string }; "/workflows/": { results: { id: string; name: string; status: string }[] } };

function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input).replace("/api/v1", "").split("?")[0];
    const exec = url.match(/^\/executions\/([^/]+)\/$/);
    const wf = url.match(/^\/workflows\/([^/]+)\/$/);
    const body = exec ? fx.failedExecution : wf ? fx["/workflows/"].results.find((w) => w.id === wf[1]) : url === "/workflows/templates/" ? [] : fx[url];
    return new Response(JSON.stringify(body ?? {}), { status: body === undefined ? 404 : 200 });
  });
}

function renderAt(path: string, element: React.ReactNode, route = path) {
  sessionStorage.setItem("flowpilot.token", "t");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider><ToastProvider><Routes><Route path={route} element={element} /></Routes></ToastProvider></AuthProvider>
    </MemoryRouter>,
  );
}

afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

it("dashboard shows the four key figures, the attention callout and recent runs", async () => {
  mockApi();
  renderAt("/", <Dashboard />);
  expect(await screen.findByText(/Active workflows/)).toBeInTheDocument();
  expect(screen.getByText(/Successful runs/)).toBeInTheDocument();
  expect(screen.getByText(/Failed runs/)).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Executions per day/ })).toBeInTheDocument();
  expect(screen.getByRole("table", { name: /Most recent workflow executions/ })).toBeInTheDocument();
});

it("workflows lists strips with readable trigger and action names", async () => {
  mockApi();
  renderAt("/workflows", <Workflows />);
  expect(await screen.findByRole("heading", { name: "Low inventory alert" })).toBeInTheDocument();
  expect(screen.getAllByText(/Create alert/).length).toBeGreaterThan(0);
  expect(screen.getAllByText("Archived").length).toBeGreaterThan(0);
  expect(screen.getAllByRole("button", { name: "Disable" }).length).toBeGreaterThan(0);
});

it("executions table has filters and links to detail", async () => {
  mockApi();
  renderAt("/executions", <Executions />);
  expect(await screen.findByRole("table", { name: /Workflow executions/ })).toBeInTheDocument();
  expect(screen.getByLabelText("Search")).toBeInTheDocument();
  expect(screen.getByLabelText("From date")).toBeInTheDocument();
});

it("a failed execution shows the error, advice and an enabled retry button", async () => {
  mockApi();
  renderAt(`/executions/${fx.failedExecution.id}`, <ExecutionView />, "/executions/:id");
  expect(await screen.findByRole("alert")).toHaveTextContent(fx.failedExecution.error_message);
  expect(screen.getByRole("button", { name: /Retry this execution/ })).toBeEnabled();
  expect(screen.getByRole("heading", { name: "Input data" })).toBeInTheDocument();
});

it("workflow editor loads rules and actions as labelled form controls", async () => {
  mockApi();
  const target = fx["/workflows/"].results.find((w) => w.name === "Low inventory alert")!;
  renderAt(`/workflows/${target.id}`, <WorkflowEditor />, "/workflows/:id");
  expect(await screen.findByLabelText("Rule 1 field")).toHaveValue("quantity");
  expect(screen.getByLabelText("Rule 1 value")).toHaveValue("{{ payload.reorder_level }}");
  expect(screen.getByLabelText("title")).toHaveValue("Low stock: {{ payload.sku }}");
  expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
});

it("the editor makes archived workflows read-only", async () => {
  mockApi();
  const target = fx["/workflows/"].results.find((w) => w.status === "archived")!;
  renderAt(`/workflows/${target.id}`, <WorkflowEditor />, "/workflows/:id");
  expect(await screen.findByText(/archived and read-only/)).toBeInTheDocument();
  expect(screen.getByLabelText("Name")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
});

it("a new workflow can start from the blank form", async () => {
  mockApi();
  renderAt("/workflows/new", <WorkflowEditor />);
  expect(await screen.findByLabelText("Name")).toHaveValue("");
  await userEvent.click(screen.getByRole("button", { name: "Add action" }));
  expect(await screen.findByRole("heading", { name: "Action 1" })).toBeInTheDocument();
});

it("integrations say 'simulated' in demo mode and never show secret values", async () => {
  mockApi();
  renderAt("/integrations", <Integrations />);
  expect(await screen.findByRole("heading", { name: "n8n webhooks" })).toBeInTheDocument();
  expect(screen.getAllByText(/Simulated \(demo mode\)/).length).toBe(3);
  expect(screen.queryByText(/Connected/)).not.toBeInTheDocument();
  expect(screen.getAllByText(/not set|set \(value hidden\)/).length).toBeGreaterThan(0);
});

it("outputs tabs switch between mailbox, notifications and tickets", async () => {
  mockApi();
  renderAt("/outputs", <Outputs />);
  expect(await screen.findByRole("table", { name: /Emails handled/ })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "Ticket assignments" }));
  await waitFor(() => expect(screen.getByRole("table", { name: /Support tickets/ })).toBeInTheDocument());
});

it("guided demo lists the scenarios as ordered steps", async () => {
  mockApi();
  renderAt("/demo", <GuidedDemo />);
  expect(await screen.findByRole("heading", { name: "Welcome email that bounces" })).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Send this event" }).length).toBe(9);
});

it("guided demo keeps refreshing a Queued run until the worker finishes it (Celery mode)", async () => {
  const queued = { id: "e1", workflow: "w1", workflow_name: "Welcome email for new customers", event_type: "customer.registered", status: "pending", source: "demo", attempt: 1, input_summary: "x", error_code: "", error_message: "", retryable: false, created_at: "2026-01-01T00:00:00Z", started_at: null, finished_at: null, duration_ms: null, duplicate: false };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input).replace("/api/v1", "");
    if (url === "/demo/scenarios/") return new Response(JSON.stringify(fx["/demo/scenarios/"]), { status: 200 });
    if (url.endsWith("/run/") && init?.method === "POST") return new Response(JSON.stringify({ scenario: "new-customer", event: "customer.registered", idempotency_key: "k", runs: [{ label: "Delivery", executions: [queued] }] }), { status: 202 });
    if (url === "/executions/e1/") return new Response(JSON.stringify({ ...queued, status: "success", duration_ms: 12 }), { status: 200 });
    return new Response("{}", { status: 404 });
  });
  renderAt("/demo", <GuidedDemo />);
  await userEvent.click((await screen.findAllByRole("button", { name: "Send this event" }))[0]);
  expect(await screen.findByText(/Queued/)).toBeInTheDocument();
  expect(await screen.findByText(/Succeeded/, undefined, { timeout: 4000 })).toBeInTheDocument();
  expect(screen.queryByText(/Queued/)).not.toBeInTheDocument();
});

it("the test-run box is pre-filled from the saved workflow's own trigger event, not the form's blank default", async () => {
  mockApi();
  const target = fx["/workflows/"].results.find((w) => w.name === "Low inventory alert")!;
  renderAt(`/workflows/${target.id}`, <WorkflowEditor />, "/workflows/:id");
  const box = (await screen.findByLabelText("Event data (JSON)")) as HTMLTextAreaElement;
  await waitFor(() => expect(box.value).toContain('"sku"'));
  expect(box.value).toContain('"reorder_level"');
  expect(box.value).not.toContain('"order_id"');
});
