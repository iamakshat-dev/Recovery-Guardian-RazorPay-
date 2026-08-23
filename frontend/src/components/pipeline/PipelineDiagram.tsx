import { useEffect, useState } from "react";
import { useReducedMotion } from "../../lib/useReducedMotion";

export interface PipelineDiagramNode {
  id: string;
  label: string;
  detail: string;
  isFinal?: boolean;
}

export type PipelineFinalStyle = "ceremonial" | "quiet";
export type PipelineFinalAccent = "safety" | "info" | "warning" | "neutral";

interface PipelineDiagramProps {
  nodes: PipelineDiagramNode[];
  finalStyle: PipelineFinalStyle;
  finalAccent: PipelineFinalAccent;
  interactive?: boolean;
  selectedNodeId?: string | null;
  onSelectNode?: (id: string) => void;
  ariaLabel: string;
  footnote?: string;
}

const ACCENT_STYLES: Record<PipelineFinalAccent, { border: string; bg: string; text: string }> = {
  safety: { border: "border-safety/40", bg: "bg-safety/[0.06]", text: "text-safety" },
  info: { border: "border-info/40", bg: "bg-info/[0.06]", text: "text-info" },
  warning: { border: "border-warning/40", bg: "bg-warning/[0.06]", text: "text-warning" },
  neutral: { border: "border-border", bg: "bg-bg-surface", text: "text-text-primary" },
};

/**
 * The SINGLE shared pipeline visual (Milestone 2 spec section 3/26) —
 * used both by the Overview's static preview and the interactive
 * Decision Pipeline page. There is exactly one implementation of node
 * design, connection lines, the lock/glow ceremony, and the quiet
 * settle transition; presentation context (static vs interactive) is
 * the only thing that differs between call sites.
 *
 * `finalStyle="ceremonial"` is reserved for BLOCK_RECONCILE — the hard
 * safety override earns the lock + glow. Every other action
 * (`DEFER_RETRY`, `HUMAN_REVIEW`, ...) uses `finalStyle="quiet"`: a
 * simple, calm settle into its accent color, no lock, no glow. This is
 * a presentational mapping from an already-known action string to a
 * badge-like accent color — the same pattern `ProvenanceBadge` already
 * uses — never a computation of the action itself.
 */
export function PipelineDiagram({
  nodes,
  finalStyle,
  finalAccent,
  interactive = false,
  selectedNodeId = null,
  onSelectNode,
  ariaLabel,
  footnote,
}: PipelineDiagramProps) {
  const reducedMotion = useReducedMotion();
  const [revealed, setRevealed] = useState(reducedMotion);
  const [finalRevealed, setFinalRevealed] = useState(reducedMotion);

  useEffect(() => {
    setRevealed(reducedMotion);
    setFinalRevealed(reducedMotion);
    if (reducedMotion) return;

    const finalDelay = finalStyle === "ceremonial" ? 500 : 250;
    const t1 = window.setTimeout(() => setRevealed(true), 30);
    const t2 = window.setTimeout(() => setFinalRevealed(true), 30 + nodes.length * 40 + finalDelay);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
    // Re-run the reveal sequence whenever the underlying scenario changes
    // (nodes array identity changes on scenario switch).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion, nodes, finalStyle]);

  const accent = ACCENT_STYLES[finalAccent];

  return (
    <div>
      <ol
        className="flex flex-col gap-2 md:flex-row md:items-stretch md:gap-3"
        aria-label={ariaLabel}
      >
        {nodes.map((node, index) => {
        const isLast = Boolean(node.isFinal);
        const nodeRevealed = isLast ? finalRevealed : revealed;
        const isSelected = interactive && selectedNodeId === node.id;

        const cardClassName = [
          "min-w-0 flex-1 rounded border p-4 text-left transition-all ease-guardian-out",
          reducedMotion ? "duration-0" : "duration-300",
          nodeRevealed ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
          isLast ? (finalRevealed ? `${accent.border} ${accent.bg}` : "border-border bg-bg-surface") : "border-border bg-bg-surface",
          interactive ? "cursor-pointer hover:border-text-muted focus-visible:outline-2 focus-visible:outline-info" : "",
          isSelected ? "ring-1 ring-info" : "",
        ].join(" ");

        const cardStyle = !reducedMotion ? { transitionDelay: `${index * 40}ms` } : undefined;

        const content = (
          <>
            <div className="flex items-center justify-between gap-2">
              <p className="font-mono text-[11px] uppercase tracking-wider text-text-muted">
                {String(index + 1).padStart(2, "0")}
              </p>
              {isLast && finalStyle === "ceremonial" ? (
                <span
                  aria-hidden="true"
                  className={[
                    "font-mono text-sm transition-opacity ease-guardian-out",
                    reducedMotion ? "duration-0" : "duration-500",
                    finalRevealed ? "opacity-100" : "opacity-0",
                  ].join(" ")}
                >
                  🔒
                </span>
              ) : null}
            </div>
            <p className="mt-1.5 text-sm font-medium text-text-primary">{node.label}</p>
            <p className={["mt-0.5 break-words font-mono text-xs", isLast && finalRevealed ? accent.text : "text-text-muted"].join(" ")}>
              {node.detail}
            </p>
          </>
        );

          return (
            <li key={node.id} className="flex min-w-0 flex-1 items-center gap-2 md:flex-col md:items-stretch">
              {interactive ? (
                <button
                  type="button"
                  className={cardClassName}
                  style={cardStyle}
                  aria-expanded={isSelected}
                  aria-controls="pipeline-node-detail"
                  onClick={() => onSelectNode?.(node.id)}
                >
                  {content}
                </button>
              ) : (
                <div className={cardClassName} style={cardStyle}>
                  {content}
                </div>
              )}
              {index < nodes.length - 1 ? (
                <span aria-hidden="true" className="hidden shrink-0 text-text-muted md:block md:self-center">
                  &rarr;
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
      {footnote ? <p className="mt-4 text-xs text-text-muted">{footnote}</p> : null}
    </div>
  );
}
