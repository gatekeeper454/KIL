# V4 Control-Plane Static-Manifest Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Authenticate the two effective kubeadm control-plane manifests from the exact owned Kind node, preserve them as replay-safe private evidence, and prove the kube-apiserver and kube-controller-manager API mirror configurations without widening the V4 claim boundary.

**Architecture:** Add one identity-bracketed, read-only Docker source proof immediately after `cluster_create`, persist it as a deterministic private checkpoint, and make the journal require that checkpoint before any image or apply mutation. Two later pure validators consume the same source plus the exact runtime-ownership proof to validate disk configuration, conditional CA mounts, and the independently transformed API mirror Pods.

**Tech Stack:** Python 3.12 standard library, existing KIL frozen proof records and journal grammar, the repository's closed YAML decoder, `unittest`, Markdown reader generation.

---

## File map and fixed boundaries

- Create `src/kil/v3b2_control_plane_manifest_source.py`: closed read command builder, four-observation identity bracket, raw manifest parsing, immutable source bindings and proof reconstruction.
- Create `tests/test_v3b2_control_plane_manifest_source.py`: independent literal fixtures and command/source adversarial matrix.
- Create `src/kil/v3b2_control_plane_manifest_source_record.py`: canonical 4 MiB private checkpoint encoding, no-follow write-once publication, and bounded replay.
- Create `tests/test_v3b2_control_plane_manifest_source_record.py`: persistence, file-safety, replay, corruption, and context-binding tests.
- Modify `src/kil/v3b2_journal.py`, `src/kil/v3b2_proofs.py`, and their tests: add the `control_plane_manifest_source` lifecycle family and require it between cluster creation and image import.
- Modify `src/kil/v3b2_controller.py` and `tests/test_v3b2_controller.py`: capture once after cluster creation and recover only from retained bytes.
- Create `src/kil/v3b2_kube_apiserver_mirror_configuration.py` and its test module: fixed disk configuration, all 32 CA subsets, owned Node InternalIP, and disk-to-API proof.
- Create `src/kil/v3b2_kube_controller_manager_mirror_configuration.py` and its test module: independent fixed disk configuration, all 32 CA subsets, and disk-to-API proof.
- Modify `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md` and regenerate its `.htm` reader at every accepted checkpoint.

The implementation remains static-only until the later V4 controller gate explicitly authorizes a live run. It must not start, stop, inspect, or delete any Colima profile while executing this plan.

### Task 1: Closed command and pure source proof

**Files:**
- Create: `src/kil/v3b2_control_plane_manifest_source.py`
- Create: `tests/test_v3b2_control_plane_manifest_source.py`
- Modify: `src/kil/v3b2_journal.py`
- Modify: `tests/test_v3b2_journal.py`

- [ ] **Step 1: Write failing tests for the exact command surface**

Add tests that require these public constants and command builder:

```python
COMPONENT_PATHS = (
    ("kube-apiserver", "/etc/kubernetes/manifests/kube-apiserver.yaml"),
    ("kube-controller-manager", "/etc/kubernetes/manifests/kube-controller-manager.yaml"),
)
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_SOURCE_RECORD_BYTES = 4 * 1024 * 1024

def test_read_argv_is_closed_to_two_literal_paths(self):
    node_id = "a" * 64
    self.assertEqual(
        control_plane_manifest_read_argv(node_id, "kube-apiserver"),
        ("docker", "exec", node_id, "/bin/cat", "--",
         "/etc/kubernetes/manifests/kube-apiserver.yaml"),
    )
    with self.assertRaises(ControlPlaneManifestSourceError):
        control_plane_manifest_read_argv(node_id, "../kube-scheduler")
```

Also reject short/uppercase/nonhex container IDs, caller paths, extra arguments, stdin, mutating classification, foreign Docker endpoints, missing private Docker configuration, shell forms, and path substitutions through `Command`.

