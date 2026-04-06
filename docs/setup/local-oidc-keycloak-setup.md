# Local OIDC Setup With Keycloak

This guide sets up a local OIDC provider for the current PranaPulse monorepo.
It matches the defaults used by:

- [service-core/src/main/resources/application.yml](/Users/satishjonnala/Documents/Data Team - AIML/github-repos/pranascan-mvp/service-core/src/main/resources/application.yml)
- [mobile/src/hooks/useOidcAuth.ts](/Users/satishjonnala/Documents/Data Team - AIML/github-repos/pranascan-mvp/mobile/src/hooks/useOidcAuth.ts)
- [mobile/app.json](/Users/satishjonnala/Documents/Data Team - AIML/github-repos/pranascan-mvp/mobile/app.json)

The target shape is:

- realm: `pranapulse`
- issuer: `http://localhost:8081/realms/pranapulse`
- mobile client id: `pranapulse-mobile`
- required audience for `service-core`: `pranapulse-core`
- mobile redirect URI: `pranascan://auth/callback`

## Quick Start (Automated — Recommended)

The realm, client, PKCE settings, audience mapper, and test user are all
pre-configured in [`keycloak/pranapulse-realm.json`](/Users/satishjonnala/Documents/Data Team - AIML/github-repos/pranascan-mvp/keycloak/pranapulse-realm.json)
and auto-imported when `docker-compose.yml` starts Keycloak.

### Using Podman Desktop

```bash
podman compose up -d
```

### Using Docker

```bash
docker compose up -d
```

This starts **all four services** in one command:

| Service               | Port  | Description                        |
| --------------------- | ----- | ---------------------------------- |
| `db`                  | 5433  | Postgres 16                        |
| `keycloak`            | 8081  | Keycloak 26.1 with realm imported  |
| `service-intelligence`| 8000  | Python intelligence service        |
| `service-core`        | 8080  | Spring Boot core service           |

`service-core` waits for both `db` and `keycloak` to be healthy before starting.

### Pre-configured test user

| Field    | Value                      |
| -------- | -------------------------- |
| username | `testuser`                 |
| email    | `testuser@pranapulse.dev`  |
| password | `testpassword`             |

### Verify the setup

```bash
# Keycloak OIDC discovery
curl http://localhost:8081/realms/pranapulse/.well-known/openid-configuration

# JWK set
curl http://localhost:8081/realms/pranapulse/protocol/openid-connect/certs
```

