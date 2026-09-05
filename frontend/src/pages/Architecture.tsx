import { PipelineDiagram, type PipelineDiagramNode } from "../components/pipeline/PipelineDiagram";
import { ProvenanceBadge } from "../components/ui/ProvenanceBadge";

// Same node ids/labels/details already used by the Overview preview and
// the Decision Pipeline page (Final Polish spec section 16 — "exact
// labels must match the repository's actual terminology"). This is a
// conceptual, non-scenario-bound rendering of the SAME shared
// PipelineDiagram component — not a duplicate implementation, and not
// tied to any one transaction's outcome, so `finalStyle="quiet"` and
// `finalAccent="neutral"` rather than the ceremonial BLOCK_RECONCILE
// treatment a real scenario earns elsewhere.
const NODES: PipelineDiagramNode[] = [
  { id: "payment-event", label: "Payment Event", detail: "Canonical PaymentEvent" },
  { id: "feature-builder", label: "Feature Builder", detail: "26 frozen features" },
  { id: "ml-classifier", label: "ML Classifier", detail: "CalibratedRootCauseClassifier" },
  { id: "policy-engine", label: "Policy Engine", detail: "RulesPolicyEngine" },
  { id: "action", label: "Action", detail: "DEFER_RETRY · HUMAN_REVIEW · BLOCK_RECONCILE · CUSTOMER_RECOVERY · NO_ACTION", isFinal: true },
];

/**
 * Architecture (Final Polish pass). Makes the system understandable to
 * a technical judge in about one minute. Purely conceptual — it renders
 * no snapshot data and computes nothing; it is documentation, not a
 * dashboard.
 *
 * The explanation layer is deliberately NOT a node in the pipeline
 * diagram above: it is downstream of the decision (spec section 18),
 * so it is rendered as a separate, visually distinct, dashed-border
 * callout below the solid decision path — never between Policy Engine
 * and Action, and never implying the LLM sits inside the decision path.
 */
export function Architecture() {
  return (
    <div className="px-6 py-14 md:px-10">
      <div className="mx-auto max-w-4xl">
        {/* Hero */}
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Architecture</p>
        <h1 className="mt-2 text-2xl font-semibold text-text-primary md:text-3xl">
          A safety-constrained recovery decision system, not an autonomous retry bot.
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-text-secondary">
          A frozen ML classifier produces a calibrated confidence estimate. A deterministic policy engine — never
          the model, never an LLM — decides what recovery, if any, is safe. An optional explanation layer describes
          that decision afterward; it cannot change it.
        </p>

        {/* Decision path */}
        <section aria-labelledby="decision-path-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="decision-path-heading" className="text-lg font-semibold text-text-primary">
            The decision path
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-text-secondary">
            Every transaction travels the same fixed path, in this order, with no branch that skips the policy
            engine.
          </p>
          <div className="mt-6">
            <PipelineDiagram
              nodes={NODES}
              finalStyle="quiet"
              finalAccent="neutral"
              ariaLabel="Recovery Guardian decision path"
            />
          </div>

          {/* Explanation — deliberately separate from the diagram above */}
          <div className="mt-6 flex items-start gap-3">
            <span aria-hidden="true" className="mt-2 h-px w-8 shrink-0 border-t border-dashed border-border" />
            <div className="min-w-0 flex-1 rounded border border-dashed border-border bg-bg-surface2/40 p-4">
              <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                Downstream · optional · no decision authority
              </p>
              <p className="mt-1.5 text-sm font-medium text-text-primary">Explanation layer</p>
              <p className="mt-1 text-xs text-text-secondary">
                Reads the already-made decision and describes it in prose (Claude, or a deterministic fallback when
                unavailable). It cannot alter the root-cause prediction, the policy action, or the confidence
                threshold — structurally, it only ever runs after they are fixed.
              </p>
            </div>
          </div>
        </section>

        {/* Safety boundary */}
        <section aria-labelledby="safety-boundary-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="safety-boundary-heading" className="text-lg font-semibold text-text-primary">
            The safety boundary
          </h2>
          <div className="mt-4 rounded border border-safety/30 bg-safety/[0.05] p-5">
            <p className="text-sm text-text-primary">
              The model recommends a confidence estimate; the policy engine determines whether recovery is
              permitted.
            </p>
            <p className="mt-2 text-xs text-text-secondary">
              A high-confidence prediction is not, by itself, authorization to act. When payment state is genuinely
              ambiguous (WEBHOOK_AMBIGUITY), the policy engine enforces a hard override to BLOCK_RECONCILE
              regardless of model confidence — this is a rule, not a model output, and it cannot be talked out of it
              by the explanation layer.
            </p>
          </div>
        </section>

        {/* Determinism */}
        <section aria-labelledby="determinism-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="determinism-heading" className="text-lg font-semibold text-text-primary">
            Deterministic by construction
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-text-secondary">
            The decision path is:
          </p>
          <p className="mt-3 rounded border border-border bg-bg-surface px-4 py-3 font-mono text-sm text-text-primary">
            ML confidence + deterministic policy constraints → action
          </p>
          <p className="mt-3 max-w-2xl text-sm text-text-secondary">
            never:
          </p>
          <p className="mt-3 rounded border border-dashed border-critical/30 bg-critical/[0.04] px-4 py-3 font-mono text-sm text-text-muted line-through decoration-critical/60">
            LLM → payment action
          </p>
          <p className="mt-3 text-xs text-text-muted">
            The same frozen model and the same policy rules produce the same action for the same input, every time
            — a property this project verified directly (Day 6 reproducibility proof), not a claim taken on faith.
          </p>
        </section>

        {/* Honest scope */}
        <section aria-labelledby="scope-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="scope-heading" className="text-lg font-semibold text-text-primary">
            Scope
          </h2>
          <div className="mt-4">
            <ProvenanceBadge value="SIMULATED" />
          </div>
          <ul className="mt-4 space-y-2 text-sm text-text-secondary">
            <li>Trained and evaluated on synthetic, generated payment-failure data — not live Razorpay traffic.</li>
            <li>Incident Replay is a deterministic replay of a historical synthetic incident window, not live monitoring.</li>
            <li>Recovery outcomes are produced by a counterfactual simulator, not observed production recovery.</li>
            <li>The explanation provider is optional and downstream; the system functions with or without it.</li>
            <li>No live payment execution, webhook feed, or Razorpay credentials exist anywhere in this project.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