- [ ] **Step 2: Run the command tests and confirm RED**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_control_plane_manifest_source tests.test_v3b2_journal -v`

Expected: import or command-grammar failures because the module and the two admitted Docker forms do not exist.

- [ ] **Step 3: Implement the minimal command API and journal grammar**

Create the module export surface and exact builder:

```python
__all__ = (
    "COMPONENT_PATHS", "MAX_MANIFEST_BYTES", "MAX_SOURCE_RECORD_BYTES",
    "ControlPlaneManifestBinding", "ControlPlaneManifestSourceError",
    "ControlPlaneManifestSourceProof", "control_plane_manifest_observation_specs",
    "control_plane_manifest_pod", "control_plane_manifest_read_argv",
    "validate_control_plane_manifest_source",
)

def control_plane_manifest_read_argv(node_container_id: str, component: str) -> tuple[str, ...]:
    if type(node_container_id) is not str or re.fullmatch(r"[0-9a-f]{64}", node_container_id) is None:
        raise ControlPlaneManifestSourceError("owned node container ID is invalid")
    paths = dict(COMPONENT_PATHS)
    if type(component) is not str or component not in paths:
        raise ControlPlaneManifestSourceError("control-plane component is not reviewed")
    return ("docker", "exec", node_container_id, "/bin/cat", "--", paths[component])
```

Extend `Command.__post_init__` with exactly the two forms above. Keep them non-mutating, stdin-free, and bound to the already journaled isolated Docker endpoint and private `DOCKER_CONFIG`.

- [ ] **Step 4: Write failing tests for the four-observation proof**

Test one independent literal pair of `v1/Pod` YAML documents and require:

```python
proof = validate_control_plane_manifest_source(
    context=context,
    owned_identity=owned_identity,
    observations=(before, apiserver_read, controller_manager_read, after),
)
self.assertEqual(tuple(binding.component for binding in proof.bindings),
                 ("kube-apiserver", "kube-controller-manager"))
self.assertFalse(proof.runtime_complete)
self.assertFalse(proof.application_complete)
```

Cover exact before/read/read/after order; identical 64hex container/config IDs; exact cluster, node, role and control-plane labels; running state; cluster-incarnation UID; nonzero/truncated/invalid UTF-8 reads; the 1 MiB boundary; absent/extra/duplicated sources; multiple YAML documents; tags, aliases, duplicate keys and ambiguous scalars; non-`v1/Pod` roots; raw and semantic digest changes; forged constructors; and strict false completion flags.

- [ ] **Step 5: Run the source tests and confirm RED at the proof boundary**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_control_plane_manifest_source -v`

Expected: failures because the proof records and validator are absent.

- [ ] **Step 6: Implement the pure source proof**

Use frozen/slotted records and reconstruct every field in `__post_init__`:

```python
@dataclass(frozen=True, slots=True)
class ControlPlaneManifestBinding:
    component: str
    path: str
    byte_count: int
    sha256: str
    semantic_sha256: str

@dataclass(frozen=True, slots=True)
class ControlPlaneManifestSourceProof:
    run_id: str
    cluster_uid: str
    node_container_id: str
    node_config_id: str
    raw_observations: tuple[bytes, ...]
    bindings: tuple[ControlPlaneManifestBinding, ...]
    runtime_complete: bool = False
    application_complete: bool = False
```

`validate_control_plane_manifest_source` must decode each successful stdout with strict UTF-8, call `decode_closed_yaml`, require an exact `apiVersion: v1`, `kind: Pod`, `metadata` and `spec` root, and hash `canonical(parsed_pod)` independently from the raw bytes. `control_plane_manifest_pod` must revalidate the exact proof and return a fresh decoded Pod only for the two literal component names.

