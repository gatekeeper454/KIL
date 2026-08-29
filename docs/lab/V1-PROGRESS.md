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
| 2 — decay arithmetic | expected RED: missing-module exit 1; exponent mismatch 1 failure; context/operand regressions 7 failures and 6 errors; precision-boundary clamp 1 failure | bundled Python 3.12; focused 11 tests and full 28-test validation passed, 0 failed; checksums and `git diff --check` passed | approved | approved | completed |
| 3 — domain records | expected RED: missing `kil.domain` module, exit 1; quality regressions exposed 2 increasing-authority and 5 outcome/reason consistency failures | bundled Python 3.12; corrected focused suite 14 tests and full validation 42 tests passed, 0 failed; source checksums and `git diff --check` passed | approved | approved | completed |
| 4 — decision engine | expected RED: missing `kil.engine` module, exit 1; runtime contract regressions exposed 2 failures and 3 errors; quality regressions exposed 7 timestamp/enum failures and 2 escaped Decimal errors | bundled Python 3.12; corrected domain+engine suite 32 tests and full validation 60 tests passed, 0 failed; source checksums and `git diff --check` passed | approved | approved | completed |
| 5 — canonicalization and invariants | expected RED: missing `kil.canonical` module, exit 1; package-version expectation failed against `0.0.0`, 1 failure; quality regression RED first exposed missing limit constants, then 9 behavioral failures and 1 recursion error | bundled Python 3.12; corrected focused V1 suite 66 tests and full validation 76 tests passed, 0 failed; source checksums and `git diff --check` passed | approved | fixes implemented; re-review pending | implemented; quality re-review pending |

## Evidence boundary

No historical counterfactual or live enforcement behavior is validated by this
progress ledger. It records software-development evidence only.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
