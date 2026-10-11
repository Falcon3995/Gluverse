# GluVerse — end-to-end engineering audit

**Date:** 10 October 2026
**Revision examined:** local main at f474bca (no application source changes made)
**Scope:** GluVerse root application. The nested OmniRoute checkout is a separate project and was excluded.
**Status terms:** PASS = executed and met the stated expectation; FAIL = executed and did not; BLOCKED = environment or unavailable integration prevented execution; NOT TESTED = inspected only. A PASS for a narrow case is not proof of clinical or production safety.

## A. Executive summary

**What this repo does:** GluVerse is a Flask API and React web app for manual glucose, meal, insulin, alert-setting, community, achievement, contact, and saved shop-request records. I assessed it as a small private beta with concurrent users and sensitive health data, not as an insulin dosing device.

The basic record flows work in an isolated test account: 105 backend tests passed, and browser registration, login, logout, glucose, meal, insulin, analytics, community, contacts, achievements, and CGM status were exercised. The most direct user-facing break is the Alerts & Settings form: every save sends numeric notification flags to an API that requires booleans, and the server rejects it. A manual glucose entry also appears as a “Live reading,” which can imply a sensor feed despite the displayed source being manual. Alerts are evaluated only when requested; configured email/SMS/push delivery is absent. CGM sync is explicitly disabled. No dosing calculator or insulin-on-board (IOB) model exists.

**Production assessment: not ready.** Production Compose lacks a TLS gateway, the Docker CI job lacks required Compose variables, startup requires NVIDIA credentials even when the README says that integration is disabled, schema changes are not versioned, and dependency audit reports unresolved advisories. A future insulin-dose feature requires a separate clinical and regulatory program. No external AI call or real-patient-data test was made for this audit.

**Important audit side effect:** The first backend-test invocation used the default ignored backend/gluverse.db. Its setUp calls /api/demo/reset, which deletes rows and reseeds demo data. I stopped that run on discovering this and reran all 105 tests using /tmp/gluverse-audit.8xBaIz/test.db. The prior contents of backend/gluverse.db cannot be verified or restored from this audit. Do not assume that local database still contains its prior contents. SQLite WAL/SHM files remain untracked; I left them untouched to avoid further data loss. This is an observed test-harness hazard, not a hypothetical one.

## Project map and README check

| Layer | Actual implementation |
|---|---|
| Frontend | React 18, React Router 6, Create React App/react-scripts 5; frontend/src/App.js routes and component-local API calls; frontend/src/api.js attaches cookies and CSRF header. |
| Backend | Flask 3, SQLAlchemy 2 connection wrapper, bcrypt password hashes, server-side sessions in SQLite or PostgreSQL; most logic and routes are in backend/app.py (2,000+ lines). |
| Deployment | Multi-stage Node 20/Python 3.12 Dockerfile, Gunicorn, PostgreSQL 16 in Compose; no TLS reverse proxy in Compose. |
| Tests | One Python unittest module with 105 cases; React component and API test files; CI has backend, frontend, and Docker jobs. |
| Database | 13 tables: users, glucose_readings, meals, insulin_logs, alert_rules, achievements, user_achievements, community_posts, community_reports, cgm_connections, notification_settings, emergency_contacts, shop_requests, plus sessions (14 total). Created by init_db; ensure_schema patches only three user/session columns. |

**Pages:** /dashboard, /log-meal, /meal-history, /insulin, /ai-coach, /emergency, /settings/notifications, /analytics, /achievements, /community, /shop, and /settings/cgm; unauthenticated users see the sign-in/create-account screen (frontend/src/App.js:70–145).

**Frontend component map:** App handles routing, authentication state, and protected navigation. Sidebar provides navigation. Dashboard shows recent readings and summaries; LogMeal and MealHistory handle meals; InsulinLog handles dose events; Analytics shows glucose aggregates; NotificationSettings handles alert/profile preferences; EmergencyGuidance handles static guidance and contacts; AICoach sends coach prompts; CommunityForum handles posts and moderation actions; Achievements shows earned badges; CGMSettings shows disabled connection status; Shop shows a catalog and saved requests. Components use frontend/src/api.js for HTTP and largely own their own form/loading state. Component tests exist for these views except Achievements; App and API tests also exist. This is a source inventory, not a claim that each component's tests ran.

