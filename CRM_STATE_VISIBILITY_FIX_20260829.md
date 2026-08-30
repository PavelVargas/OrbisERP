# CRM state visibility fix - 2026-08-29

Fixed CRM state rendering where empty, error, loading and client dossier states could appear simultaneously.

Cause: component CSS used `display: ... !important`, which overrode the browser's default `[hidden] { display: none; }` behavior.

Fix: explicit high-priority `[hidden]` selectors for CRM state panels. The CRM now guarantees one visible state at a time.

Asset version bumped to `20260829-crm8` to avoid stale cached CSS.
