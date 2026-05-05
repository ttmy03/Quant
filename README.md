# Paper Quant

Automatisierte Aktientrading-App als sicherer MVP-Scaffold fuer Research und Paper Trading. Das Projekt enthaelt FastAPI, ein minimales Dashboard, Alpaca-Paper-Grenzen, SQLite-Audit-Logs, eine Moving-Average-Strategie, Monte-Carlo-Simulation und eine rekursive Verbesserungslogik.

Keine Finanzberatung. Dieses Repository ist nicht fuer Live-Geld-Trading vorkonfiguriert.

## Sicherheitsgrundsaetze

- `DRY_RUN=true` ist der Default: Orders werden nicht an Alpaca gesendet.
- `PAPER_TRADING_ONLY=true` ist der Default: Nicht-Paper-Endpunkte werden blockiert.
- API-Keys gehoeren nur in lokale Umgebungsvariablen oder `.env`, nie in Git.
- Jede Order, Simulation und Strategieaenderung wird als Audit Event gespeichert.
- Strategieparameter werden nur verbessert, wenn Risikolimits eingehalten werden.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

Alpaca Paper Keys optional in `.env` setzen:

```bash
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets
DRY_RUN=true
PAPER_TRADING_ONLY=true
```

Ohne Keys laeuft das Dashboard in lokalem Safe Mode mit synthetischen Demo-Daten.

## Befehle

```bash
# Tests
python -m pytest

# Server
PYTHONPATH=src python -m trading_app.cli run-server --port 8000

# Simulation
PYTHONPATH=src python -m trading_app.cli run-simulation --seed 42 --paths 1000
```

Dashboard: `http://localhost:8000`

## API-Auszug

- `GET /health`: Healthcheck.
- `GET /api/portfolio/status`: Alpaca Account-Status und letzte Bars.
- `GET /api/orders`: gespeicherte Orders.
- `POST /api/orders`: risikogepruefte Paper/Dry-Run Order.
- `GET /api/strategy`: aktuelle Strategieparameter und Demo-Signal.
- `PUT /api/strategy`: Strategieparameter aktualisieren.
- `POST /api/simulations/monte-carlo`: Monte-Carlo-Simulation ausfuehren.
- `POST /api/improvement/run`: Kandidatenparameter testen und ggf. uebernehmen.
- `GET /api/audit-events`: Audit Log.

## Architektur

Siehe [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Hermes/Codex Workflow

Hermes gibt Ziele, Prioritaeten und Review-Anweisungen. Codex setzt diese als konkrete Git-Aenderungen um, fuehrt Tests aus und committed nachvollziehbar. Beide sollen ueber Git-Zugriff und Pull-Request-Reviews arbeiten, damit Strategie-, Risiko- und Execution-Aenderungen nachvollziehbar bleiben.

## Roadmap

Siehe [docs/ROADMAP.md](docs/ROADMAP.md).
