# V4 controller CI boundary design

## Status

Approved on 2026-09-11 by explicit authorization to repair the narrow V4
CI/proof blocker before merging the V3B-1 publication pull request.

## Problem

The default `make validate` gate executes an unfinished V4 controller lifecycle
suite. Sixteen methods assume proof stages that are intentionally deferred past
publication. They produce 34 errors or subtest failures, all inside
`V3B2ControllerTest`, while the accepted V3B-1 publication tests and completed
V3B-2 proof/unit modules pass. Implementing the missing node-image, applied
object, runtime inventory, and terminal proof graph would merge the large V4
implementation into the publication boundary.

## Considered approaches

1. **Explicit narrow quarantine with an opt-in target — selected.** Mark only
   the 16 unfinished lifecycle methods as V4 Future tests, skip them in the
   default gate, and expose a dedicated target that runs them. A guard test
   locks the exact deferred set so it cannot silently expand.
2. Merge the accumulated V4 proof graph. This would make the lifecycle tests
   meaningful but would violate the approved publication-only scope and add
   thousands of lines of future implementation.
3. Merge despite failed CI or disable the whole controller module. Both options
   would hide more signal than necessary and are rejected.

## Design

`tests/test_v3b2_controller.py` owns a small `v4_future` decorator. It skips a
test unless `KIL_RUN_V4_FUTURE_TESTS=1`. The decorator is applied only to the 16
methods identified in both GitHub CI runs. The other controller tests remain in
the default discovery suite.

`tests/test_v4_future_controller_gate.py` asserts the exact deferred method set,
the opt-in environment contract, and the dedicated Make target. Any accidental
addition or removal fails the default gate and forces an explicit boundary
decision.

`Makefile` exposes `v4-future-controller-test`. It sets the opt-in variable and
runs the full `V3B2ControllerTest` class directly. That target is expected to
remain red until V4 resumes; its output is the durable backlog signal rather
than a publication blocker.

## Claim and safety boundary

This change does not make any V4 proof pass, alter V4 production behavior,
touch runtime state, or relax V3B-1 publication assertions. It changes only
which explicitly unfinished integration methods participate in the default
publication gate. The dedicated target preserves reproducibility of the
failure, while completed unit and proof tests continue to gate every commit.

## Acceptance criteria

- A regression test fails before the deferral exists.
- Exactly the 16 CI-failing lifecycle methods are deferred by default.
- Other `V3B2ControllerTest` methods still run in default discovery.
- `make v4-future-controller-test` explicitly includes the deferred methods.
- The full `make validate` gate passes locally and on PR #23.
- The existing 70-test publication gate and 58 generated readers remain valid.
- No Colima, Docker, Kind, Kubernetes, or evidence runtime is invoked.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
