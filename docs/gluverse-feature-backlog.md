# GluVerse Feature Test Backlog

Audit date: 2026-09-09

## Tested feature areas

| Feature | Automated coverage | Result |
|---|---|---|
| Authentication, sessions, CSRF, ownership | Backend API tests | Pass |
| Glucose dashboard and writes | Backend + Dashboard helpers | Pass |
| Meal logging and history | Backend + LogMeal tests | Pass |
| Insulin logging | Backend + InsulinLog tests | Pass |
| Emergency guidance and contacts | Backend + EmergencyGuidance tests | Pass |
| Notification thresholds | Backend + NotificationSettings tests | Pass |
| Analytics | Backend API coverage | Pass |
| AI coach safety behavior | Backend API coverage | Pass |
| Community and shop workflows | Backend API coverage | Pass |
| Achievements | Backend API coverage | Pass |
| API client error handling | Frontend API tests | Pass |

## Backlog

1. **P1 — Make CGM settings reachable — completed.** Added the `/settings/cgm` route, Sidebar link, navigation assertion, and unavailable-state render test. The unavailable integration response remains unchanged.
2. **P1 — Add App shell tests — completed.** Login/register mode switching, protected-route redirect, expired-session sign-in handling, CGM unavailable-state rendering, and recoverable error-boundary rendering are covered.
3. **P2 — Add component tests for Analytics, Community, Shop, Achievements, Coach, and Meal History — completed.** Empty and primary state coverage is now present for these user-facing components.
4. **P2 — Run browser-level smoke tests — blocked.** Chrome DevTools MCP is configured in `.mcp.json` and the package fetch succeeds, but this Codex session has not reloaded the server, local socket access is restricted, and the existing backend virtualenv hangs while importing Flask. Validate sign-in, one health-data write, emergency contacts, and logout once the browser test runtime is available.
5. **P3 — Refresh release audit after the above fixes — completed.** Release evidence was refreshed on 2026-09-09; Docker/deployment remains deferred by user instruction.

## Current validation

- Backend: 105 tests passed, including invalid and out-of-range timestamp freshness handling, blank shop status preservation, blank community content validation, local-only demo reset, overflow-safe, future-bounded, and UTC-normalized health timestamps, bounded request bodies, non-cacheable health API responses, production HSTS, spoof-resistant authentication rate limiting, blank coach-message validation, deterministic rate-limit test isolation, atomic demo reset rollback, race-safe default settings initialization, readiness failure connection cleanup, read failure connection cleanup, write failure rollback and connection cleanup, atomic account bootstrap, registration uniqueness-race conflict handling, authentication credential-type validation, atomic settings replacement, partial settings section preservation, partial alert-rule value preservation, partial profile settings preservation, falsey settings-section validation, falsey timestamp validation, shop request status and field preservation, partial meal edit field preservation, insulin-to-meal referential integrity, atomic emergency-contact replacement, strict numeric health data, finite numeric health data, shared timestamp, community content, report and moderation referential integrity, glucose ID/source, duplicate glucose IDs, meal ID, duplicate meal IDs, insulin ID, duplicate insulin IDs, achievement referential integrity, coach message, settings flags, alert-rule validation, contact-ID validation, and required-field validation.
- Frontend: 15 suites / 24 tests passed, including accurate external-AI privacy disclosure and disabled blank coach submission.
- Frontend production build: passed.
- Browser smoke: blocked by Codex MCP reload/local socket restrictions; the configured server is recorded in `.mcp.json`.
