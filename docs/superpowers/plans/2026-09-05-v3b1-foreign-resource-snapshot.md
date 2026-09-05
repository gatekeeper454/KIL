# V3B-1 Foreign-Resource Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add exact, durable before/after foreign Colima resource evidence so a fresh request-free V3B-1 lifecycle can safely unlock the one-shot central proof gate.

**Architecture:** Keep raw profile names only in the private lifecycle journal, derive run-scoped HMAC pseudonyms for public evidence, and advance new controller output to manifest generation v3 while retaining explicit v1/v2 verification. Capture the before snapshot after journal creation and before the first Colima mutation intent; capture the after snapshot after exact dedicated-profile deletion and before publication. Any missing, malformed, duplicate, phase-invalid, or unequal snapshot fails closed and never authorizes mutation of foreign profiles.

**Tech Stack:** Python 3.12 standard library (`hmac`, `hashlib`, `json`), existing canonical JSON helpers, `unittest`, Colima closed JSON inventory, generated Markdown readers.

---

### Task 1: Closed private snapshots and pseudonymous projections

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Test: `tests/test_v3b1_local_envoy.py`

- [ ] **Step 1: Write failing pure-contract tests**

Import `canonical_foreign_profile_snapshot`, `compare_foreign_profile_snapshots`, and `project_foreign_profile_snapshot`, then add tests that exercise the real helpers:

```python
def test_foreign_snapshots_are_closed_sorted_and_exclude_the_lab_profile(self):
    records = parse_colima_profiles(
        '[{"name":"zeta","status":"Stopped","arch":"aarch64",'
        '"cpus":2,"memory":4294967296,"disk":21474836480,"runtime":"docker"},'
        '{"name":"kil-v3-lab","status":"Running","arch":"aarch64",'
        '"cpus":4,"memory":8589934592,"disk":64424509440,"runtime":"docker"},'
        '{"name":"alpha","status":"Stopped","arch":"x86_64",'
        '"cpus":1,"memory":2147483648,"disk":10737418240,"runtime":"containerd"}]'
    )
    snapshot = canonical_foreign_profile_snapshot(
        records, "before_colima_mutation"
    )
    self.assertEqual([item["name"] for item in snapshot["profiles"]], ["alpha", "zeta"])
    self.assertNotIn("kil-v3-lab", canonical_json(snapshot))

def test_public_projection_is_nonce_scoped_and_name_free(self):
    snapshot = canonical_foreign_profile_snapshot(
        ({"name": "personal", "status": "Stopped", "arch": "aarch64",
          "cpus": 4, "memory": 4294967296, "disk": 21474836480,
          "runtime": "containerd"},),
        "before_colima_mutation",
    )
    first = project_foreign_profile_snapshot(snapshot, HEX_A)
    second = project_foreign_profile_snapshot(snapshot, HEX_B)
    self.assertNotEqual(first, second)
    self.assertNotIn("personal", canonical_json(first))
```

Also cover duplicate names, unknown fields, boolean resources, nonpositive resources, surrogate-containing names, invalid stages, duplicate public references, and every mismatch category.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_v3b1_local_envoy.ControllerContractTest -v
```

Expected: import failure because the three snapshot helpers do not exist.

- [ ] **Step 3: Implement the minimal pure helpers**

Add closed constants and helpers near `parse_colima_profiles`:

```python
FOREIGN_SNAPSHOT_SCHEMA = "kil.v3b1-foreign-profile-snapshot.v1"
FOREIGN_ATTESTATION_SCHEMA = "kil.v3b1-foreign-profile-attestation.v1"
_FOREIGN_CAPTURE_STAGES = {
    "before_colima_mutation",
    "after_owned_profile_deletion",
}
_FOREIGN_PROFILE_FIELDS = {
    "name", "status", "arch", "cpus", "memory", "disk", "runtime",
}

def canonical_foreign_profile_snapshot(
    records: Sequence[Mapping[str, object]], capture_stage: str
) -> dict[str, object]:
    """Validate and sort one exact private foreign-profile observation."""

def project_foreign_profile_snapshot(
    snapshot: Mapping[str, object], execution_nonce: str
) -> list[dict[str, object]]:
    """Replace exact private names with run-scoped HMAC references."""

def compare_foreign_profile_snapshots(
    before: Mapping[str, object], after: Mapping[str, object]
) -> dict[str, object]:
    """Return exact equality plus sorted closed mismatch categories."""
