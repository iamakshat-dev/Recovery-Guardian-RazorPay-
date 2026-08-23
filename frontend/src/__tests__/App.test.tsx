import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "../App";

describe("App", () => {
  it("renders without crashing", () => {
    render(<App />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("renders the primary navigation", () => {
    render(<App />);
    expect(screen.getByRole("navigation", { name: /sections/i })).toBeInTheDocument();
  });

  it("renders the Overview by default", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { name: /safe recovery decisions for payment failures/i })
    ).toBeInTheDocument();
  });
});