**API route map:** authentication: POST /api/auth/register, /login, /logout; GET /api/auth/me. Profile/settings: GET/PUT /api/profile/{user_id}, /api/settings/{user_id}, /api/alert-rules/{user_id}. Glucose: GET /api/glucose/latest/{user_id}, GET/POST /api/glucose/{user_id}, DELETE /api/glucose/{reading_id}, GET /api/analytics/glucose/{user_id}. Meals: GET/POST /api/meals/{user_id}, PUT/DELETE /api/meals/{meal_id}, GET /api/meals/{user_id}/summary. Insulin: GET/POST /api/insulin/{user_id}, GET /api/insulin/{user_id}/summary. Alerts: GET /api/alerts/{user_id}, /api/alerts/evaluate/{user_id}. Community: GET/POST /api/community/posts, POST hide/report and DELETE post by ID. Achievements: GET per-user list/progress, POST award. CGM: GET /api/cgm/status and /verify-auth; POST /sync and /demo-sync. Notification delivery probe: POST /api/notifications/test-low-email. Emergency: GET /api/emergency/guidance, GET/PUT /api/emergency/contacts/{user_id}. Shop: GET catalog, GET/POST per-user requests, PUT/DELETE request by ID. Operations: GET /api/health and /api/ready; POST /api/demo/reset (local development only).

**README accuracy:** It correctly describes the Flask/React stack, cookie/CSRF model, PostgreSQL production requirement, and disabled CGM/email routes. Its claim that AI/vendor integration is disabled until verified conflicts with backend/app.py:145–149 and :1910–1975: startup requires NVIDIA configuration and the coach can call that external endpoint. The README's beta and non-medical-device caveats are appropriate. Its test command is unsafe against an existing local database unless DATABASE_URL is set to a disposable path. The README notes Docker verification is outstanding, and this environment could not complete it.

## B. Feature inventory

| Feature | Implementation status | Actual result | Missing or limited behavior |
|---|---|---|---|
| Register, login, logout, sessions | Implemented | PASS browser and HTTP | No account recovery or MFA; limited beta identity model. |
| User data isolation and CSRF | Implemented on inspected paths | PASS independent HTTP: other user 403, missing CSRF 403 | No full penetration test; admin ID is hardcoded. |
| Profile and alert settings | API persists partial updates; UI broken | FAIL browser Save Settings; PASS direct API partial update | Frontend/API boolean contract mismatch; no settings history. |
| Manual glucose and latest reading | Implemented | PASS browser and HTTP | Manual data misleadingly labeled “Live”; no verified sensor feed. |
| Glucose analytics | Implemented simple aggregates | PASS browser on one synthetic reading | Clinical accuracy, time zones, large-data behavior unvalidated. |
| Meal/carbohydrate log and history | Implemented | PASS browser create/display and HTTP | No verified photo analysis; photo_url is a stored URL. |
| Insulin event log/history | Implemented as tracking | PASS browser create/display and HTTP | No concentration, drug formulation, action duration, IOB, or dosing logic. |
| Alerts and preferences | Threshold evaluation implemented on GET | PASS evaluation tests; FAIL as alert-delivery feature | No continuous evaluation or reliable email/SMS/push delivery. |
| Emergency guidance and contacts | Static guidance plus persistent contacts | PASS browser save | No emergency monitoring or outreach service; clinical text not reviewed here. |
| AI coach | Endpoint, model call, fallback text | PASS mocked backend tests; NOT TESTED real model | External health-data transfer and clinical-output validation unresolved. |
| Community | Posts, report/hide moderation | PASS browser synthetic post | No robust abuse handling or scale test; placeholder profanity list. |
| Achievements | Rules and stored awards | PASS browser first-log badges | No adversarial/time-zone assessment. |
| CGM | Status and demo state only | PASS browser shows disabled status | Real sync/verification BLOCKED by product implementation. |
| Shop | Static catalog and saved request records | NOT TESTED in browser | No checkout or payment service by design. |
| PostgreSQL/Compose | Configuration and code present | BLOCKED locally | Docker daemon and Compose plugin unavailable; CI configuration issue below. |

## C. Executed tests and limits

