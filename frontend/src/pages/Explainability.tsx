import { useState } from "react";
import { PipelineDiagram, type PipelineDiagramNode } from "../components/pipeline/PipelineDiagram";
import { ScenarioSelector } from "../components/pipeline/ScenarioSelector";
import { ProvenanceBadge } from "../components/ui/ProvenanceBadge";
import { formatPercent } from "../lib/format";
import { pipelineStyleForAction } from "../lib/pipelineAccent";
import { snapshot } from "../data/snapshot";

const SCENARIO_OPTIONS = [
  { id: "webhook_ambiguity", label: "WEBHOOK AMBIGUITY" },
  { id: "infrastructure_high_confidence", label: "INFRASTRUCTURE / HIGH CONFIDENCE" },
  { id: "infrastructure_low_confidence", label: "INFRASTRUCTURE / LOW CONFIDENCE" },
] as const;

type ScenarioKey = (typeof SCENARIO_OPTIONS)[number]["id"];

function evidenceChainNodes(
  scenario: (typeof snapshot)["day14"]["scenarios"][ScenarioKey]
): PipelineDiagramNode[] {
  return [
    { id: "payment-event", label: "Payment Event", detail: scenario.paymentEvent.failureCode },
    {
      id: "ml-prediction",
      label: "ML Prediction",
      detail: `${scenario.prediction.rootCause} · ${scenario.prediction.probability.toFixed(2)}`,
    },
    { id: "policy-decision", label: "Policy Decision", detail: scenario.policy.reason },
    { id: "recovery-action", label: "Recovery Action", detail: scenario.policy.action, isFinal: true },
  ];
}

/**
 * Explainability (Milestone 3). Answers "why did Guardian make this
 * decision?" downstream of an already-computed decision — it never
 * computes one. Reuses the exact scenario records M2 already produced
 * (frontend/src/data/snapshot.ts's `day14.scenarios`), extended in this
 * milestone with the same artifact's `explanation` object — see
 * scripts/generate_frontend_snapshot.py's module docstring for the
 * data-continuity contract.
 *
 * `explanation.summary`/`safetyNote` are prose, rendered as text only.
 * Nothing on this page parses that prose to determine anything — the
 * root cause, action, and reason all come from the same structured
 * `prediction`/`policy` fields the Decision Pipeline page uses.
 */
