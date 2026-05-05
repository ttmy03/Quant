from trading_app.monte_carlo import calculate_max_drawdown, simulate_portfolio_paths


def test_max_drawdown_uses_running_peak() -> None:
    assert calculate_max_drawdown([100, 120, 90, 130]) == 0.25


def test_monte_carlo_is_deterministic_and_reports_risk_metrics() -> None:
    returns = [0.001, -0.002, 0.003, 0.0005, -0.001]
    first = simulate_portfolio_paths(returns, paths=250, horizon_days=30, seed=7)
    second = simulate_portfolio_paths(returns, paths=250, horizon_days=30, seed=7)

    assert first == second
    assert first.paths == 250
    assert first.horizon_days == 30
    assert first.value_at_risk_95 >= 0
    assert first.conditional_value_at_risk_95 >= first.value_at_risk_95
    assert 0 <= first.probability_of_ruin <= 1
