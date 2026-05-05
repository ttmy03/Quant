# Paper Quant

Automatisierte Aktientrading-App als sicherer MVP-Scaffold fuer Research und Paper Trading. Das Projekt enthaelt FastAPI, ein minimales Dashboard, Alpaca-Paper-Grenzen, SQLite-Audit-Logs, eine Moving-Average-Strategie, Monte-Carlo-Simulation und eine rekursive Verbesserungslogik.

Keine Finanzberatung. Dieses Repository ist nicht fuer Live-Geld-Trading vorkonfiguriert.

## Sicherheitsgrundsaetze

- `DRY_RUN=true` ist der Default: Orders werden nicht an Alpaca gesendet.
- `PAPER_TRADING_ONLY=true` ist der Default: Nicht-Paper-Endpunkte werden blockiert.
- API-Keys gehoeren nur in lokale Umgebungsvariablen oder `.env`, nie in Git.
- `AUTH_ENABLED=true` schuetzt Dashboard und API per signiertem Session-Cookie.
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

## Auth Setup

Dashboard und API sind standardmaessig geschuetzt. `/health` und `/login` bleiben oeffentlich.

Setze fuer VPS/Production mindestens:

```bash
AUTH_ENABLED=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=...
SESSION_SECRET=...
SESSION_COOKIE_NAME=paper_quant_session
SESSION_MAX_AGE_SECONDS=86400
```

Passwort-Hash erzeugen:

```bash
PYTHONPATH=src python -c "from trading_app.auth import hash_password; import getpass; print(hash_password(getpass.getpass()))"
```

Session Secret erzeugen:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`ADMIN_PASSWORD` wird als lokale/dev Convenience akzeptiert, wenn kein `ADMIN_PASSWORD_HASH` gesetzt ist. Fuer `APP_ENV=production` bricht der Serverstart ab, wenn `AUTH_ENABLED=true` ist und `SESSION_SECRET` oder Admin-Credentials fehlen. Fuer lokale Tests kann `AUTH_ENABLED=false` gesetzt werden.

Nutze fuer einen oeffentlich erreichbaren VPS HTTPS vor dem Login. Real-Order-Submission bleibt in diesem Scaffold weiterhin durch `DRY_RUN=true` blockiert.

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

Falls Port `8000` auf einem VPS bereits belegt ist, kann der Host-Port in `.env` geaendert werden:

```bash
HOST_PORT=8010
docker compose up --build -d
```

## API-Auszug

- `GET /health`: Healthcheck.
- `GET /login` / `POST /login`: Dashboard-Login.
- `POST /logout`: Session-Cookie loeschen.
- `GET /api/auth/me`: angemeldeter User und Safety State.
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
