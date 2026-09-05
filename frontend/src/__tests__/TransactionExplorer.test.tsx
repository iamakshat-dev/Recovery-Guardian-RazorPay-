import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TransactionExplorer } from "../pages/TransactionExplorer";
import { snapshot } from "../data/snapshot";

describe("TransactionExplorer — population and provenance", () => {
  it("shows every Day 12 transaction, with the actual count read from the snapshot", () => {
    render(<TransactionExplorer />);
    const total = snapshot.day12.transactions.length;
    expect(total).toBeGreaterThan(0);
    expect(screen.getByText(new RegExp(`Showing ${total} of ${total} transactions`))).toBeInTheDocument();
  });

  it("distinguishes the Day 12 population from the Day 9 population in copy", () => {
    render(<TransactionExplorer />);
    const body = document.body.textContent ?? "";
    expect(body).toMatch(/Day 12 incident-window population/);
    expect(body).toMatch(/Day 9 test-set population/);
    expect(body).toMatch(/never combined/);
  });
});

describe("TransactionExplorer — search, filter, sort", () => {
  it("filters the list down to a single row when searching by exact transaction ID", () => {
    render(<TransactionExplorer />);
    const first = snapshot.day12.transactions[0];
    const input = screen.getByLabelText(/search transaction id/i);
    fireEvent.change(input, { target: { value: first.transactionId } });
    expect(screen.getByText(new RegExp(`Showing 1 of ${snapshot.day12.transactions.length} transactions`))).toBeInTheDocument();
  });

  it("shows a no-match state for a query that matches nothing", () => {
    render(<TransactionExplorer />);
    const input = screen.getByLabelText(/search transaction id/i);
    fireEvent.change(input, { target: { value: "not-a-real-id-xyz" } });
    expect(screen.getByText(/No transactions match the current filters/i)).toBeInTheDocument();
  });

  it("filters by root cause using an option actually present in the data", () => {
    render(<TransactionExplorer />);
    const rootCause = snapshot.day12.transactions[0].predictedRootCause;
    const expectedCount = snapshot.day12.transactions.filter((t) => t.predictedRootCause === rootCause).length;
    const select = screen.getByLabelText(/root cause/i);
    fireEvent.change(select, { target: { value: rootCause } });
    expect(
      screen.getByText(new RegExp(`Showing ${expectedCount} of ${snapshot.day12.transactions.length} transactions`))
    ).toBeInTheDocument();
  });
});

describe("TransactionExplorer — detail panel and ground-truth firewall", () => {
  it("opens a detail panel on row selection showing predicted vs known root cause as distinct rows", () => {
    render(<TransactionExplorer />);
    const first = snapshot.day12.transactions[0];
    fireEvent.click(screen.getByRole("button", { name: new RegExp(first.transactionId) }));
    expect(screen.getByText(/Predicted root cause \(model\)/)).toBeInTheDocument();
    expect(screen.getByText(/Known root cause \(synthetic label\)/)).toBeInTheDocument();
  });

  it("never presents the known synthetic label as something the model inferred", () => {
    render(<TransactionExplorer />);
    const first = snapshot.day12.transactions[0];
    fireEvent.click(screen.getByRole("button", { name: new RegExp(first.transactionId) }));
    const body = document.body.textContent ?? "";
    expect(body).toMatch(/never available to the model or the policy engine at decision time/);
  });

  it("shows no detail panel before any row is selected", () => {
    render(<TransactionExplorer />);
    expect(screen.queryByRole("region", { name: /detail for transaction/i })).not.toBeInTheDocument();
  });
});
