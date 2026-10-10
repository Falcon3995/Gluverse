# GluVerse Progress

## Active section

Health safety, privacy, accessibility, and legal boundaries.

## Completed story

Harden health-data write boundaries and emergency guidance UX.

Acceptance criteria met: malformed writes return controlled validation errors; health feedback uses accessible live regions; backend and frontend checks pass.

## Active story

Release audit: validation evidence consistency.

Emergency contact completeness validation is complete: server and client reject partial contacts, while blank untouched rows remain allowed.

## Completed in current increment

- Added malformed-payload validation for emergency contacts and settings.
- Added accessible live regions and native telephone input to emergency guidance.
- Added accessible live regions to dashboard, meal, and insulin-entry feedback.
- Extended live-region feedback across settings, analytics, CGM, achievements, shop, and community views.
- Added client-side glucose range validation before submission.
- Added client-side nonnegative numeric validation for meal nutrition fields.
- Added client-side nonnegative finite validation for insulin log units.
- Added native min/max bounds to profile and alert-threshold inputs.
- Added shared relational validation so alert thresholds remain ordered.
- Added matching client-side threshold-order validation before settings submission.
- Added target-low/target-high ordering validation on client and server.
- Aligned meal macro inputs with backend support for fractional grams.
- Added screen-reader status announcements for health-data loading states.
- Extended loading status announcements to analytics, CGM, shop, and meal views.
- Added `aria-busy` save-state announcements to glucose, meal, and insulin forms.
- Added live status semantics to the Analytics no-data state.
- Added live status semantics to Community Forum and Shop no-data states.
- Added live status semantics to the Dashboard alert summary.
- Added live status semantics to the CGM connection-state banner.
- Added mobile decimal keypad hints to glucose, meal, and insulin numeric inputs.
- Extended mobile decimal keypad hints to notification target and alert-threshold inputs.
- Verified backend and frontend regression suites.
- Rejected health-record timestamps more than five minutes in the future so they cannot remain falsely latest.
- Converted UTC timestamp overflows into controlled validation errors instead of server errors.
- Restricted the destructive demo-reset endpoint to loopback callers while preserving its production block.
- Rejected blank community posts at the API boundary to match the existing client workflow.
- Preserved the existing/default shop request status when a blank status is submitted.
- Returned an `Unknown` freshness label for invalid stored glucose timestamps instead of raising during health reads.
- Returned an `Unknown` freshness label for out-of-range stored glucose timestamps instead of raising during health reads.
- Treated out-of-range stored glucose timestamps as stale in the shared health-read check instead of raising before freshness labeling.
- Preserved existing shop request status when a repeat save omits the status field.
- Preserved existing shop request quantity and notes when a repeat save omits those fields.
- Preserved existing meal fields when a partial edit omits them.
- Preserved existing alert rules and notification flags when a partial settings update omits those sections.
- Preserved existing alert-rule values when a partial alert-rules update omits them.
- Preserved existing profile settings JSON when a partial profile update omits it.
- Ensured shared writes roll back and close their database connection on failure.
- Ensured shared reads close their database connection when a read fails.
- Ensured readiness probe connections close when the database query fails.
- Made lazy alert-rule and notification-settings initialization safe under concurrent requests.
- Made demo reset atomic so reseed failures preserve existing data and close the database connection.
- Rejected blank coach messages before model processing and isolated rate-limit state between backend tests.
- Disabled the Coach Send button until the message contains non-whitespace text.
- Corrected the Coach privacy disclosure to state that messages use an external AI service and should omit identifying details.
- Prevented clients from bypassing authentication throttling with spoofed `X-Forwarded-For` headers.
- Added production HSTS so browsers retain HTTPS for future GluVerse visits.
- Marked API responses `no-store` so private health data is not retained by browser or intermediary caches.
- Limited request bodies to 1 MiB so oversized JSON is rejected before parsing and validation.
- Rejected timezone-naive health-record timestamps to prevent ambiguous storage and glucose freshness failures.
- Normalized accepted health-record timestamps to UTC so database text ordering remains chronological across offsets.
- Rejected falsey non-text timestamps across glucose, meal, and insulin writes and meal updates.
- Rejected falsey non-object settings sections at the settings API boundary.
- Made profile, alert-rule, and notification settings updates commit atomically.
- Returned controlled validation errors for non-text registration and login credentials.
- Returned a controlled 409 conflict when the registration insert hits the username uniqueness constraint.
- Made account bootstrap inserts transactional so companion-row failures cannot leave an orphaned user.

## Validation

- Backend: 104 tests passed, including invalid and out-of-range timestamp freshness handling, blank shop status preservation, blank community content validation, local-only demo reset, overflow-safe, future-bounded, and UTC-normalized health timestamps, bounded request bodies, non-cacheable health API responses, production HSTS, and spoof-resistant authentication rate limiting.
- Latest backend validation: 105 tests passed, including the shared out-of-range timestamp stale-check regression.
- Frontend: 15 suites / 24 tests passed; production build passed.
- Browser smoke validation remains blocked because the new Chrome DevTools MCP configuration requires a Codex reload, this environment restricts local socket access, and the existing backend virtualenv hangs while importing Flask.
- Fixed the local launcher port-selection loop so free backend and frontend ports are accepted instead of incrementing forever; `sh -n run.sh` passes.
- Updated `run.sh` to select an available backend port when macOS services occupy port 5000 and pass that URL to the React dev server.

## Next action

Continue improving user-facing health-data flows; Docker deployment remains deferred.