| Check / exact command or method | Result | Evidence |
|---|---|---|
| backend/.venv/bin/python -m unittest discover -s tests -p 'test_*.py' with DATABASE_URL=/tmp/gluverse-audit.8xBaIz/test.db | PASS | Ran 105 tests in 80.856 s; OK. Two logged 500s were expected negative-path tests. |
| Same unittest command without isolated DATABASE_URL | INTERRUPTED | Stopped with Ctrl-C after observing setUp reset the default DB; no trustworthy test count from this run. |
| backend/.venv/bin/python -m py_compile backend/app.py backend/wsgi.py tests/test_backend_api.py scripts/smoke_test.py | PASS | Exit 0. |
| Import backend.app with NVIDIA variables unset | FAIL startup | RuntimeError: Missing required NVIDIA configuration: NVIDIA_API_KEY, NVIDIA_COACH_MODEL, NVIDIA_SAFETY_MODEL. |
| Local Flask at 127.0.0.1:5100 with temporary DB and placeholder NVIDIA values | PASS startup | GET /api/health returned 200. No coach call was made. |
| Independent synthetic localhost HTTP flow | PASS, 14 checks | Unauthorized me 401; register 200; profile 200; cross-user 403; missing CSRF 403; glucose/meal/insulin writes 201; settings PUT/GET 200 and persisted target; insulin history 200; logout 200; post-logout me 401. |
| Browser, isolated synthetic user | PASS in tested paths | Register; glucose, meal, insulin logging; analytics; emergency contact; community post; achievements; logout and login. Data remained after login. |
| Browser Alerts & Settings Save Settings | FAIL | UI showed “low_glucose_alert must be boolean.” No settings were saved. |
| Browser manual glucose display | FAIL wording | Source manual was shown with “Live reading.” |
| Browser 390×844 viewport | PASS limited visual check | Sign-in and insulin form rendered; authenticated insulin page had document width = viewport width (390 px). Other pages/device sizes NOT TESTED. |
| Frontend production build, npm run build | BLOCKED | React Scripts process made no output after “react-scripts build” for over five minutes on Node 20; terminated. Node 26 attempt also stalled. No successful build claim. Existing frontend/build was served for browser tests, not produced by this audit. |
| Frontend test suite, CI=true npm test -- --watch=false --runInBand | BLOCKED | Initial Node 26 attempt and Node 20 retry both made no test-result output after several minutes; both were terminated. No frontend test count or pass claim. |
| Fresh frontend dependency installation | NOT TESTED | Existing node_modules was present; npm install was not rerun. |
| npm audit --json --omit=dev | FAIL dependency gate | 112 advisories: 2 critical, 70 high, 37 moderate, 3 low. The tree includes React Scripts/build tooling because react-scripts is declared as a production dependency; exploitability of the deployed browser bundle was not established. Critical findings include proxy-addr and shell-quote. |
| Docker CLI / docker compose version / docker info | BLOCKED | Docker CLI present, Compose command unavailable, and daemon socket unavailable. Compose build/start, PostgreSQL integration, restore drill, and deployment smoke test were not run. |
| Real CGM, email/SMS/push delivery, external AI, clinical dosing | NOT TESTED | CGM/delivery disabled, paid/external AI expressly excluded, and no dosing calculator exists. |
| Python dependency vulnerability scan | NOT TESTED | No pip-audit result; requirements are ranges rather than a lockfile. |

No real patient data was intentionally entered in the isolated account. The default-database reset caveat above is material. Synthetic records live only in /tmp/gluverse-browser-audit.p5PUl6/browser.db.

The report is a focused audit rather than exhaustive proof: I did not complete a clean dependency installation, frontend test/build, PostgreSQL migration or restore drill, large-data benchmark, accessibility audit, penetration test, real CGM connection, or clinical content review. Static findings are labeled accordingly below.

## D. Reproducible bugs and reliability defects

1. **High — settings page cannot save** (frontend/src/components/NotificationSettings.js:47–54; backend/app.py:1859–1870). Reproduce: register, open Alerts, change Target low, press Save Settings. Expected: saved values and confirmation. Actual: “low_glucose_alert must be boolean”; the frontend converts flags to 0/1 while to_bool rejects numbers. Fix: send JSON booleans and add a browser/API contract test. This was executed.

