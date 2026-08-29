# V2 historical-replay live progress

**Branch:** `feature/v2-historical-replay`  
**Started:** 2026-08-29  
**Base:** `main` at `261474c`  
**Runtime:** bundled Python 3.12  
**Baseline:** 79 tests passed from the primary checkout with managed worktrees present

This ledger is updated at every RED, GREEN, and review checkpoint. A passing
replay test validates deterministic software behavior only. Historical
counterfactual decisions remain **modeled**, never validated.

| Task | RED observed | GREEN observed | Review | Status |
|---|---|---|---|---|
| 0 — V2 gate and runtime baseline | n/a | primary checkout: 79 tests passed; five source hashes passed | complete | completed |
| 1 — scenario schema and loader | expected RED: missing `kil.scenario`; UTF-8 boundary regression then failed once | focused 10 tests; full 89 tests; five source hashes and schema JSON parse passed | plan and self-review approved | completed |
| 2 — common-stream paired replay | expected RED: `ModuleNotFoundError: kil.replay`, exit 1 | focused 5 tests; full 94 tests; five source hashes passed | plan and self-review approved | completed |
| 3 — deterministic run bundles | expected RED: `ModuleNotFoundError: kil.run_bundle`, exit 1 | focused 5 tests; full 99 tests; five source hashes passed | plan and self-review approved | completed |
| 4 — eight-phase Hugging Face scenario | expected RED: scenario file absent; exit 1 | focused 4 tests; full 103 tests; JSON parse and five source hashes passed | plan and self-review approved | completed |
| 5 — replay CLI and modeled report | expected RED: missing `tools/replay.py`; subprocess exit 2 | focused 1 CLI test and 25 V2 tests; full 104 tests; six bundle hashes and five source hashes passed | plan and self-review approved | completed |

## Evidence boundary

Observed incident facts must carry primary-source references. Synthetic KTP
state, local signals, control assumptions, and every replay decision must carry
modeled provenance and rationale. The word **validated** is reserved for behavior
reproduced under an approved validation protocol; V2 historical replay does not
meet that threshold.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

## First modeled report

- Run ID: `1ab32d9f4ea27624`
- Scenario: `hf-july-2026-eight-phase`
- Implementation: `e803cd144d785c13d07f9d96670a5c52e796314f`
- Profile: `weighted-diagonal-v0-modeled`
- Events: 8
- Modeled credential-policy permits: 8
- Signed-state-only denials: 8; unreachable descendants: 7
- Signed-plus-local-reduction denials: 8; unreachable descendants: 7
- Integrity: all six public-artifact SHA-256 entries verified
- Persistent local path: `artifacts/generated/v2-historical-replay/1ab32d9f4ea27624`

This report is local generated evidence and is intentionally excluded from Git
by `artifacts/generated/`. Its manifest, decisions, and metrics are modeled,
not validated.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

## Task 4 verification note

The first post-write focused invocation omitted `PYTHONPATH=src` and failed at
import; a subsequent generic `make validate` selected system Python 3.9 and was
correctly rejected by the repository's Python 3.11 minimum. Neither was a code
failure. The declared bundled Python 3.12 command then passed all four focused
tests and the complete 103-test suite. The replay smoke check shows eight
modeled baseline permits, a phase-1 KIL denial in both KIL modes, and all seven
dependent KIL paths marked unreachable while retaining their computed modeled
decisions.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
