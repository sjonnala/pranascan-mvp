# Local Setup — Podman PostgreSQL + Local Backend/Mobile

This is the recommended local path for running PranaScan end-to-end when you want PostgreSQL in Podman Desktop and the backend/mobile running directly on your machine.

## Prerequisites

- Podman Desktop installed and running
- Python 3.11
- Node.js / npm
- A physical phone or emulator/simulator for Expo

## 1. Start PostgreSQL in Podman

From the repo root:

```bash
./scripts/start-postgres-podman.sh
```

If Podman Desktop is using a machine/VM on macOS, make sure it is started first:

```bash
podman machine start
```

Default local database values used by the script:

- database: `pranascan`
- user: `pranascan`
- password: `pranascan_dev_password`
- port: `5432`

You can override them with environment variables:

```bash
PRANASCAN_DB_PORT=5433 ./scripts/start-postgres-podman.sh
```

## 2. Configure and start the backend

```bash
cd backend
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Important local settings in `backend/.env`:

- `DATABASE_URL`
- `SECRET_KEY`
- `ENVIRONMENT=development`
- `DEBUG=false`

Optional local beta enablement:

```bash
BETA_ONBOARDING_ENABLED=true
BETA_SEED_INVITE_CODE=CLOSED50
```

## 3. Configure and start the mobile app

```bash
cd mobile
cp .env.example .env
npm install
npx expo start
```

Important:

- `EXPO_PUBLIC_API_URL=http://localhost:8000` works only for simulator/emulator on the same machine.
- For a physical phone, replace `localhost` with your machine LAN IP.

Example:

```bash
EXPO_PUBLIC_API_URL=http://192.168.1.25:8000
```

## 4. First-run checklist

- backend health check works at `http://localhost:8000/health`
- database migrations completed successfully
- mobile app can request camera and microphone permissions
- if beta gating is enabled, the seed invite code works
- scan session creation succeeds against the backend

## 5. Optional integrations you can leave off locally

- Telegram
- WhatsApp
- ABHA / ABDM
- internal agent secret

The app still works locally without those, but those features will remain inactive until credentials are provided.
