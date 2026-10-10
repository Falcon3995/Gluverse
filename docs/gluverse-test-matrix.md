# GluVerse Test Matrix

| Check | Latest result |
|---|---|
| Backend unittest suite | 104 passed, including invalid and out-of-range timestamp freshness handling, blank shop status preservation, blank community content validation, local-only demo reset, overflow-safe, future-bounded, and UTC-normalized health timestamps, bounded request bodies, non-cacheable health API responses, production HSTS, spoof-resistant authentication rate limiting, blank coach-message validation, deterministic rate-limit test isolation, atomic demo reset rollback, race-safe default settings initialization, readiness failure connection cleanup, read failure connection cleanup, write failure rollback and connection cleanup, atomic account bootstrap, registration uniqueness-race conflict handling, authentication credential-type validation, atomic settings replacement, partial settings section preservation, partial alert-rule value preservation, partial profile settings preservation, falsey settings-section validation, falsey timestamp validation, shop request status and field preservation, partial meal edit field preservation, insulin-to-meal referential integrity, atomic emergency-contact replacement, strict numeric health data, finite numeric health data, shared timestamp, community content, report and moderation referential integrity, glucose ID/source, duplicate glucose IDs, meal ID, duplicate meal IDs, insulin ID, duplicate insulin IDs, achievement referential integrity, coach message, settings flags, alert-rule validation, contact-ID validation, and required-field validation |
| Frontend Jest suite | 15 suites / 24 tests passed, including accurate external-AI privacy disclosure and disabled blank coach submission |
| Frontend production build | Passed |
| Compose config validation | Passed |
| Python compilation | Passed |
| Feature backlog audit | Completed; see `docs/gluverse-feature-backlog.md` |
