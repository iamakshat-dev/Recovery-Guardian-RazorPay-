export interface ScenarioOption {
  id: string;
  label: string;
}

interface ScenarioSelectorProps {
  options: ScenarioOption[];
  selectedId: string;
  onSelect: (id: string) => void;
}

/**
 * A compact demo/engineering control — three buttons, not a slider or a
 * game-like toggle (Milestone 2 spec section 10). Implemented as a
 * pressed-button group (`aria-pressed`) rather than a full custom
 * `role="radiogroup"` with roving tabindex, so every option remains
 * independently, unambiguously keyboard-reachable via Tab.
 */
export function ScenarioSelector({ options, selectedId, onSelect }: ScenarioSelectorProps) {
  return (
    <div>
      <p id="scenario-selector-label" className="font-mono text-xs uppercase tracking-wider text-text-muted">
        Scenario
      </p>
      <div role="group" aria-labelledby="scenario-selector-label" className="mt-2 flex flex-wrap gap-2">
        {options.map((option) => {
          const isSelected = option.id === selectedId;
          return (
            <button
              key={option.id}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onSelect(option.id)}
              className={[
                "rounded border px-3 py-2 text-left font-mono text-xs transition-colors duration-150",
                isSelected
                  ? "border-info/50 bg-info/10 text-text-primary"
                  : "border-border bg-bg-surface text-text-secondary hover:border-text-muted hover:text-text-primary",
              ].join(" ")}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
