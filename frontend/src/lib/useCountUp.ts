import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "./useReducedMotion";

/**
 * Counts from 0 to `target` over `durationMs` (spec: 600-800ms), easing
 * out, no bounce. Disabled entirely under prefers-reduced-motion, in
 * which case the target value is shown immediately — this is a reveal
 * animation, never a claim of live-streaming data.
 */
export function useCountUp(target: number, durationMs = 700): number {
  const reducedMotion = useReducedMotion();
  const [value, setValue] = useState(reducedMotion ? target : 0);
  const frameRef = useRef<number>();

  useEffect(() => {
    if (reducedMotion) {
      setValue(target);
      return;
    }

    const start = performance.now();
    const from = 0;

    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(1, elapsed / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic, no bounce
      setValue(from + (target - from) * eased);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      }
    }

    frameRef.current = requestAnimationFrame(tick);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs, reducedMotion]);

  return value;
}