- [ ] **Step 7: Run focused and neighboring proof tests**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_control_plane_manifest_source tests.test_v3b2_closed_yaml tests.test_v3b2_node_image_commands tests.test_v3b2_journal -v`

Expected: all tests pass.

- [ ] **Step 8: Commit Task 1**

```bash
git add src/kil/v3b2_control_plane_manifest_source.py src/kil/v3b2_journal.py tests/test_v3b2_control_plane_manifest_source.py tests/test_v3b2_journal.py
git commit -m "feat: add closed control-plane manifest source proof"
```

### Task 2: Durable source checkpoint and replay-safe lifecycle family

**Files:**
- Create: `src/kil/v3b2_control_plane_manifest_source_record.py`
- Create: `tests/test_v3b2_control_plane_manifest_source_record.py`
- Modify: `src/kil/v3b2_proofs.py`
- Modify: `src/kil/v3b2_journal.py`
- Modify: `tests/test_v3b2_proofs.py`
- Modify: `tests/test_v3b2_journal.py`

- [ ] **Step 1: Write failing checkpoint tests**

Require these functions:

```python
encoded = encode_control_plane_manifest_source_record(proof=proof, context=context)
published = publish_control_plane_manifest_source_record(
    path=checkpoint_path, proof=proof, context=context)
self.assertEqual(published, encoded)
self.assertEqual(
    read_control_plane_manifest_source_record(path=checkpoint_path, context=context),
    proof,
)
```

Test canonical bytes, exact context reconstruction, the 4 MiB boundary, write-once idempotence, existing altered bytes, symlink/hardlink/FIFO/non-0600 rejection, parent replacement, corruption, unknown fields, forged nested proof, and file/parent fsync.

- [ ] **Step 2: Confirm checkpoint tests are RED**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_control_plane_manifest_source_record -v`

Expected: import failure because no durable source record exists.

- [ ] **Step 3: Implement canonical checkpoint encoding and safe publication**

Use one closed envelope:

```python
{
    "schema": "kil.v4.control-plane-manifest-source.v1",
    "context": expected_context,
    "proof": encoded_proof,
}
```

Reuse the existing no-follow, owned regular file, 0600, single-link, exclusive/no-replace, flush/fsync, atomic-publication, and parent-fsync helpers. The deterministic controller path is `control-plane-manifest-source-<intent_sequence>.json`; the reader must never discover or substitute another filename.

- [ ] **Step 4: Write failing lifecycle tests**

Add `control_plane_manifest_source` to the tested operation set and require:

```python
self.assertLess(event_names.index("cluster_create_complete"),
                event_names.index("control_plane_manifest_source_intent"))
self.assertLess(event_names.index("control_plane_manifest_source_complete"),
                event_names.index("image_import_intent"))
```

Test one deterministic local checkpoint observation request, exact `kind_cluster` pair details, source completion only after `cluster_create_complete`, rejection of `image_import_intent` before source completion, failure-to-teardown-only behavior, terminal digest binding, `prior_control_plane_manifest_source` injection rejection, reconstruction from retained bytes, and recovery that never issues live Docker reads.

- [ ] **Step 5: Confirm lifecycle tests are RED**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_proofs tests.test_v3b2_journal -v`

Expected: failures for the missing family, operation, expected-input version, and reconstruction API.

- [ ] **Step 6: Implement the operation and journal order**

Add:

```python
Operation(
    family="control_plane_manifest_source",
    requests=(ObservationRequest(
        "control_plane_manifest_source",
        source="control_plane_manifest_source",
    ),),
)
```

Add `control_plane_manifest_source_version: 1` to immutable preflight inputs; add `reconstruct_prior_control_plane_manifest_source(context)`; reserve caller injection of `prior_control_plane_manifest_source`; and enforce `cluster_create_complete -> control_plane_manifest_source_complete -> image_import_intent`. A persisted checkpoint missing only its terminal may be revalidated and completed; a missing or invalid checkpoint after cluster creation becomes teardown-only and never triggers recollection.

- [ ] **Step 7: Run focused lifecycle and persistence tests**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_control_plane_manifest_source tests.test_v3b2_control_plane_manifest_source_record tests.test_v3b2_proofs tests.test_v3b2_journal tests.test_v3b2_observed_lifecycle -v`

