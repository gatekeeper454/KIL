# V3B-1 Runtime Evidence Source-Format Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the V3B-1 real Envoy runtime emit the existing canonical evidence shape and make live ledger reads bounded, so one newly authorized exactly-once Task 11 run can produce an accepted proof.

**Architecture:** Correct evidence at its producers instead of rewriting collected bytes. The authorization service ignores only two exact Envoy-generated transport headers, Envoy emits canonical JSON text with string/sentinel values, and the controller performs a bounded read-only ledger availability loop before exact copy and digest comparison. Publish and synchronize the code correction before starting a separate clean live-proof worktree.

**Tech Stack:** Python 3.12, `unittest`, Envoy v3 JSON bootstrap, Docker CLI, Colima, canonical JSONL, GitHub Actions.

---

## File map

- `src/kil/ext_authz_http.py`: classify exact transport-generated headers without widening trusted client input.
- `tests/test_ext_authz_http.py`: prove fixed Envoy headers are ignored and arbitrary headers remain recorded.
- `src/kil/v3b_envoy.py`: emit the existing closed Envoy evidence record as canonical JSON text.
- `tests/test_v3b_envoy.py`: lock the exact inline format, string values, sentinels, and secret exclusions.
- `tools/v3b1_local_envoy.py`: bound live ledger availability and verify copied bytes against the observed source.
- `tests/test_v3b1_local_envoy.py`: cover missing-then-present, timeout, integrity, and no-request behavior.
- `README.md`, `adapters/envoy/README.md`, `docs/lab/V3-PROGRESS.md`: record the failed-closed discovery and correction boundary.
- `docs/superpowers/specs/2026-09-05-v3b1-runtime-evidence-source-format-design.md`: change status from approved design to implemented only after tests pass.
- `docs/superpowers/plans/2026-09-05-v3b1-runtime-evidence-source-format.md`: track this plan.
- `artifacts/generated/v3b1-local-envoy/$kil_verified_run_id/`: force-add only the exact accepted bundle after offline verification.
- `docs/paper/kinetic-infrastructure.md`: add only calibrated accepted local-Envoy claims after the live proof passes.

### Task 1: Classify exact Envoy transport headers

**Files:**

- Modify: `tests/test_ext_authz_http.py`
- Modify: `src/kil/ext_authz_http.py`

- [x] **Step 1: Write the failing transport-metadata test**

Add this test to `ExtAuthzHttpTest`:

```python
def test_envoy_transport_headers_are_ignored_but_arbitrary_headers_are_not(self):
    app = self.app(LiveTrack.SIGNED_STATE_ONLY)

    response = app.handle(
        self.request(
            self.signed_token,
            extra_headers=(
                ("x-envoy-expected-rq-timeout-ms", "250"),
                ("x-envoy-internal", "true"),
                ("x-client-controlled", "present"),
            ),
        )
    )

    self.assertEqual(response.status, 200)
    self.assertEqual(
        app.records[0].untrusted_header_names,
        ("x-client-controlled",),
    )
```

- [x] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_ext_authz_http.ExtAuthzHttpTest.test_envoy_transport_headers_are_ignored_but_arbitrary_headers_are_not -v
```

Expected: FAIL because both `x-envoy-*` names are currently included in
`untrusted_header_names`.

- [x] **Step 3: Implement the exact transport classification**

Change the constant to this literal closed set:

```python
_IGNORED_TRANSPORT_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "x-envoy-expected-rq-timeout-ms",
        "x-envoy-internal",
    }
)
```

Do not add an `x-envoy-` prefix rule or change `_TRUSTED_HEADERS`.

- [x] **Step 4: Verify GREEN and the authorization module**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_ext_authz_http -v
```

Expected: all authorization HTTP tests PASS.

- [x] **Step 5: Commit**

```bash
git add src/kil/ext_authz_http.py tests/test_ext_authz_http.py
git commit -m "fix: classify Envoy transport headers"
```

### Task 2: Emit canonical Envoy JSON text at the producer

**Files:**

- Modify: `tests/test_v3b_envoy.py`
- Modify: `src/kil/v3b_envoy.py`

- [x] **Step 1: Replace the typed-JSON expectation with a failing text-format test**

Update the stdout access-log assertion to require:

