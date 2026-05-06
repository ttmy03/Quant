from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Sequence

import numpy as np

from trading_app.config import Settings
from trading_app.monte_carlo import calculate_max_drawdown, simulate_portfolio_paths
from trading_app.risk import RiskGuard
from trading_app.schemas import Bar
from trading_app.strategy import MovingAverageCrossoverStrategy, StrategyParams


@dataclass(frozen=True)
class CandidateEvaluation:
    params: StrategyParams
    total_return: float
    sharpe: float
    max_drawdown: float
    probability_of_ruin: float
    accepted: bool
    rejection_reasons: tuple[str, ...]


class RecursiveImprover:
    """Evaluate candidate strategy parameters and promote only risk-approved changes."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.risk_guard = RiskGuard(settings)

    def propose_candidates(self, base: StrategyParams) -> list[StrategyParams]:
        candidates: set[StrategyParams] = {base}
        for short_delta in (-2, -1, 1, 2):
            short_window = max(2, base.short_window + short_delta)
            for long_delta in (-5, -2, 2, 5):
                long_window = max(short_window + 1, base.long_window + long_delta)
                candidates.add(
                    replace(
                        base,
                        short_window=short_window,
                        long_window=long_window,
                        min_crossover_pct=base.min_crossover_pct,
                    )
                )
        candidates.add(
            replace(
                base,
                short_window=base.short_window,
                long_window=base.long_window,
                min_crossover_pct=max(0.0, base.min_crossover_pct / 2),
            )
        )
        candidates.add(
            replace(
                base,
                short_window=base.short_window,
                long_window=base.long_window,
                min_crossover_pct=min(0.2, base.min_crossover_pct * 2),
            )
        )
        return sorted(candidates, key=lambda item: (item.long_window, item.short_window, item.min_crossover_pct))

    def improve(
        self,
        base: StrategyParams,
        bars: Sequence[Bar],
        *,
        seed: int = 42,
    ) -> dict[str, object]:
        base_evaluation = self.evaluate_candidate(base, bars, seed=seed)
        evaluations = [self.evaluate_candidate(candidate, bars, seed=seed) for candidate in self.propose_candidates(base)]
        accepted = [evaluation for evaluation in evaluations if evaluation.accepted]
        best = max(accepted, key=lambda item: (item.sharpe, item.total_return), default=base_evaluation)
        promoted = best.accepted and best.sharpe > base_evaluation.sharpe
        selected = best if promoted else base_evaluation

        return {
            "promoted": promoted,
            "selected_params": asdict(selected.params),
            "base": self._evaluation_dict(base_evaluation),
            "best": self._evaluation_dict(best),
            "evaluations": [self._evaluation_dict(evaluation) for evaluation in evaluations],
        }

    def evaluate_candidate(
        self,
        params: StrategyParams,
        bars: Sequence[Bar],
        *,
        seed: int = 42,
    ) -> CandidateEvaluation:
        returns = self._backtest_returns(params, bars)
        if not returns:
            return CandidateEvaluation(params, 0.0, 0.0, 0.0, 0.0, False, ("not enough bars",))

        equity = list(np.cumprod(1 + np.array(returns)))
        total_return = float(equity[-1] - 1)
        max_drawdown = calculate_max_drawdown(equity)
        volatility = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
        sharpe = float(np.mean(returns) / volatility * np.sqrt(252)) if volatility > 0 else 0.0
        monte_carlo = simulate_portfolio_paths(
            returns,
            initial_value=10_000,
            horizon_days=90,
            paths=500,
            seed=seed,
        )
        risk_decision = self.risk_guard.strategy_metrics_pass(
            max_drawdown=max_drawdown,
            probability_of_ruin=monte_carlo.probability_of_ruin,
        )

        return CandidateEvaluation(
            params=params,
            total_return=round(total_return, 6),
            sharpe=round(sharpe, 6),
            max_drawdown=round(max_drawdown, 6),
            probability_of_ruin=monte_carlo.probability_of_ruin,
            accepted=risk_decision.allowed,
            rejection_reasons=tuple(risk_decision.reasons),
        )

    def _backtest_returns(self, params: StrategyParams, bars: Sequence[Bar]) -> list[float]:
        if len(bars) <= params.long_window:
            return []

        strategy = MovingAverageCrossoverStrategy(params)
        position = 0.0
        returns: list[float] = []
        for index in range(1, len(bars)):
            signal = strategy.generate_signal(bars[index].symbol, bars[:index])
            if signal.action == "BUY":
                position = 1.0
            elif signal.action == "SELL":
                position = 0.0

            previous_close = bars[index - 1].close
            current_close = bars[index].close
            market_return = (current_close / previous_close) - 1
            returns.append(position * market_return)

        return returns

    @staticmethod
    def _evaluation_dict(evaluation: CandidateEvaluation) -> dict[str, object]:
        return {
            "params": asdict(evaluation.params),
            "total_return": evaluation.total_return,
            "sharpe": evaluation.sharpe,
            "max_drawdown": evaluation.max_drawdown,
            "probability_of_ruin": evaluation.probability_of_ruin,
            "accepted": evaluation.accepted,
            "rejection_reasons": list(evaluation.rejection_reasons),
        }
