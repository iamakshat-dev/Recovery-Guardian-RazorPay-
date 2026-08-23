import { useEffect, useState } from "react";
import { useReducedMotion } from "../../lib/useReducedMotion";

interface PipelineNode {
  label: string;
  detail: string;
  isFinal?: boolean;
}

const NODES: PipelineNode[] = [
  { label: "Payment Event", detail: "Canonical PaymentEvent" },
  { label: "Feature Builder", detail: "26 frozen features" },
  { label: "ML Classifier", detail: "CalibratedRootCauseClassifier" },
  { label: "Policy Engine", detail: "RulesPolicyEngine" },
  { label: "Action", detail: "BLOCK_RECONCILE", isFinal: true },
];

/**
 * Overview architecture preview (Milestone 1 spec section 20). The
 * final node deliberately shows the WEBHOOK_AMBIGUITY safety outcome
 * (BLOCK_RECONCILE) with the one ceremonial animation this milestone
 * uses (spec section 29's "Safety Signature Moment") — everything else
 * uses the same restrained fade/rise reveal as the rest of the page.
 * This is a static preview, not the interactive Decision Pipeline page
 * (a later milestone).
 */
export function PipelinePreview() {
  const reducedMotion = useReducedMotion();
  const [revealed, setRevealed] = useState(reducedMotion);
  const [safetyRevealed, setSafetyRevealed] = useState(reducedMotion);

  useEffect(() => {
    if (reducedMotion) return;
    const t1 = window.setTimeout(() => setRevealed(true), 30);
    const t2 = window.setTimeout(() => setSafetyRevealed(true), 30 + NODES.length * 40 + 200);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [reducedMotion]);

  return (
    <section aria-labelledby="pipeline-heading" className="border-b border-border px-6 py-14 md:px-10">
      <div className="mx-auto max-w-4xl">
        <h2 id="pipeline-heading" className="text-xl font-semibold text-text-primary">
          Decision pipeline
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-text-secondary">
          Every transaction travels the same fixed path. The explanation
          layer (not shown here) reads the result of this pipeline — it
          has no authority to change it.
        </p>

        <ol className="mt-8 flex flex-col gap-2 md:flex-row md:items-stretch md:gap-3" aria-label="Decision pipeline stages">
          {NODES.map((node, index) => {
            const isLast = node.isFinal;
            const nodeRevealed = isLast ? safetyRevealed : revealed;
            return (
              <li key={node.label} className="flex flex-1 items-center gap-2 md:flex-col md:items-stretch">
                <div
                  className={[
                    "flex-1 rounded border p-4 transition-all ease-guardian-out",
                    reducedMotion ? "duration-0" : "duration-300",
                    nodeRevealed ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
                    isLast
                      ? safetyRevealed
                        ? "border-safety/40 bg-safety/[0.06]"
                        : "border-border bg-bg-surface"
                      : "border-border bg-bg-surface",
                  ].join(" ")}
                  style={!reducedMotion ? { transitionDelay: `${index * 40}ms` } : undefined}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                      {String(index + 1).padStart(2, "0")}
                    </p>
                    {isLast ? (
                      <span
                        aria-hidden="true"
                        className={[
                          "font-mono text-sm transition-opacity ease-guardian-out",
                          reducedMotion ? "duration-0" : "duration-500",
                          safetyRevealed ? "opacity-100" : "opacity-0",
                        ].join(" ")}
                      >
                        🔒
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1.5 text-sm font-medium text-text-primary">{node.label}</p>
                  <p
                    className={[
                      "mt-0.5 font-mono text-xs",
                      isLast && safetyRevealed ? "text-safety" : "text-text-muted",
                    ].join(" ")}
                  >
                    {node.detail}
                  </p>
                </div>
                {index < NODES.length - 1 ? (
                  <span aria-hidden="true" className="hidden shrink-0 text-text-muted md:block md:self-center">
                    &rarr;
                  </span>
                ) : null}
              </li>
            );
          })}
        </ol>
        <p className="mt-4 text-xs text-text-muted">
          Shown for a representative WEBHOOK_AMBIGUITY transaction — the
          hard safety override that never becomes DEFER_RETRY.
        </p>
      </div>
    </section>
  );
}