```python
expected_record = {
    "run_id": "%REQ(X-KIL-RUN-ID)%",
    "request_id": "%REQ(X-REQUEST-ID)%",
    "track": TRACK.value,
    "response_code": "%RESPONSE_CODE%",
    "upstream_host": "%UPSTREAM_HOST%",
    "upstream_service_time": "%RESP(X-ENVOY-UPSTREAM-SERVICE-TIME)%",
    "decision_digest": (
        "%DYNAMIC_METADATA(envoy.filters.http.ext_authz:"
        "x-kil-decision-digest)%"
    ),
}
expected_line = canonical_json(expected_record) + "\n"
self.assertEqual(
    access_log["typed_config"]["log_format"],
    {"text_format_source": {"inline_string": expected_line}},
)
self.assertEqual(json.loads(expected_line), expected_record)
self.assertNotIn("json_format", access_log["typed_config"]["log_format"])
```

Import `json` in the test module. Update the digest-evidence test to read and
parse `text_format_source.inline_string` instead of `json_format`.

- [x] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b_envoy -v
```

Expected: FAIL because the renderer still produces `json_format`.

- [x] **Step 3: Implement the canonical inline source**

In `render_envoy_config`, build the fixed record and replace `json_format`:

```python
access_record = {
    "run_id": "%REQ(X-KIL-RUN-ID)%",
    "request_id": "%REQ(X-REQUEST-ID)%",
    "track": track.value,
    "response_code": "%RESPONSE_CODE%",
    "upstream_host": "%UPSTREAM_HOST%",
    "upstream_service_time": "%RESP(X-ENVOY-UPSTREAM-SERVICE-TIME)%",
    "decision_digest": (
        "%DYNAMIC_METADATA(envoy.filters.http.ext_authz:"
        "x-kil-decision-digest)%"
    ),
}
```

Set the logger field exactly:

```python
"log_format": {
    "text_format_source": {
        "inline_string": canonical_json(access_record) + "\n"
    }
},
```

- [x] **Step 4: Verify GREEN and closed configuration**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b_envoy -v
```

Expected: all tests PASS, the rendered config contains one inline JSON
line, and secret-bearing formatter fields remain absent.

- [x] **Step 5: Commit**

```bash
git add src/kil/v3b_envoy.py tests/test_v3b_envoy.py tests/test_v3b1_local_envoy.py
git commit -m "fix: emit canonical Envoy evidence records"
```

### Task 3: Bound live ledger availability without retrying requests

**Files:**

- Modify: `tests/test_v3b1_local_envoy.py`
- Modify: `tools/v3b1_local_envoy.py`

- [x] **Step 1: Write failing availability and timeout tests**

Add a focused `LiveLedgerCopyTest` using an injected runner, monotonic clock,
and sleeper. The success test must return a missing closed `_LEDGER_PROBE`
record once, then a present record, perform one exact `docker cp`, and assert
the destination bytes and digest match. The runner must reject any argv
containing `driver`, `run`, an HTTP client, or a request instruction.

Use these closed observations:

```python
missing = canonical_json({
    "exists": False,
    "regular_file": False,
    "byte_count": None,
    "sha256": None,
}) + "\n"
payload = (canonical_json({"track": "signed_state_only"}) + "\n").encode()
present = canonical_json({
    "exists": True,
    "regular_file": True,
    "byte_count": len(payload),
    "sha256": sha256(payload).hexdigest(),
}) + "\n"
```

The timeout test must keep returning `missing`, advance the injected monotonic
clock beyond five seconds through the sleeper, and require
`ControllerError("live ledger availability deadline exceeded")` with zero copy
commands. Add table-driven tests that return nonregular, oversized, copied-size
mismatch, and copied-digest mismatch observations and require immediate failure
without another probe.

- [x] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_v3b1_local_envoy.LiveLedgerCopyTest -v
```

Expected: FAIL because `_copy_live_ledger` and injected `sleep` do not exist.

- [x] **Step 3: Add bounded constants and injected sleep**

Add:

```python
_EVIDENCE_READ_DEADLINE_NS = 5_000_000_000
_EVIDENCE_READ_POLL_S = 0.05
```

Extend `LocalEnvoyController.__init__` with:

```python
sleep: Callable[[float], None] | None = None,
```

and bind:

```python
self.sleep = time.sleep if sleep is None else sleep
```

- [x] **Step 4: Implement `_copy_live_ledger`**

Implement a private controller method with this contract:

```python
def _copy_live_ledger(
    self,
    *,
    container_id: str,
    source_path: str,
    destination: Path,
) -> bytes:
    """Copy one exact live ledger under a shared monotonic deadline."""
