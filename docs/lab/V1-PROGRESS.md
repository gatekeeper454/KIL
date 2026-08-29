# V1 deterministic-kernel live progress

**Branch:** `feature/v1-deterministic-kernel`
**Started:** 2026-08-29
**Runtime:** bundled Python 3.12
**Baseline:** 11 tests passed, 0 failed

This ledger is updated at each red/green and review checkpoint. A red result is
an expected test-first state, not a validated KIL outcome.

| Task | RED observed | GREEN observed | Spec review | Quality review | Status |
|---|---|---|---|---|---|
| 0 — runtime pin | n/a: build configuration | Python 3.12.13; 11 tests passed | approved | approved | completed |
| 1 — evidence contract | expected RED: focused test exited 1; import failed before implementation (`kil.evidence` unavailable; direct invocation also lacked the Makefile's `PYTHONPATH=src`) | focused suite with repository import path: 4 tests passed, 0 failed | pending | pending | implemented; reviews pending |
| 2 — decay arithmetic | pending | pending | pending | pending | queued |
| 3 — domain records | pending | pending | pending | pending | queued |
| 4 — decision engine | pending | pending | pending | pending | queued |
| 5 — canonicalization and invariants | pending | pending | pending | pending | queued |

## Evidence boundary

No historical counterfactual or live enforcement behavior is validated by this
progress ledger. It records software-development evidence only.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
