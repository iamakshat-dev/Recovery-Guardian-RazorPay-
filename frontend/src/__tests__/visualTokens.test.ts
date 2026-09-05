import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Visual System spec section 27: no component may hardcode a raw color
 * — every color must resolve through the semantic token layer in
 * index.css so a theme switch reskins the whole app. `index.css` itself
 * is the one legitimate exception (it IS the token definitions).
 */

const SRC_DIR = join(__dirname, "..");
const EXCLUDED_PATHS = [join(SRC_DIR, "index.css")];
const RAW_COLOR_PATTERN = /#[0-9A-Fa-f]{3,8}\b|rgba\(\s*\d|hsla?\(/;

function collectSourceFiles(dir: string): string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    const fullPath = join(dir, entry);
    const stats = statSync(fullPath);
    if (stats.isDirectory()) {
      if (entry === "__tests__") continue;
      files.push(...collectSourceFiles(fullPath));
    } else if (/\.(ts|tsx|css)$/.test(entry) && !EXCLUDED_PATHS.includes(fullPath)) {
      files.push(fullPath);
    }
  }
  return files;
}

describe("no hardcoded colors outside the token layer (Visual System spec section 27)", () => {
  it("no application source file encodes a raw hex/rgba/hsl color", () => {
    const files = collectSourceFiles(SRC_DIR);
    expect(files.length).toBeGreaterThan(0);

    for (const file of files) {
      const content = readFileSync(file, "utf-8");
      expect(
        RAW_COLOR_PATTERN.test(content),
        `${file} contains a raw color literal — use a semantic token (rgb(var(--color-...))) or a Tailwind class instead`
      ).toBe(false);
    }
  });

  it("index.css is the only file defining the raw color values (sanity check on the exclusion)", () => {
    const content = readFileSync(join(SRC_DIR, "index.css"), "utf-8");
    expect(RAW_COLOR_PATTERN.test(content)).toBe(true);
    expect(content).toContain("--color-bg");
    expect(content).toContain('[data-theme="light"]');
  });
});
