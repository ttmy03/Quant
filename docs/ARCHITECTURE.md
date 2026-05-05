# Architektur

Dieses Repository ist ein Paper-Trading- und Research-Scaffold. Es ist absichtlich so gebaut, dass Live-Geld nicht der Standardpfad ist.

## Komponenten

- `trading_app.main`: FastAPI-App, REST-Endpunkte und ausgeliefertes Dashboard.
- `trading_app.alpaca`: HTTP-Grenze zu Alpaca. Orders werden nur nach Risk-Check und Paper/Dry-Run-Pruefung weitergegeben.
- `trading_app.risk`: Pre-Trade- und Strategie-Risikoregeln.
- `trading_app.strategy`: Pluggbare Strategie-Schnittstelle mit Moving-Average-Crossover-MVP.
- `trading_app.monte_carlo`: Portfolio-Pfadsimulation mit VaR, CVaR, Drawdown und Ruin-Wahrscheinlichkeit.
- `trading_app.improver`: Rekursive Parameterbewertung. Neue Parameter werden nur uebernommen, wenn Performance besser ist und Risikolimits eingehalten werden.
- `trading_app.storage`: SQLite-Persistenz fuer Audit Events, Orders und Simulationsergebnisse.
- `trading_app.static`: Minimal-Dashboard ohne Build-Step.

## Datenfluss

1. Dashboard oder CLI loest Status, Simulation, Verbesserung oder Order aus.
2. Orders werden als `OrderIntent` validiert.
3. `RiskGuard` prueft Allowlist, Notional-Limits, Tageslimit und Paper-Endpoint.
4. `AlpacaClient` fuehrt bei `DRY_RUN=true` keine externe Order aus. Bei `DRY_RUN=false` muss Alpaca konfiguriert sein und der Paper-Endpoint aktiv bleiben.
5. Jede Orderentscheidung, Simulation und Strategieaenderung wird in SQLite auditiert.

## Sicherheitsmodell

- `DRY_RUN=true` ist der Default.
- `PAPER_TRADING_ONLY=true` ist der Default.
- Keine API-Keys im Code oder in Git.
- `.env.example` dokumentiert Variablen, enthaelt aber keine Secrets.
- Live-Trading ist kein MVP-Ziel und muss vor einer Erweiterung separat entworfen, getestet und freigegeben werden.

## Hermes/Codex Workflow

Hermes kann Anforderungen, Review-Kommentare und Prioritaeten vorgeben. Codex fuehrt konkrete Repository-Aenderungen aus. Beide arbeiten ueber Git: jede relevante Aenderung soll nachvollziehbar committed werden, CI muss Tests ausfuehren, und sicherheitsrelevante Aenderungen sollen ueber Pull Requests sichtbar bleiben.
