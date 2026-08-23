import type { PipelineFinalAccent, PipelineFinalStyle } from "../components/pipeline/PipelineDiagram";

/**
 * Presentational mapping ONLY: an already-known RecoveryAction string
 * (read from the authoritative Day 14 artifact) to a badge-like visual
 * accent and animation style. This does not decide, infer, or derive an
 * action from anything — it is the same "look up how to display a known
 * value" pattern `ProvenanceBadge`'s STYLES record already uses.
 * BLOCK_RECONCILE is the only action that ever earns the ceremonial
 * lock/glow (Milestone 2 spec section 17): the hard safety override.
 */
export function pipelineStyleForAction(action: string): {
  finalStyle: PipelineFinalStyle;
  finalAccent: PipelineFinalAccent;
} {
  switch (action) {
    case "BLOCK_RECONCILE":
      return { finalStyle: "ceremonial", finalAccent: "safety" };
    case "DEFER_RETRY":
      return { finalStyle: "quiet", finalAccent: "info" };
    case "HUMAN_REVIEW":
      return { finalStyle: "quiet", finalAccent: "warning" };
    default:
      return { finalStyle: "quiet", finalAccent: "neutral" };
  }
}