```

It must validate the full container ID and literal source path, establish one
five-second deadline, call the existing `_LEDGER_PROBE`, retry only a closed
missing observation after the injected 50 ms sleep, clip every command timeout
to the remaining budget, reject oversize before copy, perform one exact
`docker cp` after a present observation, require a regular nonsymlink output,
and compare copied byte count and SHA-256 with the probe. Any copy or integrity
failure is terminal; remove or quarantine a partial destination before raising.

- [x] **Step 5: Route live collection through the helper**

In `_copy_sources`, replace both direct ledger `docker cp` blocks with:

```python
decision_bytes = self._copy_live_ledger(
    container_id=str(authz["id"]),
    source_path="/evidence/decisions.jsonl",
    destination=decision_path,
)
target_bytes = self._copy_live_ledger(
    container_id=str(target["id"]),
    source_path="/evidence/targets.jsonl",
    destination=target_path,
)
```

Parse `decision_bytes` and `target_bytes` directly. Do not add any call to
driver startup, instruction writing, `run`, HTTP, or request-state mutation.

- [x] **Step 6: Verify GREEN and request sequencing**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_v3b1_local_envoy.LiveLedgerCopyTest \
  tests.test_v3b1_local_envoy.DriverRequestSequencingTest -v
```

Expected: all tests PASS; timeout is bounded; exactly one request intent and
instruction remain enforced per track.

- [x] **Step 7: Commit**

```bash
git add tools/v3b1_local_envoy.py tests/test_v3b1_local_envoy.py
git commit -m "fix: bound V3B-1 live evidence reads"
```

### Task 4: Document and publish the correction

**Files:**

- Modify: `README.md`
- Modify: `adapters/envoy/README.md`
- Modify: `docs/lab/V3-PROGRESS.md`
- Modify: `docs/superpowers/specs/2026-09-05-v3b1-runtime-evidence-source-format-design.md`
- Modify: `docs/superpowers/plans/2026-09-05-v3b1-runtime-evidence-source-format.md`
- Modify: generated `.htm` siblings

- [x] **Step 1: Run focused tests and update status**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_ext_authz_http tests.test_v3b_envoy \
  tests.test_v3b1_local_envoy.LiveLedgerCopyTest \
  tests.test_v3b1_local_envoy.DriverRequestSequencingTest -v
```

Expected: PASS. Then mark Tasks 1–3 complete, set the design status to
`Implemented; publication pending`, and document that the failed bundle remains
nonpromotable and no second request occurred during implementation.

- [x] **Step 2: Regenerate readers and run the full gate**

```bash
../../.venv/bin/python tools/render_markdown.py
make validate PYTHON=../../.venv/bin/python
```

Expected: all tests PASS, all generated readers verify, and `git diff --check`
emits no error.

- [x] **Step 3: Run the public-boundary secret scan**

Run the repository's existing V3B-1 forbidden-token/public-boundary tests and:

```bash
git diff --cached --name-only
git grep -n -I -E 'Bearer |eyJ|/Users/|execution_nonce' -- \
  README.md adapters/envoy/README.md docs/lab/V3-PROGRESS.md \
  docs/superpowers/specs/2026-09-05-v3b1-runtime-evidence-source-format-design.md \
  docs/superpowers/plans/2026-09-05-v3b1-runtime-evidence-source-format.md
```

Expected: only explicitly documented forbidden-token names, if any; no secret
value, private host path, raw foreign-profile name, or nonce value.

- [x] **Step 4: Review the exact diff**

Because agent delegation is disabled for this session, perform two separate
fresh-context local review passes: specification compliance, then quality and
security. Resolve every critical or important issue and rerun focused and full
verification.

- [x] **Step 5: Commit and publish**

```bash
git add README.md README.htm adapters/envoy/README.md adapters/envoy/README.htm \
  docs/lab/V3-PROGRESS.md docs/lab/V3-PROGRESS.htm \
  docs/superpowers/specs/2026-09-05-v3b1-runtime-evidence-source-format-design.md \
  docs/superpowers/specs/2026-09-05-v3b1-runtime-evidence-source-format-design.htm \
  docs/superpowers/plans/2026-09-05-v3b1-runtime-evidence-source-format.md \
  docs/superpowers/plans/2026-09-05-v3b1-runtime-evidence-source-format.htm
