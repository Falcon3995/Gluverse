# GluVerse

GluVerse is a Flask + React private-beta MVP for tracking glucose, meals, insulin logs, settings, achievements, community posts, emergency contacts, and saved supply requests.

This repository is not a medical device, not emergency care, and not HIPAA/compliance-ready by code changes alone. For beta use, invite a small group, keep expectations explicit, and do not use the app as the only health record.

## Current Production-Readiness Position

- Core workflows use real API/data paths.
- Authentication uses HttpOnly session cookies plus CSRF protection.
- User-scoped API routes enforce ownership checks.
- Production config requires a strong secret, explicit CORS origins, and PostgreSQL.
- Docker Compose is configured for a local production-like app + PostgreSQL stack.
- CGM, email notification delivery, and AI/vendor integrations are disabled and return clear responses until real credentials and verification exist.
- Docker verification is still required on a machine with Docker installed.

## Local Development

```bash
cp .env.example .env
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python app.py
```

In another terminal:

```bash
cd frontend
npm install
npm start
```

The local dev seed account is available only outside production when demo seeding is enabled.

## Verified Checks

Run backend tests:

```bash
backend/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Run syntax checks:

```bash
backend/.venv/bin/python -m py_compile backend/app.py backend/wsgi.py tests/test_backend_api.py scripts/smoke_test.py
```

Build frontend:

```bash
cd frontend
npm install
npm run build
```

## Production-Like Docker Compose

Docker is required for these checks.

Set production-like secrets:

```bash
cp .env.example .env
# Edit .env:
# APP_ENV=production
# FLASK_ENV=production
# FLASK_DEBUG=0
# SECRET_KEY=<at least 32 random chars>
# NVIDIA_API_KEY=<your NVIDIA API key>
# NVIDIA_COACH_MODEL=<normal coach model>
# NVIDIA_SAFETY_MODEL=<safety/triage model>
# POSTGRES_PASSWORD=<strong local password>
# CORS_ORIGINS=http://localhost:5000
# DEMO_RESET_ENABLED=false
```

Start and verify:

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:5000/api/health
curl --fail http://127.0.0.1:5000/api/ready
BASE_URL=http://127.0.0.1:5000 python3 scripts/smoke_test.py
```

Persistence proof:

```bash
PERSISTENCE_STATE_FILE=/tmp/gluverse-smoke.json BASE_URL=http://127.0.0.1:5000 python3 scripts/smoke_test.py
docker compose restart backend
BASE_URL=http://127.0.0.1:5000 SMOKE_USERNAME="$(python3 -c 'import json;print(json.load(open("/tmp/gluverse-smoke.json"))["username"])')" SMOKE_PASSWORD="$(python3 -c 'import json;print(json.load(open("/tmp/gluverse-smoke.json"))["password"])')" python3 scripts/smoke_test.py
```

## Backup And Restore

PostgreSQL backup:

```bash
DATABASE_URL="postgresql://gluverse:<password>@127.0.0.1:5432/gluverse" scripts/backup_db.sh
```

PostgreSQL restore is intentionally guarded:

```bash
ALLOW_RESTORE=1 scripts/restore_db.sh backups/gluverse-postgres-YYYYMMDDTHHMMSSZ.sql.gz "postgresql://gluverse:<password>@127.0.0.1:5432/gluverse"
```

Stop write traffic before restoring.

## Beta Release Limits

- Do not claim HIPAA compliance or medical-device status.
- Do not use for emergency decisions.
- Do not use as the sole record of insulin or glucose.
- Avoid unnecessary identifying health details in community posts.
- Tell beta users data may be removed during maintenance.
- Establish a support and incident-reporting channel before inviting users.