Expected: all tests pass.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/kil/v3b2_control_plane_manifest_source_record.py src/kil/v3b2_proofs.py src/kil/v3b2_journal.py tests/test_v3b2_control_plane_manifest_source_record.py tests/test_v3b2_proofs.py tests/test_v3b2_journal.py
git commit -m "feat: persist V4 control-plane manifest evidence"
```

### Task 3: Controller capture ordering and recovery

**Files:**
- Modify: `src/kil/v3b2_controller.py`
- Modify: `tests/test_v3b2_controller.py`

- [ ] **Step 1: Write failing controller tests**

Require an exact successful order:

```python
self.assertLess(labels.index("cluster_create_complete"),
                labels.index("control_plane_manifest_source_complete"))
self.assertLess(labels.index("control_plane_manifest_source_complete"),
                labels.index("image_import_intent"))
```

Add failure cases for changed before/after node identity, stopped node, nonzero or truncated reads, invalid checkpoint publication, and missing/corrupt recovery checkpoint. Assert every failure dispatches zero image-load, Calico, and application apply commands. Add crash-boundary tests proving a persisted source with a missing terminal is revalidated from disk and that recovery executes zero `docker exec ... /bin/cat` commands.

- [ ] **Step 2: Confirm controller tests are RED**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_controller.V3B2ControllerTest.test_image_load_and_calico_apply_complete_before_application_gate -v`

Expected: failure because the source checkpoint is not yet inserted between cluster creation and image import.

- [ ] **Step 3: Implement capture and replay branches**

Add a controller producer with the fixed shape:

```python
def _checkpoint_control_plane_manifest_source(self) -> CommandResult:
    context = load_expected_context(self.paths.journal)
    identity = OwnedIdentity.from_context(context)
    observations = tuple(
        self._observe(spec.command, "control_plane_manifest_source_invalid")
        for spec in control_plane_manifest_observation_specs(identity)
    )
    proof = validate_control_plane_manifest_source(
        context=context, owned_identity=identity, observations=observations)
    publish_control_plane_manifest_source_record(
        path=self._control_plane_manifest_checkpoint_path(context),
        proof=proof, context=context)
    return CommandResult(0, "", "")
```

Insert `_journal_pair("control_plane_manifest_source", {"kind_cluster": LAB_IDENTITY}, self._checkpoint_control_plane_manifest_source)` immediately after `cluster_create` and before any image or apply work. Add a `_collect_observations` branch that reads only the deterministic retained checkpoint. Do not add a recovery path that issues the four live capture commands.

- [ ] **Step 4: Run controller, journal, and proof integration tests**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_controller tests.test_v3b2_journal tests.test_v3b2_proofs tests.test_v3b2_control_plane_manifest_source_record -v`

Expected: all default-gate tests pass; the existing 16 V4 lifecycle methods remain explicitly deferred.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/kil/v3b2_controller.py tests/test_v3b2_controller.py
git commit -m "feat: checkpoint control-plane manifests after cluster creation"
```

### Task 4: Kube-apiserver disk and API mirror proof

**Files:**
- Create: `src/kil/v3b2_kube_apiserver_mirror_configuration.py`
- Create: `tests/test_v3b2_kube_apiserver_mirror_configuration.py`

- [ ] **Step 1: Write the exhaustive independent fixture tests**

Define the candidate set literally and run all masks:

```python
CA_CANDIDATES = (
    ("etc-ca-certificates", "/etc/ca-certificates"),
    ("etc-pki-ca-trust", "/etc/pki/ca-trust"),
    ("etc-pki-tls-certs", "/etc/pki/tls/certs"),
    ("usr-local-share-ca-certificates", "/usr/local/share/ca-certificates"),
    ("usr-share-ca-certificates", "/usr/share/ca-certificates"),
)

for mask in range(32):
    selected = tuple(pair for bit, pair in enumerate(CA_CANDIDATES)
                     if mask & (1 << bit))
    proof = validate_kube_apiserver_mirror_configuration(
        ownership=literal_runtime_fixture(selected),
        source=literal_source_fixture(selected),
    )
    self.assertEqual(proof.bindings[0].conditional_volume_names,
                     tuple(name for name, _ in selected))
```