2. **High — local backend tests can erase an existing database** (tests/test_backend_api.py:18–20; backend/app.py:2112–2141). Reproduce: run the README test command with an existing default SQLite DB. Expected: isolated test data. Actual: every setUp calls the reset endpoint, which deletes all application tables and reseeds them. The initial audit run invoked this path; prior local data state is unknown. Fix: force a temporary DATABASE_URL in test setup before importing app and refuse to run against non-test paths. This was executed and stopped.

3. **High — manually entered glucose is called “Live”** (backend/app.py:1018–1028, :1415–1424; frontend/src/components/Dashboard.js:129–136). Reproduce: log a manual reading and view Dashboard. Expected: “Recent manual reading,” with clear source. Actual: “Live reading” above “Source: manual.” This can overstate freshness or connection status when CGM is disabled. Fix: reserve “Live” for verified streamed data and label manual readings by entry time/source. This was executed in browser and HTTP.

4. **High — notification preferences imply delivery that does not exist** (backend/app.py:1530–1538, :1793–1804, :1997–2006; frontend/src/components/NotificationSettings.js:111–123). Reproduce: configure low alert and expect an email or push after a new low reading. Expected: reliable evaluated-and-delivered notification if the product offers it. Actual: alert evaluation is a GET response; email test endpoint returns 503; no worker or delivery path was found. Fix: keep delivery controls disabled with explicit messaging until a monitored delivery pipeline and escalation tests exist. This is inspection plus disabled-endpoint evidence; no real emergency alert was attempted.

5. **High — Docker CI job cannot satisfy its own Compose configuration** (.github/workflows/ci.yml:48–66; docker-compose.yml:7, :27–31). Reproduce on a clean CI runner with only the workflow's declared environment: docker compose config. Expected: valid configuration. Actual by configuration inspection: Compose requires POSTGRES_PASSWORD and NVIDIA variables, but the Docker job sets none of them. Fix: supply test-only values through CI environment and use disposable credentials. Local Compose execution was blocked, so this is a static finding.

6. **Medium — ordinary startup unexpectedly requires paid AI settings** (backend/app.py:145–149; run.sh:1–40; README.md:12–18). Reproduce: import backend.app or run backend without NVIDIA variables. Expected: core tracking service starts with coach integration disabled. Actual: RuntimeError before serving. Fix: make coach optional behind explicit enablement and return a disabled response when absent. Executed without credentials.

7. **Medium — profile accepts nonsensical glucose units** (backend/app.py:1374–1405 and :1847–1852). Reproduce: PUT /api/profile/{id} with units “bananas” in isolated account. Expected: reject or normalize known units; convert readings and targets if alternative units are supported. Actual: HTTP 200 and profile units “bananas,” while glucose forms/analytics remain mg/dL. UI currently exposes only mg/dL. Fix: validate allowed units at API boundary; keep mg/dL canonical until conversion is implemented. Executed.

8. **Medium — schema evolution is not controlled** (backend/app.py:485–491, :555–724). Reproduce: start against an older DB lacking a newer column outside users/sessions, or start concurrent workers during schema setup. Expected: versioned, transactional migration with rollback. Actual by inspection: CREATE TABLE IF NOT EXISTS cannot alter old tables; ensure_schema patches only password_hash, csrf_token, revoked_at; first request performs initialization behind a process-local flag. Fix: introduce numbered migrations and run them once before serving traffic; add an upgrade fixture. PostgreSQL upgrade was not executed.

9. **Medium — PostgreSQL backup can report success after pg_dump fails** (scripts/backup_db.sh:3–26; scripts/restore_db.sh:23–30). Reproduce: run backup with invalid PostgreSQL credentials in an environment with pg_dump. Expected: nonzero failure and no purported backup. Actual by shell semantics: POSIX sh set -e checks the final gzip command of the pipeline; a failing pg_dump can leave a valid empty gzip file and a printed path. Restore likewise does not use psql ON_ERROR_STOP. Fix: capture and check pg_dump status without an unchecked pipeline, validate archive, and make restore stop on SQL errors. Not executed here.

10. **Medium — unbounded record reads and community N+1 queries** (backend/app.py:1511–1527, :1575–1583, :1604–1609, :555–704). Reproduce: grow one user's meal/insulin history or public posts, then load Dashboard/Community. Expected: bounded page and indexed lookup. Actual by inspection: full per-user lists and full community list; each post calls get_user, while schema creates almost no supporting query indexes. Fix: paginate reads, join author names, add user_id/timestamp and post-status indexes after measuring query plans. Large-load behavior was not benchmarked.