Then configure the mobile app (see [section 7](#7-configure-the-mobile-app) below)
and sign in with the test user.

### Customising the realm

Edit `keycloak/pranapulse-realm.json` and restart:

```bash
podman compose down keycloak
podman compose up -d keycloak
```

Keycloak re-imports the realm on every `start-dev --import-realm` startup.

---

## Manual Setup (Reference)

The sections below document each manual step if you prefer to run Keycloak
standalone or need to understand what the realm import automates.

### Prerequisites

- Podman Desktop or Docker installed
- `service-core` running locally or via compose
- Expo mobile app running in a simulator, emulator, or dev build

## 1. Start Keycloak

Using Podman:

```bash
podman run --name pranapulse-keycloak \
  -p 8081:8080 \
  -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:26.1 start-dev
```

Using Docker:

```bash
docker run --name pranapulse-keycloak \
  -p 8081:8080 \
  -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:26.1 start-dev
```

Open:

- `http://localhost:8081/admin`

Log in with:

- username: `admin`
- password: `admin`

## 2. Create The Realm

Create a new realm:

- `pranapulse`

After that, the expected issuer becomes:

```text
http://localhost:8081/realms/pranapulse
```

## 3. Create The Mobile Client

In Keycloak, create a new client with these settings:

- Client ID: `pranapulse-mobile`
- Client type / protocol: `openid-connect`
- Client authentication: `Off`
- Authorization: `Off`
- Standard flow: `On`
- Direct access grants: `Off`
- Service accounts: `Off`

Configure these redirect settings:

- Valid redirect URIs:
  - `pranascan://auth/callback`
- Valid post logout redirect URIs:
  - `pranascan://auth/callback`
- Web origins:
  - `*` for local development

Configure PKCE:

- PKCE code challenge method: `S256`

This client is intended to be a public mobile client, not a confidential backend client.

## 4. Add The Audience Mapper

`service-core` validates that incoming access tokens contain audience `pranapulse-core`.

In the `pranapulse-mobile` client, add a mapper:

- Mapper type: `Audience`
- Name: `service-core-audience`
- Included custom audience: `pranapulse-core`
- Add to access token: `On`
- Add to ID token: `Off`

Without this mapper, login may succeed in the app, but `service-core` will reject the bearer token.

## 5. Create A Test User

Create a user in realm `pranapulse`:

- username: any value you want
- email: set a real-looking email
- first name / last name: optional
- enabled: `On`

Under Credentials:

- set a password
- disable temporary password

`service-core` provisions the local user projection from token claims such as:

- `sub`
- `email`
- `name`
- `preferred_username`

## 6. Configure `service-core`

If you are running `service-core` locally, the defaults already point to this issuer.

If you want to set them explicitly:

```bash
APP_SECURITY_ISSUER_URI=http://localhost:8081/realms/pranapulse
APP_SECURITY_JWK_SET_URI=http://localhost:8081/realms/pranapulse/protocol/openid-connect/certs
APP_SECURITY_REQUIRED_AUDIENCE=pranapulse-core
```

These correspond to:

- [service-core/src/main/resources/application.yml](/Users/satishjonnala/Documents/Data Team - AIML/github-repos/pranascan-mvp/service-core/src/main/resources/application.yml)

## 7. Configure The Mobile App

Set these values in [mobile/.env.example](/Users/satishjonnala/Documents/Data Team - AIML/github-repos/pranascan-mvp/mobile/.env.example) or your local `mobile/.env`:

```bash
EXPO_PUBLIC_CORE_API_URL=http://localhost:8080
EXPO_PUBLIC_OIDC_ISSUER=http://localhost:8081/realms/pranapulse
EXPO_PUBLIC_OIDC_CLIENT_ID=pranapulse-mobile
EXPO_PUBLIC_OIDC_AUDIENCE=pranapulse-core
```

Optional:

```bash
EXPO_PUBLIC_OIDC_SCOPES=openid profile email offline_access
```

The app uses the custom scheme declared in [mobile/app.json](/Users/satishjonnala/Documents/Data Team - AIML/github-repos/pranascan-mvp/mobile/app.json):

```text
pranascan://auth/callback
```

## 8. Physical Phone vs Simulator

If you are using a physical phone, replace `localhost` with your machine LAN IP everywhere:

- `EXPO_PUBLIC_CORE_API_URL`
- `EXPO_PUBLIC_OIDC_ISSUER`
- `APP_SECURITY_ISSUER_URI`
- `APP_SECURITY_JWK_SET_URI`

Example:

```bash
EXPO_PUBLIC_CORE_API_URL=http://192.168.1.25:8080
EXPO_PUBLIC_OIDC_ISSUER=http://192.168.1.25:8081/realms/pranapulse
APP_SECURITY_ISSUER_URI=http://192.168.1.25:8081/realms/pranapulse
APP_SECURITY_JWK_SET_URI=http://192.168.1.25:8081/realms/pranapulse/protocol/openid-connect/certs
```

The issuer URL must stay consistent. If the mobile app gets tokens from one issuer URL string and `service-core` validates against another, auth will fail.

## 9. Run The Services

Start `service-core`:

```bash
cd service-core
./mvnw spring-boot:run
```

Start `service-intelligence`:

```bash
cd service-intelligence
source .venv/bin/activate
uvicorn app.main:app --reload
```

Start the mobile app:

```bash
cd mobile
npm install
npx expo start
```

For native redirect handling, prefer a simulator/emulator or a dev build over a pure Expo Go workflow.

## 10. Verify The Setup

Check Keycloak discovery:

```bash
curl http://localhost:8081/realms/pranapulse/.well-known/openid-configuration
```

Check the JWK set:

```bash
curl http://localhost:8081/realms/pranapulse/protocol/openid-connect/certs
```

Then in the mobile app:

1. tap the sign-in button
2. log in with the Keycloak test user
3. return to the app
4. proceed through consent

If login succeeds, `service-core` should accept the token and `GET /api/v1/auth/me` should provision or load the user.

## Troubleshooting

### Login succeeds but `service-core` returns 401

Most likely causes:

- the access token is missing audience `pranapulse-core`
- the issuer URL used by `service-core` does not exactly match the token issuer
- the mobile app is still pointing at `localhost` while the device cannot reach your host machine

### The sign-in button never works

Check:

- `EXPO_PUBLIC_OIDC_ISSUER`
- `EXPO_PUBLIC_OIDC_CLIENT_ID`
- Keycloak is reachable from the device or simulator
- the redirect URI `pranascan://auth/callback` is allowed on the client

### The redirect returns to the browser instead of the app

Check:

- `scheme: "pranascan"` is present in [mobile/app.json](/Users/satishjonnala/Documents/Data Team - AIML/github-repos/pranascan-mvp/mobile/app.json)
- the client redirect URI in Keycloak exactly matches `pranascan://auth/callback`
- you are using a native runtime that supports the redirect cleanly

