import { formatCount, formatPercent, formatRupees } from "../../lib/format";
import { ProvenanceBadge } from "../ui/ProvenanceBadge";
import type { snapshot } from "../../data/snapshot";

type Scenario = (typeof snapshot)["day14"]["scenarios"][keyof (typeof snapshot)["day14"]["scenarios"]];

interface NodeDetailPanelProps {
  nodeId: string | null;
  scenario: Scenario;
}

const NODE_TITLES: Record<string, string> = {
  "payment-event": "Payment Event",
  "feature-builder": "Feature Builder",
  "ml-classifier": "ML Classifier",
  "policy-engine": "Policy Engine",
  action: "Recovery Action",
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/60 py-2 text-sm last:border-b-0">
      <span className="text-text-muted">{label}</span>
      <span className="font-mono text-text-primary">{value}</span>
    </div>
  );
}

/**
 * Inline expansion, not a modal (Milestone 2 spec section 18). Shown
 * below the pipeline once a node is selected. Every value here is read
 * directly from the scenario record sourced by
 * scripts/generate_frontend_snapshot.py from experiments/results/
 * day14_demo.json — nothing here is computed.
 */
export function NodeDetailPanel({ nodeId, scenario }: NodeDetailPanelProps) {
  if (!nodeId) return null;

  return (
    <div
      id="pipeline-node-detail"
      role="region"
      aria-live="polite"
      aria-label={`${NODE_TITLES[nodeId] ?? "Node"} detail`}
      className="mt-4 rounded border border-border bg-bg-surface p-5"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-text-primary">{NODE_TITLES[nodeId] ?? "Detail"}</h2>
        <ProvenanceBadge value="OBSERVED" />
      </div>

      {nodeId === "payment-event" ? (
        <div className="mt-3">
          <Row label="Transaction ID" value={scenario.transactionId} />
          <Row label="Amount" value={formatRupees(scenario.paymentEvent.amount)} />
          <Row label="Payment method" value={scenario.paymentEvent.paymentMethod} />
          <Row label="Failure code" value={scenario.paymentEvent.failureCode} />
          <Row label="Retry count" value={formatCount(scenario.paymentEvent.retryCount)} />
          <Row label="Webhook delay" value={`${scenario.paymentEvent.webhookDelaySeconds}s`} />
        </div>
      ) : null}

      {nodeId === "feature-builder" ? (
        <div className="mt-3">
          <Row label="Feature count" value="26 frozen features" />
          <Row label="Computed where" value="src/features/build_features.py (backend)" />
          <p className="mt-3 text-xs text-text-muted">
            Canonical feature vector — the frontend never computes a
            feature. This value is fixed by the frozen feature contract,
            not generated per scenario.
          </p>
        </div>
      ) : null}

      {nodeId === "ml-classifier" ? (
        <div className="mt-3">
          <Row label="Predicted root cause" value={scenario.prediction.rootCause} />
          <Row label="Model probability" value={scenario.prediction.probability.toFixed(4)} />
          <Row label="Model version" value={scenario.prediction.modelVersion} />
          <p className="mt-3 text-xs text-text-muted">
            A calibrated probability, not a certainty — the policy engine
            decides what, if anything, is authorized at this confidence
            level.
          </p>
        </div>
      ) : null}

      {nodeId === "policy-engine" ? (
        <div className="mt-3">
          <Row label="Action authorized" value={scenario.policy.action} />
          <Row label="Reason code" value={scenario.policy.reason} />
          <Row
            label="Confidence threshold"
            value={scenario.policy.thresholdIfApplicable === null ? "Not applicable — hard safety override" : formatPercent(scenario.policy.thresholdIfApplicable, 0)}
          />
          <Row label="Policy version" value={scenario.policy.version} />
        </div>
      ) : null}

      {nodeId === "action" ? (
        <div className="mt-3">
          <Row label="Recovery action" value={scenario.policy.action} />
          <div className="mt-3 flex items-center justify-between gap-3 border-b border-border/60 py-2 text-sm">
            <span className="text-text-muted">Simulated outcome</span>
            <span className="flex items-center gap-2">
              <ProvenanceBadge value="SIMULATED" />
            </span>
          </div>
          <Row label="Recovered (simulated)" value={scenario.outcome.recovered ? "Yes" : "No"} />
          <Row
            label="Amount recovered (simulated)"
            value={scenario.outcome.amountRecovered !== null ? formatRupees(scenario.outcome.amountRecovered) : "Unavailable"}
          />
          <Row label="Duplicate-charge risk (simulated)" value={scenario.outcome.duplicateChargeRisk ? "Yes" : "No"} />
        </div>
      ) : null}
    </div>
  );
}