## E. Diabetes calculator readiness

**Current data can record that a dose happened, but cannot safely determine active prior insulin.** The insulin row stores insulin_type, units, timestamp, notes, and an optional meal link (backend/app.py:592–601, :1323–1333). It has no formulation, concentration, delivered-versus-planned distinction, action curve, action duration, settings version, or calculation provenance.

| Requirement | Present? | Audit conclusion |
|---|---|---|
| Editable insulin-to-carb ratio, including time-of-day schedule | No | No schema/UI/endpoint. |
| Editable correction sensitivity factor | No | No schema/UI/endpoint. |
| Editable glucose targets | Partial | target_low/high exist, but no time schedule or history; settings UI save currently fails. |
| Configurable insulin action duration | No | No model. |
| IOB tracking | No | Explicit UI says it does not calculate IOB. |
| Meal bolus calculation architecture | No | Meal and insulin rows can link, but no calculator inputs/algorithm/provenance. |
| Correction bolus calculation architecture | No | No algorithm. |
| Previous dose history | Yes, limited | Timestamp/units/type list exists; no verified delivery or formulation. |
| U-100/U-200 support | No | Units alone do not encode concentration or device; do not infer volume. |
| Long-acting versus rapid-acting | Partial | UI offers Bolus/Basal/Correction events, not specific insulin or action class. |
| Stacking prevention | No | No IOB or validated decision rules. |
| Settings history/versioning | No | Updates overwrite the current row. |

**9:00 AM breakfast, 60 g carbs; 11:30 AM lunch:** the database can show the breakfast meal and a logged dose, but cannot determine how much rapid-acting insulin remains active at lunch. The same stored dose could represent different products, actual delivery, and action profiles. Nor should all remaining IOB automatically be subtracted from a new meal bolus: meal and correction components require separate, clinically approved treatment rules. No dose recommendation should be enabled based on this model.

