# GluVerse Testing Guide

## Backend

```bash
backend/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
backend/.venv/bin/python -m py_compile backend/app.py backend/wsgi.py tests/test_backend_api.py scripts/smoke_test.py
```

Coverage includes:

- auth login/register/me/logout behavior
- malformed JSON and validation failures
- CSRF protection for unsafe requests
- cross-user access rejection
- health/readiness behavior
- stale versus fresh glucose alert behavior
- achievement deduplication
- community content moderation
- meal, insulin, emergency contact, and shop persistence
- demo reset production blocking
- disabled CGM/email integration behavior

## Frontend

```bash
cd frontend
npm install
CI=true npm test -- --runInBand
npm run build
```

Manual browser smoke areas:

- login and route refresh
- dashboard glucose state
- glucose, meal, insulin, settings, achievements, community, emergency, and shop pages
- logout and expired-session handling
- mobile navigation
- form labels, keyboard focus, and visible error/empty/loading states
- disabled CGM/email integration messaging

## Live HTTP Smoke

Start the app, then run:

```bash
BASE_URL=http://127.0.0.1:5000 python3 scripts/smoke_test.py
```

The smoke script uses browser-like cookies and CSRF headers. It exits nonzero on unexpected status codes.

## Docker Verification

Requires Docker:

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:5000/api/health
curl --fail http://127.0.0.1:5000/api/ready
BASE_URL=http://127.0.0.1:5000 python3 scripts/smoke_test.py
```

Persistence and recovery:

```bash
PERSISTENCE_STATE_FILE=/tmp/gluverse-smoke.json BASE_URL=http://127.0.0.1:5000 python3 scripts/smoke_test.py
docker compose restart backend
docker compose down
docker compose up -d
```

Confirm the smoke user and records remain available after restart and container recreation.

## Release Verdict Rule

Do not call the app production-ready unless backend tests, frontend build, Docker Compose startup, live smoke, restart persistence, and backup/restore are all personally verified in the target environment.
