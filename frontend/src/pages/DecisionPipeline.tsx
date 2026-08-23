import { useMemo, useState } from "react";
import { NodeDetailPanel } from "../components/pipeline/NodeDetailPanel";
import { PipelineDiagram, type PipelineDiagramNode } from "../components/pipeline/PipelineDiagram";
import { ScenarioSelector } from "../components/pipeline/ScenarioSelector";
import { pipelineStyleForAction } from "../lib/pipelineAccent";
import { snapshot } from "../data/snapshot";
import { ProvenanceBadge } from "../components/ui/ProvenanceBadge";

const SCENARIO_OPTIONS = [
  { id: "webhook_ambiguity", label: "WEBHOOK AMBIGUITY" },
  { id: "infrastructure_high_confidence", label: "INFRASTRUCTURE — HIGH CONFIDENCE" },
  { id: "infrastructure_low_confidence", label: "INFRASTRUCTURE — LOW CONFIDENCE" },
] as const;

type ScenarioKey = (typeof SCENARIO_OPTIONS)[number]["id"];

function buildNodes(scenario: (typeof snapshot)["day14"]["scenarios"][ScenarioKey]): PipelineDiagramNode[] {
  return [
    { id: "payment-event", label: "Payment Event", detail: "Canonical PaymentEvent" },
    { id: "feature-builder", label: "Feature Builder", detail: "26 frozen features" },
    {
      id: "ml-classifier",
      label: "ML Classifier",
      detail: `${scenario.prediction.rootCause} · ${scenario.prediction.probability.toFixed(2)}`,
    },
    { id: "policy-engine", label: "Policy Engine", detail: "RulesPolicyEngine" },
    { id: "action", label: "Recovery Action", detail: scenario.policy.action, isFinal: true },
  ];
}

/**
 * The interactive Decision Pipeline (Milestone 2 spec sections 8-12,
 * 16-18). Reuses the exact PipelineDiagram component the Overview's
 * static preview uses — this page only supplies interactive=true,
 * scenario-driven nodes, and a click handler. No decision logic lives
 * here: every node's content comes directly from
 * `snapshot.day14.scenarios`, itself sourced from the frozen
 * experiments/results/day14_demo.json.
 */
export function DecisionPipeline() {
  const [scenarioId, setScenarioId] = useState<ScenarioKey>("webhook_ambiguity");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const scenario = snapshot.day14.scenarios[scenarioId];
  // Stable node-array identity across re-renders that don't change the
  // scenario (e.g. selecting a node) -- otherwise PipelineDiagram's
  // reveal effect (keyed on `nodes`) would incorrectly re-run and
  // re-animate every already-settled node on every click.
  const nodes = useMemo(() => buildNodes(scenario), [scenario]);
  const { finalStyle, finalAccent } = pipelineStyleForAction(scenario.policy.action);

  function handleScenarioSelect(id: string) {
    setScenarioId(id as ScenarioKey);
    setSelectedNodeId(null);
  }

  return (
    <div className="px-6 py-14 md:px-10">
      <div className="mx-auto max-w-4xl">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Interactive</p>
        <h1 className="mt-2 text-2xl font-semibold text-text-primary md:text-3xl">Decision pipeline</h1>
        <p className="mt-3 max-w-2xl text-sm text-text-secondary">
          Switch between three real, authoritative scenarios. The
          frontend never recomputes a prediction or an action — it
          switches between already-decided records and displays them.
        </p>

        <div className="mt-8">
          <ScenarioSelector options={[...SCENARIO_OPTIONS]} selectedId={scenarioId} onSelect={handleScenarioSelect} />
        </div>

        <div className="mt-8">
          <PipelineDiagram
            nodes={nodes}
            finalStyle={finalStyle}
            finalAccent={finalAccent}
            interactive
            selectedNodeId={selectedNodeId}
            onSelectNode={(id) => setSelectedNodeId((current) => (current === id ? null : id))}
            ariaLabel={`Decision pipeline for ${scenario.scenarioLabel}`}
          />
        </div>

        <NodeDetailPanel nodeId={selectedNodeId} scenario={scenario} />

        <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-border pt-6">
          <ProvenanceBadge value="OBSERVED" />
          <p className="text-xs text-text-muted">
            Prediction and policy fields are observed, deterministic code
            behavior. Outcome fields (shown in the Recovery Action detail)
            are simulated — see the Action node.
          </p>
        </div>
      </div>
    </div>
  );
}
