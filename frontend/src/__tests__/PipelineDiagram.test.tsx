import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PipelineDiagram, type PipelineDiagramNode } from "../components/pipeline/PipelineDiagram";

const NODES: PipelineDiagramNode[] = [
  { id: "a", label: "Alpha", detail: "alpha detail" },
  { id: "b", label: "Beta", detail: "beta detail", isFinal: true },
];

function mockMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PipelineDiagram — reduced motion", () => {
  it("shows the final node's settled state immediately when prefers-reduced-motion is set", () => {
    mockMatchMedia(true);
    render(
      <PipelineDiagram nodes={NODES} finalStyle="ceremonial" finalAccent="safety" ariaLabel="test pipeline" />
    );
    // No intermediate "not yet revealed" state to wait out -- content is
    // present synchronously.
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("beta detail")).toBeInTheDocument();
  });
});

describe("PipelineDiagram — static (non-interactive) rendering", () => {
  it("renders plain divs, not buttons, when interactive is false", () => {
    mockMatchMedia(false);
    render(<PipelineDiagram nodes={NODES} finalStyle="quiet" finalAccent="info" ariaLabel="static pipeline" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders buttons when interactive is true", () => {
    mockMatchMedia(false);
    render(
      <PipelineDiagram nodes={NODES} finalStyle="quiet" finalAccent="info" ariaLabel="interactive pipeline" interactive />
    );
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });
});
