import { PipelineDiagram, type PipelineDiagramNode } from "../pipeline/PipelineDiagram";

const NODES: PipelineDiagramNode[] = [
  { id: "payment-event", label: "Payment Event", detail: "Canonical PaymentEvent" },
  { id: "feature-builder", label: "Feature Builder", detail: "26 frozen features" },
  { id: "ml-classifier", label: "ML Classifier", detail: "CalibratedRootCauseClassifier" },
  { id: "policy-engine", label: "Policy Engine", detail: "RulesPolicyEngine" },
  { id: "action", label: "Action", detail: "BLOCK_RECONCILE", isFinal: true },
];

/**
 * Overview architecture preview (Milestone 1 spec section 20; Milestone
 * 2 spec section 3 requires this and the interactive Decision Pipeline
 * page to share ONE underlying component — see
 * ../pipeline/PipelineDiagram.tsx). This is a thin, static, non-
 * interactive wrapper around it, always showing the WEBHOOK_AMBIGUITY
 * safety story (the one the Overview commits to). The full interactive,
 * scenario-switchable version lives at pages/DecisionPipeline.tsx.
 */
export function PipelinePreview() {
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

        <div className="mt-8">
          <PipelineDiagram
            nodes={NODES}
            finalStyle="ceremonial"
            finalAccent="safety"
            ariaLabel="Decision pipeline stages"
            footnote="Shown for a representative WEBHOOK_AMBIGUITY transaction — the hard safety override that never becomes DEFER_RETRY."
          />
        </div>
      </div>
    </section>
  );
}
