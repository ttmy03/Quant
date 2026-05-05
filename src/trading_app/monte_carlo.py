from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from trading_app.schemas import MonteCarloSummary


def calculate_max_drawdown(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, 1 - (value / peak))
    return float(max_drawdown)


def simulate_portfolio_paths(
    returns: Sequence[float],
    *,
    initial_value: float = 10_000.0,
    horizon_days: int = 252,
    paths: int = 1000,
    seed: int = 42,
    ruin_threshold: float = 0.7,
) -> MonteCarloSummary:
    """Simulate terminal portfolio outcomes and common downside metrics."""

    clean_returns = np.array(list(returns), dtype=float)
    clean_returns = clean_returns[np.isfinite(clean_returns)]
    mean_return = float(clean_returns.mean()) if clean_returns.size else 0.0002
    volatility = float(clean_returns.std(ddof=1)) if clean_returns.size > 1 else 0.01
    volatility = max(volatility, 1e-9)

    rng = np.random.default_rng(seed)
    sampled_returns = rng.normal(mean_return, volatility, size=(paths, horizon_days))
    sampled_returns = np.clip(sampled_returns, -0.95, 1.0)

    growth = np.cumprod(1 + sampled_returns, axis=1)
    values = initial_value * growth
    terminal_values = values[:, -1]
    terminal_returns = (terminal_values / initial_value) - 1

    fifth_percentile_return = np.percentile(terminal_returns, 5)
    tail_returns = terminal_returns[terminal_returns <= fifth_percentile_return]
    value_at_risk_95 = max(0.0, -float(fifth_percentile_return))
    conditional_var_95 = max(0.0, -float(tail_returns.mean())) if tail_returns.size else 0.0

    running_peaks = np.maximum.accumulate(values, axis=1)
    drawdowns = 1 - (values / running_peaks)
    max_drawdowns = drawdowns.max(axis=1)
    ruin_value = initial_value * ruin_threshold
    probability_of_ruin = float((values.min(axis=1) <= ruin_value).mean())

    chart_values = np.concatenate([np.full((paths, 1), initial_value), values], axis=1)
    fan_chart = [
        {
            "day": int(day),
            "p05": round(float(np.percentile(chart_values[:, day], 5)), 4),
            "p50": round(float(np.percentile(chart_values[:, day], 50)), 4),
            "p95": round(float(np.percentile(chart_values[:, day], 95)), 4),
        }
        for day in range(horizon_days + 1)
    ]
    histogram_counts, histogram_edges = np.histogram(terminal_values, bins=20)
    terminal_value_histogram = [
        {
            "lower": round(float(histogram_edges[index]), 4),
            "upper": round(float(histogram_edges[index + 1]), 4),
            "count": int(count),
        }
        for index, count in enumerate(histogram_counts)
    ]

    return MonteCarloSummary(
        seed=seed,
        paths=paths,
        horizon_days=horizon_days,
        initial_value=initial_value,
        mean_terminal_value=round(float(terminal_values.mean()), 4),
        median_terminal_value=round(float(np.median(terminal_values)), 4),
        p05_terminal_value=round(float(np.percentile(terminal_values, 5)), 4),
        p95_terminal_value=round(float(np.percentile(terminal_values, 95)), 4),
        value_at_risk_95=round(value_at_risk_95, 6),
        conditional_value_at_risk_95=round(conditional_var_95, 6),
        max_drawdown_p95=round(float(np.percentile(max_drawdowns, 95)), 6),
        probability_of_ruin=round(probability_of_ruin, 6),
        mean_terminal_return=round(float(terminal_returns.mean()), 6),
        fan_chart=fan_chart,
        terminal_value_histogram=terminal_value_histogram,
    )
