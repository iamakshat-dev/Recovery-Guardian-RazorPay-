import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Architecture } from "../pages/Architecture";

describe("Architecture — decision path", () => {
  it("renders the five shared pipeline stages in order", () => {
    render(<Architecture />);
    const nav = screen.getByRole("list", { name: /recovery guardian decision path/i });
    const labels = ["Payment Event", "Feature Builder", "ML Classifier", "Policy Engine", "Action"];
    for (const label of labels) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // Order matters -- Policy Engine must precede Action.
    const text = nav.textContent ?? "";
    expect(text.indexOf("Policy Engine")).toBeLessThan(text.indexOf("Action"));
  });

  it("does not render the pipeline's ceremonial lock (this is a conceptual diagram, not one specific BLOCK_RECONCILE decision)", () => {
    render(<Architecture />);
    expect(screen.queryByText("🔒")).not.toBeInTheDocument();
  });
});

describe("Architecture — explanation layer is visually and structurally downstream", () => {
  it("labels the explanation layer as downstream, optional, and without decision authority", () => {
    render(<Architecture />);
    expect(screen.getByText(/Downstream · optional · no decision authority/)).toBeInTheDocument();
    expect(screen.getByText(/Explanation layer/)).toBeInTheDocument();
  });

  it("never implies the LLM sits between the policy engine and the action", () => {
    render(<Architecture />);
    const body = document.body.textContent ?? "";
    expect(body).toMatch(/cannot alter the root-cause prediction, the policy action, or the confidence threshold/);
  });
});

describe("Architecture — safety boundary and determinism framing", () => {
  it("states the model-recommends / policy-decides boundary explicitly", () => {
    render(<Architecture />);
    expect(
      screen.getByText(/The model recommends a confidence estimate; the policy engine determines whether recovery is permitted\./)
    ).toBeInTheDocument();
  });

  it("frames the decision as deterministic, not LLM-driven, without overclaiming a production guarantee", () => {
    render(<Architecture />);
    expect(screen.getByText("ML confidence + deterministic policy constraints → action")).toBeInTheDocument();
    expect(screen.getByText("LLM → payment action")).toBeInTheDocument();
  });
});

describe("Architecture — honest scope", () => {
  it("discloses synthetic data, replay, simulation, and no live execution", () => {
    render(<Architecture />);
    const body = document.body.textContent ?? "";
    expect(body).toMatch(/synthetic/i);
    expect(body).toMatch(/deterministic replay/i);
    expect(body).toMatch(/counterfactual simulator/i);
    expect(body).toMatch(/No live payment execution/i);
  });
});
