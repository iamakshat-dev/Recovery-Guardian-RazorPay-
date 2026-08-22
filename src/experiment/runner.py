"""
Recovery Guardian — Day 9 Experiment Runner

    run_experiment(payment_events, experiment_seed) -> list[PerTransactionResult]

ONE runner, not one per strategy. For every transaction: build the one
canonical RecoveryEvidence (via the real calibrated classifier, used
identically for every strategy's outcome scoring), derive one common
random seed, ask each of the four strategies for its action, and score
every action through the single shared
src.recovery.simulator.estimate_outcome().
"""

from typing import List

from src.domain.models import PaymentEvent
from src.experiment.random_state import derive_transaction_seed
from src.experiment.results import PerTransactionResult
from src.experiment.strategies import (
    EXPERIMENT_EVALUATION_TIME,
    GuardianStrategy,
    NaiveRetryStrategy,
    NoActionStrategy,
    RulesOnlyStrategy,
)
from src.recovery.evidence import RecoveryEvidence
from src.recovery.simulator import estimate_outcome


def build_strategies() -> dict:
    """Fresh strategy instances for one experiment run. GuardianStrategy
    holds no state across transactions (see its docstring) — a fresh
    instance per run is not required for correctness, but keeps each
    run_experiment() call fully self-contained."""
    return {
        "NAIVE_RETRY": NaiveRetryStrategy(),
        "RULES_ONLY": RulesOnlyStrategy(),
        "GUARDIAN": GuardianStrategy(),
        "NO_ACTION": NoActionStrategy(),
    }


def run_experiment(
    payment_events: List[PaymentEvent],
    experiment_seed: int,
) -> List[PerTransactionResult]:
    strategies = build_strategies()
    guardian = strategies["GUARDIAN"]

    results: List[PerTransactionResult] = []
    for event in payment_events:
        # 1. Same evidence for every strategy: one real calibrated
        #    prediction, reused for the canonical RecoveryEvidence.
        prediction = guardian.predict(event)
        evidence = RecoveryEvidence.from_payment_event_and_prediction(event, prediction)

        # 2. Deterministic common random seed for this transaction --
        #    identical across all four strategies below.
        seed = derive_transaction_seed(event.transaction_id, experiment_seed)

        # 3-5. Each strategy selects an action; every action is scored
        #      through the SAME estimate_outcome(), with the SAME
        #      evidence and the SAME seed.
        for strategy_name, strategy in strategies.items():
            action = strategy.select_action(event)
            outcome = estimate_outcome(
                evidence,
                action,
                seed=seed,
                timestamp=EXPERIMENT_EVALUATION_TIME,
            )
            results.append(
                PerTransactionResult(
                    transaction_id=event.transaction_id,
                    strategy=strategy_name,
                    selected_action=action.value,
                    root_cause=prediction.root_cause.value,
                    root_cause_probability=prediction.probability,
                    transaction_amount=event.amount,
                    recovered=outcome.recovered,
                    amount_recovered=outcome.amount_recovered,
                    duplicate_charge_risk=outcome.duplicate_charge_risk,
                    outcome_reason=outcome.outcome_reason,
                    experiment_seed=experiment_seed,
                )
            )
    return results
