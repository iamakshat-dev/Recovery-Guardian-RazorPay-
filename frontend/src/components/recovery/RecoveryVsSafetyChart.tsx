import { formatCount, formatRupees } from "../../lib/format";
import { isValidAmount, isValidCount } from "../../lib/validate";
import { UnavailableMetric } from "../ui/UnavailableMetric";

export interface RecoveryVsSafetyPoint {
  strategy: string;
  simulatedAmountRecovered: number;
  duplicateChargeRiskCount: number;
  recoveryRate: number;
  isGuardian?: boolean;
}

interface RecoveryVsSafetyChartProps {
  points: RecoveryVsSafetyPoint[];
}

const WIDTH = 720;
const HEIGHT = 340;
const MARGIN = { top: 24, right: 32, bottom: 48, left: 56 };
const PLOT_WIDTH = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_HEIGHT = HEIGHT - MARGIN.top - MARGIN.bottom;

/**
 * The most visually important chart on the Recovery Analysis page
 * (Milestone 4 spec section 12): one aggregate point per strategy,
 * X = simulated amount recovered, Y = duplicate-charge risk count.
 * Hand-built SVG -- no chart library was already installed, and this is
 * four points, not a case that justifies adding one. Not a per-
 * transaction or per-seed scatter; strictly the four aggregate strategy
 * points confirmed available in snapshot.day10.strategyTable.
 *
 * The axis range is derived from the actual data (no truncation, no
 * cherry-picked range) and always includes zero on both axes so the
 * "lower is safer" / "further right is more simulated recovery" reading
 * is never visually distorted.
 */
export function RecoveryVsSafetyChart({ points }: RecoveryVsSafetyChartProps) {
  const valid = points.filter(
    (p) => isValidAmount(p.simulatedAmountRecovered) && isValidCount(p.duplicateChargeRiskCount)
  );

  if (valid.length === 0) {
    return <UnavailableMetric label="Recovery vs safety" reason="Day 10 strategy table failed validation." />;
  }

  const maxX = Math.max(...valid.map((p) => p.simulatedAmountRecovered)) * 1.12;
  const maxY = Math.max(1, Math.max(...valid.map((p) => p.duplicateChargeRiskCount)) * 1.25);

  const xScale = (value: number) => MARGIN.left + (value / maxX) * PLOT_WIDTH;
  const yScale = (value: number) => MARGIN.top + PLOT_HEIGHT - (value / maxY) * PLOT_HEIGHT;

  const xTicks = 4;
  const yTicks = Math.min(6, Math.max(1, Math.max(...valid.map((p) => p.duplicateChargeRiskCount))));

  return (
    <div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-labelledby="recovery-safety-chart-title recovery-safety-chart-desc"
        className="w-full"
      >
        <title id="recovery-safety-chart-title">Recovery vs safety, by strategy</title>
        <desc id="recovery-safety-chart-desc">
          A scatter plot with one point per strategy. Horizontal axis: simulated amount recovered. Vertical axis:
          duplicate-charge risk count. An accessible data table with the same values follows this chart.
        </desc>

        {/* Gridlines + Y axis ticks */}
        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const value = (maxY / yTicks) * i;
          const y = yScale(value);
          return (
            <g key={`y-${i}`}>
              <line x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y} y2={y} stroke="#252B33" strokeWidth={1} />
              <text x={MARGIN.left - 10} y={y} textAnchor="end" dominantBaseline="middle" fontSize={11} fill="#7B8794" fontFamily="ui-monospace, monospace">
                {Math.round(value)}
              </text>
            </g>
          );
        })}

        {/* X axis ticks */}
        {Array.from({ length: xTicks + 1 }, (_, i) => {
          const value = (maxX / xTicks) * i;
          const x = xScale(value);
          return (
            <g key={`x-${i}`}>
              <text
                x={x}
                y={HEIGHT - MARGIN.bottom + 20}
                textAnchor="middle"
                fontSize={11}
                fill="#7B8794"
                fontFamily="ui-monospace, monospace"
              >
                {`₹${Math.round(value / 1000)}K`}
              </text>
            </g>
          );
        })}

        {/* Axis lines */}
        <line x1={MARGIN.left} x2={MARGIN.left} y1={MARGIN.top} y2={HEIGHT - MARGIN.bottom} stroke="#252B33" strokeWidth={1.5} />
        <line
          x1={MARGIN.left}
          x2={WIDTH - MARGIN.right}
          y1={HEIGHT - MARGIN.bottom}
          y2={HEIGHT - MARGIN.bottom}
          stroke="#252B33"
          strokeWidth={1.5}
        />

        {/* Axis labels */}
        <text x={MARGIN.left + PLOT_WIDTH / 2} y={HEIGHT - 6} textAnchor="middle" fontSize={11} fill="#9AA3AE">
          Simulated amount recovered &rarr;
        </text>
        <text
          x={14}
          y={MARGIN.top + PLOT_HEIGHT / 2}
          textAnchor="middle"
          fontSize={11}
          fill="#9AA3AE"
          transform={`rotate(-90, 14, ${MARGIN.top + PLOT_HEIGHT / 2})`}
        >
          Duplicate-charge risk count
        </text>

        {/* Data points */}
        {valid.map((p) => {
          const cx = xScale(p.simulatedAmountRecovered);
          const cy = yScale(p.duplicateChargeRiskCount);
          return (
            <g key={p.strategy}>
              {p.isGuardian ? (
                <circle cx={cx} cy={cy} r={16} fill="rgba(34,197,94,0.12)" />
              ) : null}
              <circle
                cx={cx}
                cy={cy}
                r={7}
                fill={p.isGuardian ? "#22C55E" : "#60A5FA"}
                stroke="#080A0D"
                strokeWidth={2}
              />
              <text x={cx} y={cy - 14} textAnchor="middle" fontSize={11} fill="#F3F5F7" fontFamily="ui-monospace, monospace">
                {p.strategy}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Accessible text/table equivalent -- not merely a tooltip */}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[480px] border-collapse text-left text-xs">
          <caption className="sr-only">Recovery versus safety, one row per strategy</caption>
          <thead>
            <tr className="border-b border-border text-text-muted">
              <th scope="col" className="py-2 pr-4 font-mono font-normal uppercase tracking-wider">
                Strategy
              </th>
              <th scope="col" className="py-2 pr-4 font-mono font-normal uppercase tracking-wider">
                Simulated recovery
              </th>
              <th scope="col" className="py-2 pr-4 font-mono font-normal uppercase tracking-wider">
                Recovery rate
              </th>
              <th scope="col" className="py-2 font-mono font-normal uppercase tracking-wider">
                Duplicate-charge risk
              </th>
            </tr>
          </thead>
          <tbody>
            {valid.map((p) => (
              <tr key={p.strategy} className="border-b border-border/60">
                <td className="py-2 pr-4 font-mono text-text-primary">{p.strategy}</td>
                <td className="py-2 pr-4 font-mono tabular-nums text-text-secondary">
                  {formatRupees(p.simulatedAmountRecovered)}
                </td>
                <td className="py-2 pr-4 font-mono tabular-nums text-text-secondary">
                  {(p.recoveryRate * 100).toFixed(2)}%
                </td>
                <td className="py-2 font-mono tabular-nums text-text-secondary">{formatCount(p.duplicateChargeRiskCount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
