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
| 1 — evidence contract | expected RED: initial import failure; review regressions then exposed 8 runtime type/blank-metadata bypass failures | focused suite with repository import path: 6 tests passed, 0 failed | approved | approved | completed |
| 2 — decay arithmetic | expected RED: missing-module exit 1; exponent mismatch 1 failure; quality regressions 7 failures and 6 errors exposed caller-context dependence and invalid operands | bundled Python 3.12; focused 10 tests and full 27-test validation passed, 0 failed; checksums and `git diff --check` passed | approved | context/operand findings fixed; re-review pending | review pending |
| 3 — domain records | pending | pending | pending | pending | queued |
| 4 — decision engine | pending | pending | pending | pending | queued |
| 5 — canonicalization and invariants | pending | pending | pending | pending | queued |

## Evidence boundary

No historical counterfactual or live enforcement behavior is validated by this
progress ledger. It records software-development evidence only.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
