import { ProvenanceBadge } from "../ui/ProvenanceBadge";

export function Hero() {
  return (
    <section aria-labelledby="hero-heading" className="border-b border-border px-6 py-14 md:px-10 md:py-20">
      <div className="mx-auto max-w-4xl">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">
          Recovery Guardian
        </p>
        <h1
          id="hero-heading"
          className="mt-4 text-3xl font-semibold leading-tight tracking-tight text-text-primary md:text-5xl"
        >
          Safe recovery decisions for payment failures.
        </h1>
        <p className="mt-5 max-w-2xl text-base leading-relaxed text-text-secondary md:text-lg">
          A calibrated ML classifier identifies the likely root cause of a
          payment failure. A deterministic policy engine — never the
          model, never an LLM — decides what action is safe. A shared
          simulation environment evaluates the consequence before it is
          claimed as evidence.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <ProvenanceBadge value="SIMULATED" />
          <p className="text-xs text-text-muted">
            Results below are simulated / counterfactual — not live Razorpay
            production data.
          </p>
        </div>
      </div>
    </section>
  );
}
