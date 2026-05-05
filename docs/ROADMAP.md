# Roadmap

## Phase 1: Paper-MVP

- FastAPI-Dashboard, SQLite-Persistenz und Audit-Logs.
- Alpaca-Paper-Adapter mit `DRY_RUN`-Default.
- Moving-Average-Crossover-Strategie.
- Synthetischer Long-only-Backtest mit Transaktionslog, Equity Curve und Basis-Metriken.
- Monte-Carlo-Simulation mit VaR, CVaR, Drawdown und Ruin-Wahrscheinlichkeit.
- Rekursive Parameterverbesserung mit Risikolimits.
- CI mit Pytest.

## Phase 2: Research-Qualitaet

- Historische Marktdaten sauber ueber Alpaca Data API laden und cachen.
- Backtesting gegen historische Marktdaten mit Transaktionskosten, Slippage und erweiterten Positionsgroessen.
- Strategie-Registry fuer mehrere Strategien.
- Walk-forward-Validierung und Out-of-sample-Auswertung.
- Erweiterte Metriken: Sortino, Calmar, Exposure, Turnover, Hit Rate.

## Phase 3: Betrieb und Beobachtbarkeit

- Rollenmodell fuer Hermes/Codex/Admin-Aktionen.
- Strukturierte Logs, Metriken und Alerting.
- Review-Queue fuer vorgeschlagene Strategieaenderungen.
- Exportierbare Audit-Berichte.
- Secrets-Management fuer Deployment-Umgebungen.

## Phase 4: Streng kontrollierte Ausfuehrung

- Paper-Trading-Scheduler mit Kill-Switch.
- Order-Reconciliation gegen Alpaca.
- Positions- und Cash-Abgleich.
- Manuelle Freigabe fuer jede Aenderung an Execution-Regeln.

Live-Trading bleibt ausserhalb dieser Roadmap, bis ein separates Sicherheits-, Compliance- und Betriebsdesign existiert.
