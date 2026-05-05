from __future__ import annotations

import argparse
import json
import subprocess
import sys

from trading_app.config import get_settings
from trading_app.data import generate_synthetic_bars, returns_from_bars
from trading_app.monte_carlo import simulate_portfolio_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper Quant utility CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    server_parser = subparsers.add_parser("run-server", help="Run the FastAPI dashboard server")
    server_parser.add_argument("--host", default="0.0.0.0")
    server_parser.add_argument("--port", type=int, default=8000)

    simulation_parser = subparsers.add_parser("run-simulation", help="Run deterministic Monte Carlo simulation")
    simulation_parser.add_argument("--seed", type=int, default=42)
    simulation_parser.add_argument("--paths", type=int, default=1000)
    simulation_parser.add_argument("--horizon-days", type=int, default=252)

    subparsers.add_parser("run-tests", help="Run pytest")

    args = parser.parse_args()
    if args.command == "run-server":
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "trading_app.main:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ]
        raise SystemExit(subprocess.call(command))

    if args.command == "run-simulation":
        settings = get_settings()
        symbol = settings.default_symbols[0] if settings.default_symbols else "AAPL"
        bars = generate_synthetic_bars(symbol=symbol, seed=args.seed)
        summary = simulate_portfolio_paths(
            returns_from_bars(bars),
            seed=args.seed,
            paths=args.paths,
            horizon_days=args.horizon_days,
        )
        print(json.dumps(summary.model_dump(), indent=2, sort_keys=True))
        return

    if args.command == "run-tests":
        raise SystemExit(subprocess.call([sys.executable, "-m", "pytest"]))


if __name__ == "__main__":
    main()