Before any calculator release: define intended use and jurisdiction; obtain clinical and regulatory review; record prescriber-authorized parameters with effective times, versioning, insulin formulation/concentration, actual delivery and corrections; design fail-closed behavior for missing/stale/contradictory inputs; require units and time-zone invariants; independently verify calculation code against clinician-approved reference cases, boundary/error cases, and retrospective scenarios; test human factors, accessibility, alarm behavior, audit logs, postmarket monitoring, and incident response. FDA guidance indicates that software providing dose recommendations may be regulated depending on intended use; classification cannot be decided from this code audit alone ([FDA clinical decision support guidance list](https://www.fda.gov/medical-devices/digital-health-center-excellence/guidances-digital-health-content), [FDA device software policy](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/policy-device-software-functions-and-mobile-medical-applications)).

## F. Security and privacy findings

| Priority | Evidence and exposure | Action |
|---|---|---|
| High | docker-compose.yml:45–47 publishes app port directly over HTTP and supplies no TLS proxy. A public deployment could transmit health data and credentials without transport protection. HSTS alone does not create TLS. | Require HTTPS termination, secure cookies, network restrictions, and production smoke tests before exposure. |
| High | backend/app.py:1910–1975 builds an external AI prompt from latest glucose, meal, and insulin data; :332–358 sends it to NVIDIA. Frontend discloses external AI in a banner, but data flow, retention, consent, vendor terms, and incident obligations need a formal review before real data. | Gate this integration; document data fields, minimize them, obtain appropriate authorization/contract review. HHS/FTC applicability depends on the business model, not a README claim ([HHS health-app resources](https://www.hhs.gov/hipaa/for-professionals/special-topics/health-apps/index.html), [FTC health-app breach rule](https://www.ftc.gov/business-guidance/resources/health-breach-notification-rule-basics-business)). |
| Medium | backend/app.py:449–458 stores rate-limit timestamps in a process-local dict keyed by remote IP; only auth routes use it. Multiple workers do not share counters, and keys can accumulate. | Use a shared bounded limiter at edge/API; test proxy IP configuration and abuse paths. |
| Medium | npm audit --json --omit=dev reports 112 advisory records, including critical proxy-addr and shell-quote transitive packages ([GHSA-jqcg-44mw-7w3h](https://github.com/advisories/GHSA-jqcg-44mw-7w3h), [GHSA-pqg4-j6r4-53mv](https://github.com/advisories/GHSA-pqg4-j6r4-53mv)). Because React Scripts sits in dependencies, these totals include build/dev tooling and do not alone show browser exploitability. | Separate build-time and shipped runtime exposure; update vulnerable packages with a verified build/test gate. |
| Medium | backend/app.py:555–704 creates health tables without foreign keys and few indexes; backup/restore proof is incomplete. This raises integrity and recovery risk. | Add measured indexes, constraints, migration/restore drills, and retention controls. |

**Positive controls observed:** bcrypt password hashes, parameterized SQL in the inspected paths, server-side session revocation, HttpOnly session cookie, per-user checks, CSRF on authenticated unsafe requests, no-store on API responses, CSP and basic response headers. Independent HTTP checks confirmed one cross-user denial and one CSRF denial. No exploitable SQL injection or XSS was demonstrated; this was not a comprehensive penetration test. Secret files were excluded from Git, but I did not inspect their values. Logging records request path/user identifiers; production PHI/log-retention review remains.

## G. Roadmap, effort, and dependencies

Estimates are rough single-engineer working time, excluding clinical, legal, vendor, and infrastructure review.

| Priority | Work | Estimate | Depends on |
|---|---|---:|---|
| P0 | Isolate tests before app import; assess/restore any affected local DB from independent backup; fix settings boolean contract; make CI Docker job use disposable required variables; require TLS before public deployment. | 3–7 engineering days plus data recovery if needed | Backup availability; CI secrets strategy; hosting design |
| P1 | Remove unconditional AI startup dependency; disable misleading alert delivery controls; correct manual “Live” label; validate profile units; add reliable migration and restore workflow; triage npm advisories. | 1–3 weeks | Product wording, data-model plan, dependency compatibility |
| P2 | Paginate/index reads; shared rate limiting; account recovery and stronger identity controls; browser contract tests and mobile/a11y coverage; production PostgreSQL load and backup drills. | 2–4 weeks | P0/P1 stable API and deployment |
| P3 | Real CGM integration, notification delivery, richer moderation/shop features; clinician-led dosing feasibility project with new data model and regulatory plan. | Months, not a sprint estimate | Vendor access, clinical governance, regulatory determination |

## H. Top 10 next actions

1. Check whether the pre-audit local backend/gluverse.db needs recovery from an existing backup; do not delete its WAL/SHM files blindly.
2. Make the backend test suite create and require a disposable DB before importing the app.
3. Fix the settings UI to send booleans and add a browser-to-API regression test.
4. Remove “Live” for manual glucose and review all alert/freshness wording with a clinician.
5. Keep delivery toggles disabled until alerts can be evaluated, sent, retried, and audited.
6. Repair the Docker CI environment and demonstrate a clean build, PostgreSQL startup, smoke run, and teardown.
7. Place production traffic behind HTTPS and verify cookie, CORS, and header behavior.
8. Make coach configuration optional until vendor/privacy controls are approved; test fallback without network calls.
9. Add versioned migrations, verified backup/restore, and key indexes/foreign keys where safe.
10. Triage npm advisories, then rerun frontend build/tests on a clean supported Node installation and expand end-to-end coverage.

## I. Final assessment

| Dimension | Score / 10 | Basis |
|---|---:|---|
| Architecture | 4 | Clear small-stack boundaries, but backend monolith and request-time schema setup. |
| Code quality | 5 | Useful validation and ownership helpers; weak UI/API contracts and migration discipline. |
| Functionality | 5 | Core manual records work; settings save fails and key integrations are absent. |
| Security | 4 | Several good controls, but transport, abuse protection, dependencies, and health-data governance need work. |
| Testing | 4 | 105 passing backend cases; destructive default test setup, frontend checks blocked locally, no clinical validation. |
| User experience | 5 | Core flows usable; misleading “Live” label and broken settings undermine trust. |
| Production readiness | 2 | Docker/CI, TLS, migration, backup, alert, dependency, and privacy gates remain. |

**Verdict:** suitable for a controlled engineering beta only after the settings and test-isolation defects are fixed and the database impact is assessed. It is not ready for public health-data use or clinical insulin-dose recommendations.
