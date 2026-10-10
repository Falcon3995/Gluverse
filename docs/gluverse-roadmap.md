# GluVerse Roadmap

1. Harden health safety, privacy, accessibility, and legal boundaries.
2. Validate full frontend/backend integration.
3. Complete deployment and release audit.

Current focus: browser-level smoke validation for the tested feature surface.

Latest validation: backend unittest suite passed with 105 tests, including invalid and out-of-range timestamp freshness handling, blank shop status preservation, blank community content validation, local-only demo reset, overflow-safe, future-bounded, and UTC-normalized health timestamps, bounded request bodies, non-cacheable health API responses, production HSTS, and spoof-resistant authentication rate limiting, and the frontend passed 15 suites / 24 tests plus its production build, including accurate external-AI privacy disclosure and disabled blank coach submission; the launcher port-selection loop is fixed and syntax-validated; browser smoke remains blocked pending Codex reload of `.mcp.json`, local socket access, and a healthy Flask import in the existing virtualenv.