```

Use `hmac.new(bytes.fromhex(execution_nonce), b"kil.v3b1-foreign-profile-ref.v1\0" + name.encode("utf-8"), sha256).hexdigest()` and reject all ambiguous inputs before producing a projection.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the focused class from Step 2. Expected: all tests pass.

- [ ] **Step 5: Commit the pure contract**

```bash
git add tools/v3b1_local_envoy.py tests/test_v3b1_local_envoy.py
git commit -m "feat: define V3B-1 foreign resource snapshots"
```

### Task 2: Versioned lifecycle-journal authority

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Test: `tests/test_v3b1_local_envoy.py`

- [ ] **Step 1: Write failing journal-schema and ordering tests**

Create a v2 journal, append `foreign_profile_snapshot_before`, and assert it must be unique and must precede `preflight_complete` and `colima_start_intent`. Append `foreign_profile_snapshot_after` and assert it must follow `colima_delete_complete` and precede `publication_intent`. Verify missing, duplicated, reordered, or synthesized snapshots fail loading. Retain a fixture proving a v1 journal without snapshot events still loads only under its legacy rules.

- [ ] **Step 2: Run journal tests and verify RED**

```bash
PYTHONPATH=src python -m unittest tests.test_v3b1_local_envoy.JournalRecoveryTest -v
```

Expected: failures because snapshot events and journal v2 dispatch are absent.

- [ ] **Step 3: Add explicit journal generation dispatch**

```python
LEGACY_JOURNAL_SCHEMA = "kil.v3b1-lifecycle-journal.v1"
JOURNAL_SCHEMA = "kil.v3b1-lifecycle-journal.v2"
```

Keep the closed top-level fields unchanged. Teach `_validate_lifecycle_event_details` to validate the two snapshot events and a closed `foreign_profile_mismatch` record. Teach `_validate_lifecycle_history` to enforce v2 ordering, uniqueness, and mutation/publication prerequisites while preserving exact v1 acceptance.

- [ ] **Step 4: Run journal tests and verify GREEN**

Run the command from Step 2. Expected: all journal recovery tests pass.

- [ ] **Step 5: Commit durable journal authority**

```bash
git add tools/v3b1_local_envoy.py tests/test_v3b1_local_envoy.py
git commit -m "feat: bind foreign snapshots in the V3B-1 journal"
```

### Task 3: Capture snapshots at exact lifecycle boundaries

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Test: `tests/test_v3b1_local_envoy.py`

- [ ] **Step 1: Write failing controller-order tests**

Use `FakeRunner` and a temporary repository to prove:

```python
before = controller._capture_foreign_profile_snapshot("before_colima_mutation")
self.assertEqual(before["capture_stage"], "before_colima_mutation")
self.assertEqual(runner.calls[-1][0], ["colima", "list", "--json"])
```

For `up`, inject a crash immediately after the durable before event and prove no `colima start` call occurred. For `down` and both recovery publication paths, assert the after event follows verified dedicated-profile absence and precedes publication intent. Assert a mismatch records only snapshot digests and categories, finishes owned teardown, never issues a command naming a foreign profile, and remains nonpromotable.

- [ ] **Step 2: Run controller and teardown tests and verify RED**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_v3b1_local_envoy.ControllerContractTest \
  tests.test_v3b1_local_envoy.TeardownContinuationTest -v
```

Expected: failures because the capture method and lifecycle calls are absent.

- [ ] **Step 3: Implement fresh capture and recovery reuse**

Add:

```python
def _capture_foreign_profile_snapshot(self, capture_stage: str) -> dict[str, object]:
    listed = self._execute(["colima", "list", "--json"], timeout_s=20)
    return canonical_foreign_profile_snapshot(
        parse_colima_profiles(listed.stdout), capture_stage
    )
```

Call it from `up` after journal creation and before `preflight_complete`. Add one shared post-deletion helper that loads the durable before snapshot, captures and journals the after snapshot exactly once, compares them, records a mismatch when needed, and returns both snapshots plus comparison. Use that helper in normal teardown, pre-manifest teardown, post-delete recovery, and publication recovery without synthesizing missing evidence.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: all focused tests pass.

- [ ] **Step 5: Commit lifecycle capture**

```bash
git add tools/v3b1_local_envoy.py tests/test_v3b1_local_envoy.py
git commit -m "feat: capture foreign resources around V3B-1 lifecycle"
```

### Task 4: Add private/public evidence generation v3

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Test: `tests/test_v3b1_local_envoy.py`
- Test: `tests/fixtures/v3b1-public-bundle-v1/manifest.json`

- [ ] **Step 1: Write failing generation-dispatch tests**

Require new runs to use:

```python
self.assertEqual(manifest()["schema_version"], "kil.v3b1-manifest.v3")
self.assertEqual(public_manifest["schema_version"], "kil.v3b1-public-manifest.v3")
self.assertEqual(
    public_manifest["foreign_profile_attestation"]["unchanged"], True
)
```

Prove v1 and v2 inputs retain their original file sets and validators; reject cross-generation snapshot fields, repaired checksums, inconsistent `unchanged`, duplicate or unordered references, and changed complete tuples.

- [ ] **Step 2: Run evidence tests and verify RED**

```bash
PYTHONPATH=src python -m unittest tests.test_v3b1_local_envoy.EvidenceBundleTest -v
```

Expected: schema and attestation assertions fail because generation v3 is absent.

- [ ] **Step 3: Implement explicit v3 schemas and validators**

