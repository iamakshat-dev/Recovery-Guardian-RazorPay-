import "@testing-library/jest-dom/vitest";

// jsdom does not implement matchMedia. A global, minimal polyfill here
// (defaulting to "no match" -- i.e. prefers-reduced-motion: reduce and
// prefers-color-scheme: light both report false, same as most CI
// environments) means every test using useTheme/useReducedMotion works
// without each file re-declaring its own mock; a test that needs a
// SPECIFIC match (e.g. reduced-motion: true) still overrides this with
// its own vi.stubGlobal, as PipelineDiagram.test.tsx already does.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