Build disk and API candidates independently. Cover the two unconditional `ca-certs` and `k8s-certs` volumes/mounts; exact lexicographic order; partial/duplicate/renamed/unexpected candidates; wrong path, `DirectoryOrCreate`, or `readOnly`; all fixed Pod/container fields; owned Node InternalIP binding; dynamic address drift; API default/metadata drift; arbitrary status retention; coordinated retained-proof tampering; constructors; and strict false flags. Run a second 32-mask loop in which API-side candidates differ from the authenticated disk subset and require rejection.

- [ ] **Step 2: Confirm apiserver tests are RED**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_kube_apiserver_mirror_configuration -v`

Expected: import failure because the component proof does not exist.

- [ ] **Step 3: Implement the apiserver proof**

Expose:

```python
def kube_apiserver_mirror_api_spec(
    *, source: ControlPlaneManifestSourceProof, node_internal_ip: str,
) -> dict:
    source.__post_init__()
    disk_pod = control_plane_manifest_pod(
        source=source, component="kube-apiserver")
    return _expected_api_pod(
        disk_pod=disk_pod, node_internal_ip=node_internal_ip)

def validate_kube_apiserver_mirror_configuration(
    *, ownership: RuntimeOwnershipProof,
    source: ControlPlaneManifestSourceProof,
) -> KubeAPIServerMirrorConfigurationProof:
    binding = _compute(ownership=ownership, source=source)
    return KubeAPIServerMirrorConfigurationProof(
        ownership=ownership, source=source, bindings=(binding,))
```

Reconstruct both dependency proofs before use. Validate the fixed disk document and derive only the conditional subset from it. Independently transform the expected disk Pod with reviewed kubelet/API defaults, then compare the one owned API mirror without copying candidate API fields into the expectation. Derive the InternalIP using the same retained owned-Node rules as etcd, but keep apiserver-specific errors local.

- [ ] **Step 4: Run apiserver and adjacent static-mirror tests**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_kube_apiserver_mirror_configuration tests.test_v3b2_etcd_mirror_configuration tests.test_v3b2_scheduler_mirror_configuration tests.test_v3b2_api_defaults -v`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/kil/v3b2_kube_apiserver_mirror_configuration.py tests/test_v3b2_kube_apiserver_mirror_configuration.py
git commit -m "feat: prove kube-apiserver mirror configuration"
```

### Task 5: Kube-controller-manager disk and API mirror proof

**Files:**
- Create: `src/kil/v3b2_kube_controller_manager_mirror_configuration.py`
- Create: `tests/test_v3b2_kube_controller_manager_mirror_configuration.py`

- [ ] **Step 1: Write exhaustive independent controller-manager tests**

Run the same literal five-pair, 32-mask acceptance matrix and a 32-mask disk/API mismatch rejection matrix, but use an independently written controller-manager disk fixture. Require unconditional `ca-certs`, `k8s-certs`, and `kubeconfig` volumes/mounts, controller-manager-specific command/options and probes, lexicographic ordering, exact mirror metadata/defaults, arbitrary status retention, dependency reconstruction, and strict false flags.

```python
proof = validate_kube_controller_manager_mirror_configuration(
    ownership=literal_runtime_fixture(selected),
    source=literal_source_fixture(selected),
)
self.assertEqual(proof.bindings[0].component, "kube-controller-manager")
self.assertFalse(proof.runtime_complete)
self.assertFalse(proof.application_complete)
```

- [ ] **Step 2: Confirm controller-manager tests are RED**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_kube_controller_manager_mirror_configuration -v`

Expected: import failure because the component proof does not exist.

- [ ] **Step 3: Implement the independent controller-manager proof**

Expose:

```python
def kube_controller_manager_mirror_api_spec(
    *, source: ControlPlaneManifestSourceProof,
) -> dict:
    source.__post_init__()
    disk_pod = control_plane_manifest_pod(
        source=source, component="kube-controller-manager")
    return _expected_api_pod(disk_pod=disk_pod)

def validate_kube_controller_manager_mirror_configuration(
    *, ownership: RuntimeOwnershipProof,
    source: ControlPlaneManifestSourceProof,
) -> KubeControllerManagerMirrorConfigurationProof:
    binding = _compute(ownership=ownership, source=source)
    return KubeControllerManagerMirrorConfigurationProof(
        ownership=ownership, source=source, bindings=(binding,))
```

