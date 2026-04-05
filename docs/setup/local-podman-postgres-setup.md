# Local Setup — Podman PostgreSQL + Service Intelligence/Mobile

This is the recommended local path for running PranaScan end-to-end when you want PostgreSQL in Podman Desktop and the service-intelligence/mobile running directly on your machine.

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

## 2. Configure and start the service-intelligence module

```bash
cd service-intelligence
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Important local settings in `service-intelligence/.env`:

- `DATABASE_URL`
- `AUTO_CREATE_TABLES=false` unless you intentionally want a throwaway schema outside Alembic
- `INTERNAL_SERVICE_TOKEN`
- `ENVIRONMENT=development`
- `DEBUG=false`

## 3. Configure and start the mobile app

```bash
cd mobile
cp .env.example .env
npm install
npx expo start
```

If you have not configured the OIDC provider yet, follow
[local-oidc-keycloak-setup.md](local-oidc-keycloak-setup.md) first.

Important:

- `EXPO_PUBLIC_CORE_API_URL=http://localhost:8080` works only for simulator/emulator on the same machine.
- `EXPO_PUBLIC_OIDC_ISSUER=http://localhost:8081/realms/pranapulse` must point at the issuer used by `service-core`.
- `EXPO_PUBLIC_OIDC_CLIENT_ID=pranapulse-mobile` must match a public client registered in your OIDC provider.
- `EXPO_PUBLIC_OIDC_AUDIENCE=pranapulse-core` should produce access tokens accepted by `service-core`.
- `mobile/app.json` now declares the `pranascan://auth/callback` redirect scheme. For native OIDC login, prefer a dev build or simulator/emulator setup where that redirect is reachable.
- For a physical phone, replace `localhost` with your machine LAN IP.

Example:

```bash
EXPO_PUBLIC_CORE_API_URL=http://192.168.1.25:8080
EXPO_PUBLIC_OIDC_ISSUER=http://192.168.1.25:8081/realms/pranapulse
EXPO_PUBLIC_OIDC_CLIENT_ID=pranapulse-mobile
EXPO_PUBLIC_OIDC_AUDIENCE=pranapulse-core
```

## 4. First-run checklist

- service-intelligence health check works at `http://localhost:8000/health`
- service-core health endpoints are reachable on `http://localhost:8080`
- database migrations completed successfully
- mobile app can request camera and microphone permissions
- mobile sign-in succeeds against the configured OIDC issuer
- scan session creation succeeds against service-core

## 5. Migration troubleshooting

If `alembic upgrade head` fails with duplicate table or duplicate index errors on an
older local database, that database was likely created by the previous dev
auto-create path instead of Alembic. The current migrations are now tolerant of
that state, so rerunning `alembic upgrade head` should adopt the schema.

If the local schema is still badly drifted after that, recreate the Podman
volume and rerun the setup steps.

## 6. Optional integrations you can leave off locally

- Telegram
- WhatsApp
- ABHA / ABDM
- internal agent secret

The app still works locally without those, but those features will remain inactive until credentials are provided.