export function Explainability() {
  const [scenarioId, setScenarioId] = useState<ScenarioKey>("webhook_ambiguity");
  const scenario = snapshot.day14.scenarios[scenarioId];
  const { finalAccent } = pipelineStyleForAction(scenario.policy.action);
  const invariantHolds = scenario.safetyInvariantCheck.unchanged;

  return (
    <div className="px-6 py-14 md:px-10">
      <div className="mx-auto max-w-4xl">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Explainability</p>
        <h1 className="mt-2 text-2xl font-semibold text-text-primary md:text-3xl">
          Why did Guardian make this decision?
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-text-secondary">
          The explanation below describes an already-computed decision. It
          has no authority to change it — see the safety invariant at the
          bottom of this page.
        </p>

        <div className="mt-8">
          <ScenarioSelector options={[...SCENARIO_OPTIONS]} selectedId={scenarioId} onSelect={(id) => setScenarioId(id as ScenarioKey)} />
        </div>

        {/* Decision summary */}
        <section aria-labelledby="decision-summary-heading" className="mt-10 border-t border-border pt-8">
          <div className="flex items-center justify-between gap-3">
            <h2 id="decision-summary-heading" className="text-lg font-semibold text-text-primary">
              Decision summary
            </h2>
            <ProvenanceBadge value="OBSERVED" />
          </div>
          <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded border border-border bg-bg-surface p-4">
              <dt className="font-mono text-xs uppercase tracking-wider text-text-muted">Root cause</dt>
              <dd className="mt-1 font-mono text-lg text-text-primary">{scenario.prediction.rootCause}</dd>
              <dd className="mt-1 text-xs text-text-muted">
                Model probability {scenario.prediction.probability.toFixed(4)} — a calibrated confidence, not a certainty.
              </dd>
            </div>
            <div className="rounded border border-border bg-bg-surface p-4">
              <dt className="font-mono text-xs uppercase tracking-wider text-text-muted">Policy action</dt>
              <dd className="mt-1 font-mono text-lg text-text-primary">{scenario.policy.action}</dd>
              <dd className="mt-1 text-xs text-text-muted">
                Reason: {scenario.policy.reason}
                {scenario.policy.thresholdIfApplicable !== null
                  ? ` (threshold ${formatPercent(scenario.policy.thresholdIfApplicable, 0)})`
                  : " (no threshold — hard safety override)"}
              </dd>
            </div>
          </dl>
        </section>

        {/* Evidence chain */}
        <section aria-labelledby="evidence-chain-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="evidence-chain-heading" className="text-lg font-semibold text-text-primary">
            Evidence chain
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            Payment event → ML prediction → policy decision → recovery
            action. Each stage is real, deterministic system output.
          </p>
          <div className="mt-6">
            <PipelineDiagram
              nodes={evidenceChainNodes(scenario)}
              finalStyle={finalAccent === "safety" ? "ceremonial" : "quiet"}
              finalAccent={finalAccent}
              ariaLabel={`Evidence chain for ${scenario.scenarioLabel}`}
            />
          </div>
        </section>

        {/* Explanation */}
        <section aria-labelledby="explanation-heading" className="mt-10 border-t border-border pt-8">
          <div className="flex items-center justify-between gap-3">
            <h2 id="explanation-heading" className="text-lg font-semibold text-text-primary">
              Explanation
            </h2>
          </div>
          <div className="mt-4 rounded border border-border bg-bg-surface p-5">
            <p className="text-sm leading-relaxed text-text-primary">{scenario.explanation.summary}</p>
            <p className="mt-3 text-sm leading-relaxed text-text-secondary">{scenario.explanation.safetyNote}</p>
            <p className="mt-4 border-t border-border/60 pt-3 text-xs text-text-muted">
              Source note (verbatim from the underlying record): &ldquo;{scenario.explanation.sourceNote}&rdquo;. This
              artifact does not separately record which explanation provider (Claude or the deterministic fallback)
              produced this specific prose — both are constrained identically, so this page does not guess.
            </p>
          </div>
        </section>

        {/* Safety invariant */}
        <section aria-labelledby="safety-invariant-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="safety-invariant-heading" className="text-lg font-semibold text-text-primary">
            Safety invariant
          </h2>
          <p className="mt-2 text-sm text-text-secondary">Explanation cannot change the action.</p>
          <div
            className={[
              "mt-4 flex flex-col items-center gap-3 rounded border p-6 text-center sm:flex-row sm:justify-center sm:gap-6",
              invariantHolds ? "border-safety/30 bg-safety/[0.04]" : "border-critical/40 bg-critical/[0.06]",
            ].join(" ")}
          >
            <div>
              <p className="font-mono text-xs uppercase tracking-wider text-text-muted">Action before explanation</p>
              <p className="mt-1 font-mono text-xl font-semibold text-text-primary">
                {scenario.safetyInvariantCheck.actionBeforeExplanation}
              </p>
            </div>
            <p aria-hidden="true" className="text-2xl text-text-muted">
              =
            </p>
            <div>
              <p className="font-mono text-xs uppercase tracking-wider text-text-muted">Action after explanation</p>
              <p className={["mt-1 font-mono text-xl font-semibold", invariantHolds ? "text-safety" : "text-critical"].join(" ")}>
                {scenario.safetyInvariantCheck.actionAfterExplanation}
              </p>
            </div>
          </div>
        </section>

        {/* Provenance */}
        <section aria-labelledby="explainability-provenance-heading" className="mt-10 border-t border-border pt-8">
          <h2 id="explainability-provenance-heading" className="text-lg font-semibold text-text-primary">
            Provenance
          </h2>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded border border-border bg-bg-surface p-4">
              <ProvenanceBadge value="OBSERVED" />
              <p className="mt-2 text-xs text-text-secondary">Root cause, probability, policy action, policy reason.</p>
            </div>
            <div className="rounded border border-border bg-bg-surface p-4">
              <ProvenanceBadge value="SIMULATED" />
              <p className="mt-2 text-xs text-text-secondary">
                Recovered ({scenario.outcome.recovered ? "yes" : "no"}), amount recovered, duplicate-charge risk.
              </p>
            </div>
            <div className="rounded border border-border bg-bg-surface p-4">
              <ProvenanceBadge value="UNAVAILABLE" />
              <p className="mt-2 text-xs text-text-secondary">Real Razorpay production outcomes and monitoring.</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
