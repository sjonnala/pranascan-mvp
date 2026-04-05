# Service Intelligence

`service-intelligence` is the FastAPI module for PranaPulse's intelligence and
signal-processing workflows.

## Scope

- rPPG and voice-processing fallback logic
- internal compute-only gRPC contracts for `service-core`
- HTTP health/root endpoints plus audit middleware for operational visibility
- Alembic migrations for the remaining FastAPI persistence model

## Layout

```text
service-intelligence/
├── app/
├── alembic/
├── tests/
├── alembic.ini
└── requirements.txt
```

## Local Commands

```bash
cd service-intelligence
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

For repo-local tests from this module:

```bash
cd service-intelligence
python -m pytest -q
```

## Internal Boundary

`service-intelligence` now exposes the private compute boundary used by
`service-core` in the phase-4 migration state:

- `pranapulse.intelligence.scan.v1.ScanIntelligenceService/EvaluateScan` over
  gRPC on `0.0.0.0:50051` by default

This contract is intended for `service-core` only and requires the
`x-internal-service-token` gRPC metadata header.

The default `app.main:app` entrypoint is now internal-only and no longer mounts
the legacy `python-jose` HTTP auth surface or the retired internal HTTP
scan-evaluation route. Mobile/public traffic is expected to terminate at
`service-core`.