git commit -m "docs: record V3B-1 evidence correction"
git push -u origin codex/v3b1-central-proof-v3
gh pr create --base main --head codex/v3b1-central-proof-v3 \
  --title "Correct V3B-1 runtime evidence production" \
  --body "Correct producer formats and bound evidence reads; no live request in this PR."
```

Require public CI success, merge the PR, fetch `origin/main`, and prove local,
remote-tracking, and `ls-remote` main equality before any new `up`.

### Task 5: Execute and publish the newly authorized proof

**Files:**

- Create worktree: `.worktrees/v3b1-central-proof-v3-rerun`
- Force-add: `artifacts/generated/v3b1-local-envoy/$kil_verified_run_id/`
- Modify: `README.md`
- Modify: `adapters/envoy/README.md`
- Modify: `docs/lab/V3-PROGRESS.md`
- Modify: `docs/paper/kinetic-infrastructure.md`
- Modify: `docs/superpowers/plans/2026-09-05-v3b1-runtime-evidence-source-format.md`
- Modify: generated `.htm` siblings
- Modify live only: ignored `artifacts/generated/v3b1-task6-live-status.md`

- [x] **Step 1: Create a new clean synchronized worktree**

After the correction PR merges, create
`codex/v3b1-central-proof-v3-rerun` from the exact `origin/main` commit. Verify
`.worktrees/` is ignored, the old failed-run worktree still exists, the new tree
is clean, and `make validate PYTHON=../../.venv/bin/python` passes.

- [x] **Step 2: Install/verify tools and execute the lifecycle visibly**

Update the ignored live board before every command. Run exactly:

```bash
make v3b-tools PYTHON=../../.venv/bin/python
make v3b-preflight PYTHON=../../.venv/bin/python
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src ../../.venv/bin/python tools/v3b1_local_envoy.py preflight
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src ../../.venv/bin/python tools/v3b1_local_envoy.py up
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src ../../.venv/bin/python tools/v3b1_local_envoy.py run
```

Invoke `run` once. If it returns a complete provisional bundle and the journal
contains `evidence_collect_complete`, do not invoke `collect` separately. If it
returns before collection and the journal proves three completed request states
with no collect completion, invoke `collect` once. Under every outcome invoke:

```bash
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src ../../.venv/bin/python tools/v3b1_local_envoy.py down
```

Never invoke `run` again.

- [x] **Step 3: Verify the accepted bundle**

Require the exact run ID pattern, V3 public manifest, `run_complete: true`,
accepted local-boundary class, `permit / permit / deny`, HTTP `200 / 200 / 403`,
markers `1 / 1 / 0`, three canonical driver results, nine complete source
attestations, exact foreign before/after equality, complete 15-by-6 teardown,
valid `SHA256SUMS`, public-boundary secret scan, and:

```bash
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src ../../.venv/bin/python \
  tools/v3b1_local_envoy.py view --bundle \
  "artifacts/generated/v3b1-local-envoy/$kil_verified_run_id"
```

Expected: exactly one `accepted presenter .../live.html` line.

- [x] **Step 4: Stage only the accepted bundle and calibrated documents**

Validate the run ID from `manifest.json`, then:

```bash
git add -f "artifacts/generated/v3b1-local-envoy/$kil_verified_run_id/"
```

Update the listed documentation with the exact observed result and exclusions,
mark Task 11 complete, regenerate readers, and inspect `git diff --cached
--name-only`. Reject any staged sibling run, `.tools/` path, private journal,
credential, raw profile name, nonce, or host path.

- [ ] **Step 5: Validate, review, publish, and synchronize**

Run bundle checksums, offline view, full `make validate`, the public-boundary
secret scan, and separate specification and quality/security review passes.
Commit, push, create a proof PR, require public CI, merge, fast-forward local
`main`, and prove exact local/remote/GitHub main equality. Preserve both private
worktrees until the user supplies the offline-backup destination and retention
policy.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
