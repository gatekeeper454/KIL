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
| 0 — V2 gate and runtime baseline | n/a | primary checkout: 79 tests passed; five source hashes passed | pending | in progress |
| 1 — scenario schema and loader | pending | pending | pending | queued |
| 2 — common-stream paired replay | pending | pending | pending | queued |
| 3 — deterministic run bundles | pending | pending | pending | queued |
| 4 — eight-phase Hugging Face scenario | pending | pending | pending | queued |
| 5 — replay CLI and modeled report | pending | pending | pending | queued |

## Evidence boundary

Observed incident facts must carry primary-source references. Synthetic KTP
state, local signals, control assumptions, and every replay decision must carry
modeled provenance and rationale. The word **validated** is reserved for behavior
reproduced under an approved validation protocol; V2 historical replay does not
meet that threshold.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