Keep the full fixed expectation local to this module. Reconstruct the source and ownership proofs, validate the controller-manager disk document, derive only its conditional subset, apply only reviewed kubelet/API defaults, and require the sole owned API mirror to match. Do not import apiserver expected factories or conditional decisions.

- [ ] **Step 4: Run both new component suites and all static mirrors**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_kube_apiserver_mirror_configuration tests.test_v3b2_kube_controller_manager_mirror_configuration tests.test_v3b2_etcd_mirror_configuration tests.test_v3b2_scheduler_mirror_configuration -v`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 5**

```bash
git add src/kil/v3b2_kube_controller_manager_mirror_configuration.py tests/test_v3b2_kube_controller_manager_mirror_configuration.py
git commit -m "feat: prove controller-manager mirror configuration"
```

### Task 6: Static acceptance checkpoint

**Files:**
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm`

- [ ] **Step 1: Run the combined static gate**

Run: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_control_plane_manifest_source tests.test_v3b2_control_plane_manifest_source_record tests.test_v3b2_kube_apiserver_mirror_configuration tests.test_v3b2_kube_controller_manager_mirror_configuration tests.test_v3b2_controller tests.test_v3b2_journal tests.test_v3b2_proofs -v`

Expected: all default tests pass and exactly the existing 16 V4 lifecycle methods remain deferred.

- [ ] **Step 2: Run full repository validation**

Run: `PYTHONDONTWRITEBYTECODE=1 make validate PYTHON=../../.venv/bin/python`

Expected: the full test suite and Markdown reader check pass with only the recorded V4 lifecycle skips.

- [ ] **Step 3: Record the accepted evidence boundary**

Append a dated lineage entry stating the exact test counts, accepted source/disk/API claims, unchanged false runtime/application flags, absence of live Colima/Kind execution, unresolved platform image/status/readiness composition, and the next gate.

Read the final existing `### T-<number>` heading, increment it by one, and append a heading named “V4 control-plane static-manifest source accepted.” Record these exact fields: the approved design and plan as input; “Confirmed static implementation checkpoint; no live claim” as decision status; the two identity-bracketed private manifest sources and their two reconstructable API mirror configurations as the accepted claim boundary; runtime, readiness, application completion, V4 completion, and V3C as explicitly unclaimed; and all-ten-platform-Pod configuration/image/status/readiness composition as the next gate.

- [ ] **Step 4: Regenerate and verify readers**

Run: `make docs-html PYTHON=../../.venv/bin/python`

Run: `make docs-html-check PYTHON=../../.venv/bin/python`

Expected: all tracked Markdown readers are current.

- [ ] **Step 5: Request specification and quality review, then commit**

After an independent reviewer reports no unresolved Critical or Important findings:

```bash
git add docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.htm
git commit -m "docs: record V4 control-plane manifest acceptance"
```

- [ ] **Step 6: Push the private implementation branch and verify synchronization**

```bash
git push origin codex/v3b2-kind-calico-implementation
git rev-parse HEAD
git rev-parse origin/codex/v3b2-kind-calico-implementation
git status --short
```

Expected: both revisions are identical and status output is empty.

## Plan self-review

- Spec coverage: Tasks 1–3 cover closed capture, private persistence, lifecycle ordering, crash recovery, and no recollection; Tasks 4–5 cover both fixed disk documents, all 32 conditional subsets, independent disk-to-API transformations, dynamic apiserver address binding, reconstruction, and false completion flags; Task 6 records the bounded static acceptance.
- Type consistency: every later component validator consumes the exact `ControlPlaneManifestSourceProof` and `RuntimeOwnershipProof` defined or already present; public function and record names are stable across tasks.
- Claim containment: this plan authorizes no live cluster execution, no foreign-profile mutation, no readiness or application claim, and no V3C work.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
