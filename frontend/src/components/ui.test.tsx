import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../api/client";
import { EmptyState, ErrorState, ExecutionBadge, WorkflowBadge } from "./ui";

describe("status badges", () => {
  it("shows a text label, not just a colour", () => {
    render(<><ExecutionBadge status="failed" /><ExecutionBadge status="pending" /><WorkflowBadge status="archived" /></>);
    expect(screen.getByText(/Failed/)).toBeInTheDocument();
    expect(screen.getByText(/Queued/)).toBeInTheDocument();
    expect(screen.getByText(/Archived/)).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("announces the problem, lists field details and offers a retry", async () => {
    const onRetry = vi.fn();
    render(<ErrorState error={new ApiError(400, "validation_error", "The request contains invalid data.", { actions: ["Add at least one action."] })} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("The request contains invalid data.");
    expect(screen.getByText("actions: Add at least one action.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("EmptyState", () => {
  it("renders guidance", () => {
    render(<EmptyState title="No executions yet">Run a sample event.</EmptyState>);
    expect(screen.getByRole("heading", { name: "No executions yet" })).toBeInTheDocument();
  });
});
