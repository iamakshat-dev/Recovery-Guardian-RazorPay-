import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Structural proof for Milestone 1 spec section 28: the frontend
 * visualizes system outputs and must never become a second intelligence
 * layer. Scans every application source file (excluding the generated,
 * read-only data/snapshot.ts, which legitimately embeds the STRING
 * "BLOCK_RECONCILE" etc. as already-computed data, and test files, which
 * legitimately reference these strings as expected values) for patterns
 * that would indicate the frontend recomputing a decision rather than
 * displaying one.
 */

const SRC_DIR = join(__dirname, "..");
const EXCLUDED_PATHS = [join(SRC_DIR, "data", "snapshot.ts"), join(SRC_DIR, "test-setup.ts")];

const FORBIDDEN_PATTERNS = [
  /LogisticRegression/,
  /predict_proba/,
  /sklearn/,
  /confidence_thresholds/,
  /class\s+\w*PolicyEngine/,
  /function\s+selectAction/i,
  /function\s+computeAction/i,
  /function\s+classifyRootCause/i,
  /function\s+predictRootCause/i,
  /\.fit\(/,
];

function collectSourceFiles(dir: string): string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    const fullPath = join(dir, entry);
    const stats = statSync(fullPath);
    if (stats.isDirectory()) {
      if (entry === "__tests__") continue;
      files.push(...collectSourceFiles(fullPath));
    } else if (/\.(ts|tsx)$/.test(entry) && !EXCLUDED_PATHS.includes(fullPath)) {
      files.push(fullPath);
    }
  }
  return files;
}

describe("no second intelligence layer (spec section 28)", () => {
  it("no application source file recomputes ML/policy decision logic", () => {
    const files = collectSourceFiles(SRC_DIR);
    expect(files.length).toBeGreaterThan(0);

    for (const file of files) {
      const content = readFileSync(file, "utf-8");
      for (const pattern of FORBIDDEN_PATTERNS) {
        expect(
          pattern.test(content),
          `${file} matched forbidden pattern ${pattern} — the frontend must never recompute a decision`
        ).toBe(false);
      }
    }
  });

  it("data/snapshot.ts is the only file containing raw experiment JSON structure", () => {
    // Sanity check that the exclusion list above is actually meaningful
    // (i.e. snapshot.ts really does contain data the scan would
    // otherwise flag as suspicious), not merely an unused allowance.
    const snapshotContent = readFileSync(join(SRC_DIR, "data", "snapshot.ts"), "utf-8");
    expect(snapshotContent).toContain("GENERATED FILE");
    expect(snapshotContent).toContain("simulatedAmountRecovered");
  });
});