Add v3 constants for private manifest, public manifest, authoritative bundle, and public commitment. Extend `_bundle_generation`, `_authoritative_file_names`, `_validate_manifest`, `_validate_public_manifest`, `_public_commitment_sha256`, and authoritative-attestation dispatch. New `create_run_manifest` output is v3; legacy v1/v2 validators remain unchanged and reject v3-only fields.

Build the public record only from journal-authoritative snapshots:

```python
{
    "schema_version": FOREIGN_ATTESTATION_SCHEMA,
    "before": project_foreign_profile_snapshot(before, execution_nonce),
    "after": project_foreign_profile_snapshot(after, execution_nonce),
    "unchanged": comparison["unchanged"],
}
```

Complete publication requires `unchanged is True`; incomplete failure publication may retain a truthful `False`.

- [ ] **Step 4: Run evidence and legacy tests and verify GREEN**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_v3b1_local_envoy.EvidenceBundleTest \
  tests.test_v3b1_request_driver.DriverProtocolTest -v
```

Expected: v3 and legacy compatibility tests pass.

- [ ] **Step 5: Commit evidence generation v3**

```bash
git add tools/v3b1_local_envoy.py tests/test_v3b1_local_envoy.py tests/fixtures/v3b1-public-bundle-v1
git commit -m "feat: publish V3B-1 foreign resource evidence"
```

### Task 5: Bind publication recovery and the offline verifier

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Test: `tests/test_v3b1_local_envoy.py`

- [ ] **Step 1: Write failing recovery and presenter tests**

Prove publication recovery re-derives the public attestation from the two exact journal events and the private execution nonce, rejects public/private divergence even after repaired hashes, and refuses a complete presenter when either snapshot is missing or unequal. Prove empty equal arrays are valid and unequal failure bundles remain nonpresentable.

- [ ] **Step 2: Run recovery and evidence tests and verify RED**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_v3b1_local_envoy.JournalRecoveryTest \
  tests.test_v3b1_local_envoy.EvidenceBundleTest -v
```

Expected: failures because recovery does not bind snapshot authority.

- [ ] **Step 3: Thread journal authority through publication**

Add `_journal_foreign_profile_attestation(events, execution_nonce)` and pass its result into both `finalize_publication` and `_verify_recovered_publication`. Validate the exact attestation inside `_validate_presenter_snapshot`; bind it through `manifest.json`, the v3 public commitment, and `SHA256SUMS`. Do not add a sidecar.

- [ ] **Step 4: Run recovery and evidence tests and verify GREEN**

Run the command from Step 2. Expected: all tests pass.

- [ ] **Step 5: Commit recovery/verifier binding**

```bash
git add tools/v3b1_local_envoy.py tests/test_v3b1_local_envoy.py
git commit -m "feat: verify V3B-1 foreign snapshot equality"
```

### Task 6: Document, review, and statically qualify the prerequisite

**Files:**

- Modify: `README.md`
- Modify: `adapters/envoy/README.md`
- Modify: `docs/lab/V3-PROGRESS.md`
- Modify: `docs/lab/V3B1-TASK10-REQUEST-FREE-GATE.md`
- Modify: `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Modify: generated `.htm` companions
- Test: `tests/test_v3b1_documentation.py`

- [ ] **Step 1: Write failing documentation assertions**

Require the current docs to name the implemented v3 snapshot contract, preserve Task 10 as historical v2 evidence, and state that a fresh request-free v3 lifecycle must pass before the central run.

- [ ] **Step 2: Run documentation tests and verify RED**

```bash
PYTHONPATH=src python -m unittest tests.test_v3b1_documentation -v
```

Expected: new assertions fail against the pre-extension wording.

- [ ] **Step 3: Update calibrated claims and generate readers**

Update only the implementation/prerequisite status. Do not claim an accepted enforcement outcome, Kind/Calico validation, historical prevention, repetition, performance, or production suitability. Run:

```bash
make docs-html PYTHON=python
```

- [ ] **Step 4: Run the complete static gate**

```bash
make validate PYTHON=python
```

Expected: all unit tests, all Markdown-reader checks, project metadata, and `git diff --check` pass.

- [ ] **Step 5: Review the exact change set**

```bash
git diff --check
git status --short
git diff --stat origin/main...HEAD
```

Confirm no generated runtime bundle, `.tools` state, private journal, credential, key, or unrelated presentation artifact is staged.

- [ ] **Step 6: Commit the static prerequisite**

```bash
git add README.md adapters/envoy/README.md docs/lab/V3-PROGRESS.md \
  docs/lab/V3B1-TASK10-REQUEST-FREE-GATE.md \
  docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md \
  docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md \
  tests/test_v3b1_documentation.py
git add '*.htm'
git commit -m "docs: qualify V3B-1 snapshot prerequisite"
```

- [ ] **Step 7: Stop before live execution**

The implementation branch must be independently reviewed, pushed, pass public CI, merge, and synchronize with `main`. Only then run a fresh request-free `preflight -> up -> readiness -> down` lifecycle. The central `run` remains prohibited until that new v3 gate is published, reviewed, merged, and synchronized.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
