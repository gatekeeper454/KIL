# V3B-2a Kind/Calico Nominal Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, statically validate, and execute the request-free and nominal
V3B-2a Kind/Calico lifecycles without changing any Colima profile other than
the dedicated `kil-v3-lab` profile.

**Architecture:** Add a separate V3B-2 contract and controller stack rather
than extending the V3B-1 controller monolith. Pure modules own the closed
profile and schemas, deterministic Kubernetes objects, inventory and policy
validation, lifecycle recovery, and evidence verification; a thin CLI composes
them through typed commands. The live sequence is deliberately split by public
gates: reviewed static implementation, request-free lifecycle, then one fresh
nominal lifecycle.

**Tech Stack:** Python 3.12.13, stdlib `unittest`, canonical JSON/JSONL,
SHA-256, Colima 0.10.3, Docker CLI 29.7.2, Kind 0.32.0, Kubernetes 1.36.1,
kubectl 1.36.3, Envoy 1.39.1, and Calico 3.32.0.

---

## Scope split and hard gates

This plan implements only **V3B-2a nominal parity**. V3B-2b is a second,
sequential implementation plan because it introduces a closed campaign index,
multiple clean lifecycles, poisoning cases, and calibrated diagnostic bundles.
V3B-2b planning starts only after the V3B-2a public proof is accepted and the
local and remote `main` commits are exactly synchronized.

The V3B-2a implementation has three non-collapsible gates:

1. static code, tests, specification review, quality/security review, public CI,
   merge, and exact `main` synchronization;
2. a request-free lifecycle that creates the cluster but sends zero driver
   instructions and zero HTTP requests, followed by exact teardown and public
   evidence synchronization; and
3. one newly authorized nominal lifecycle from a fresh cluster, again followed
   by exact teardown before publication.

No task may run a live command merely because its static tests pass. Every live
task begins with an explicit source-commit and synchronization assertion. Every
Colima mutation must include `--profile kil-v3-lab`. Foreign profiles may be
running or stopped; they are recorded and compared but never stopped, started,
deleted, or repaired.

## Resolved Calico content identity

The upstream manifest at the already approved release URL was fetched only for
planning and measured as follows:

| Material | Exact identity |
|---|---|
| Upstream `calico.yaml` | 349,123 bytes; SHA-256 `bccabc607685551db918f66da724893eca3e69a50c5a3e3077029b02dbab8d35` |
| `quay.io/calico/cni:v3.32.0` index | `sha256:1cfc6aa9c4dad3575fdf36b78185fd7d68bcd4acc95778f8342be4fb6a851a14` |
| `quay.io/calico/node:v3.32.0` index | `sha256:f4fafd8ba641d96c5a91b01e5a519117d77d55dee789a3562ba3ad4aa125b36a` |
| `quay.io/calico/kube-controllers:v3.32.0` index | `sha256:adf0ac895796d21bca5383bc81c4cd2614be3a4308085b47857d7999f4cc2b1f` |
| Deterministically digest-pinned manifest | SHA-256 `ac5ab7451dda57cfbf47d584ee901b896b1a9ff388d95b6f01b59f1e1130fdfa` |

The vendoring step must independently fetch the same upstream bytes, verify the
first checksum, replace only the three exact tag strings with the index digests
above, and verify the final checksum. Registry-resolved arm64 image IDs are
captured separately from realized Pods and must be stable across each evidence
read.

The corrective pass also binds the canonical projection
`deploy/kind/calico-v3.32.0.objects.json` to SHA-256
`de76213b8097d55a674cbe88ef9ac349317b067fb3c6fc326d4280d17c7104a8`.
It contains all 38 YAML documents, including CRDs and RBAC objects, not only
the subset visible in the public workload topology. Root independently checked
every projected document against a safe parse of the checksummed YAML. This
review-time projection introduces no runtime YAML parser dependency. Its
closed top-level keys are `source_sha256` and `items`; both source bytes and
canonical projection bytes must match before deriving application proofs.

#### Verified native image identity chains

Read-only registry verification on 2026-09-07 checked each pinned index hash,
the unique linux/arm64 child hash and descriptor size, then the config blob
hash/size and its linux/arm64 fields. Keep these identities distinct:

| Image | ARM64 manifest SHA-256 | Config SHA-256 |
|---|---|---|
| Envoy | `b21240e552b588017072424716c0bce30000f49deed6262bde55b042b5acfd97` | `ef846ec85aabf01a2ff7176a185260e476ca43d20478f57281d88f7a66d5671f` |
| Calico CNI | `98517eda58fb74caceb68efd19849daba32acc1e145423d3ba768ba70de24aac` | `b2f2bd95db9e9051c42eba83d403d3a0dc76ea589340911306a4073e92779c72` |
| Calico node | `f737550f3eb703d65941c0ae4daddd52431395ad4b33184c44f1fe467c0f328c` | `66d7bdfe4b6af8092769145316c850fed71ed50b2bb5a197e325db2e05a6ec09` |
| Calico controllers | `a935ba71347e6a7ea95e1dfe94fe97d6873386d8d3af4bff5b76d39018a4a4bd` | `5a2dc3609caf3dabd2a7357ebe0ea306e63bbaf2c6af88b41a2d1234cb9056eb` |

Source indexes:
[Envoy](https://registry-1.docker.io/v2/envoyproxy/envoy/manifests/sha256:57e14a549d7bd43c8d3f6d03e8cfa653e037d4b38e133acd9b54f38c524401b4),
[CNI](https://quay.io/v2/calico/cni/manifests/sha256:1cfc6aa9c4dad3575fdf36b78185fd7d68bcd4acc95778f8342be4fb6a851a14),
[node](https://quay.io/v2/calico/node/manifests/sha256:f4fafd8ba641d96c5a91b01e5a519117d77d55dee789a3562ba3ad4aa125b36a),
[controllers](https://quay.io/v2/calico/kube-controllers/manifests/sha256:adf0ac895796d21bca5383bc81c4cd2614be3a4308085b47857d7999f4cc2b1f).
The accepted KIL archive manifest is
`sha256:45a167d79b92f352af05a3e9cb8a9df8e972e38ab23d04ca692053e2eaf63649`,
with config `sha256:f21285be21c8f691b9b60b7e38bb309564a5cc238512c7455eb7759f4d922ddb`.

Docker image-inspect `.Id` and CRI image-list `.id` use the config identity.
The pinned node-store `ctr images check` target digest instead binds the
stored manifest/index. Kubernetes Pod `containerStatuses[].imageID` has a
third, explicitly traced representation: the
[1.36.1 kubelet API projection](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/kubelet_pods.go)
uses internal `ImageRef`, not internal `ImageID`.
[containerd 2.3.1 ContainerStatus](https://github.com/containerd/containerd/blob/v2.3.1/internal/cri/server/container_status.go)
sets that reference to a stored repo digest when present, falling back to the
config digest otherwise. Thus digest-pulled Envoy/Calico should bind their
exact repository/index reference; a tag-only imported KIL image may report
its config digest. Validate that branch against the observed node-store
reference chain, not by permitting either arbitrary digest suffix. Preserve
the raw runtime representation while publishing its independently validated
content relationship. These are source/registry checks, not live runtime proof.

## Closed schema inventory

The implementation must declare these field sets as constants and validate
them with exact-key equality before controller code imports them:

- `kil.v3b2-profile.v1`: `schema_version`, `host_os`, `host_arch`,
  `colima_version`, `colima_profile`, `lima_version`, `docker_cli_version`,
  `kind_version`, `kubernetes_version`, `kind_node_image`, `kubectl_version`,
  `envoy_image`, `calico_version`, `calico_upstream_url`,
  `calico_upstream_sha256`, `calico_manifest_path`, `calico_manifest_sha256`,
  `calico_images`, `cluster_name`, `pod_subnet`, `service_subnet`,
  `system_namespaces`, `application_namespaces`, and `evidence_scope`.
- `kil.v3b2-journal.v1`: `schema_version`, `run_id`, `lifecycle_mode`,
  `execution_nonce`, `source_commit`, `profile_sha256`, `phase`,
  `global_context_before`, `foreign_profiles_before`, `expected_objects`,
  `expected_inputs_sha256`, `teardown_from_sequence`, `owned_identity`, and
  `events`.
- `kil.v3b2-private-manifest.v1`: `schema_version`, `run_id`,
  `execution_nonce`, `source_commit`, `profile_sha256`, `tool_identities`,
  `content_identities`, `expected_topology`, `expected_policy_graph`,
  `request_cases`, `runtime_identities`, `source_attestations`,
  `foreign_profiles_before`, and `global_context_before`.
- `kil.v3b2-public-manifest.v1`: `schema_version`, `run_id`,
  `source_commit`, `profile_sha256`, `evidence_scope`, `result_class`,
  `promotion_status`, `content_identities`, `topology_attestation`,
  `policy_attestation`, `request_results`, `semantic_joins`,
  `source_attestations`, `foreign_profile_attestation`,
  `global_context_unchanged`, `owned_teardown`, `claim_exclusions`, and
  `public_commitment_sha256`.
- `kil.v3b2-campaign.v1`: `schema_version`, `source_commit`,
  `case_contract_sha256`, `cases`, `run_bundles`, `coverage`,
  `duplicate_case_ids`, `omitted_case_ids`, `promotion_status`,
  `claim_exclusions`, and `public_commitment_sha256`.

The V3B-2a verifier accepts the profile, journal, private-manifest, and
public-manifest schemas. It recognizes `kil.v3b2-campaign.v1` only to dispatch
to a closed `campaign_not_implemented` rejection; the V3B-2b plan replaces that
single rejection with the reviewed campaign validator. V3B-1 dispatch remains
unchanged and hybrid field sets are rejected.

## File map

- `deploy/kind/v3b2-profile.json` — exact V3B-2 profile and topology identity.
- `deploy/kind/calico-v3.32.0.yaml` — vendored digest-pinned Calico manifest.
- `deploy/kind/calico-v3.32.0.objects.json` — canonical safe-parsed projection
  of all 38 vendored YAML documents, bound to both source and projection digests.
- `src/kil/v3b2_contracts.py` — closed schemas, scalar validators, canonical
  profile loader, fixed tracks, and request-free/nominal case definitions.
- `tests/test_v3b2_contracts.py` — field closure, value closure, dispatch, and
  public/private boundary tests.
- `src/kil/v3b2_manifests.py` — deterministic Kind config and canonical JSON
  Kubernetes object renderer.
- `tests/test_v3b2_manifests.py` — static security and exact topology/policy
  tests.
- `src/kil/v3b2_inventory.py` — typed kubectl JSON decoding, UID/resourceVersion
  stability, endpoint closure, Calico readiness, and policy-graph comparison.
- `tests/test_v3b2_inventory.py` — closed inventory and ambiguity tests.
- `src/kil/v3b2_journal.py` — append-only journal, event grammar, typed command
  records, and journal-bound recovery authority.
- `tests/test_v3b2_journal.py` — crash-boundary, no-replay, exact-name teardown,
  and foreign-noninterference tests.
- `src/kil/v3b2_evidence.py` — bounded evidence capture, semantic joins, public
  projection, checksums, presenter, and offline verifier dispatch.
- `tests/test_v3b2_evidence.py` — canonicalization, replacement detection,
  tuple/join, redaction, checksums, and verifier tests.
- `src/kil/v3b2_controller.py` — request-free and nominal lifecycle state
  machine over injected command and filesystem interfaces.
- `tools/v3b2_kind_calico.py` — argument parsing and closed error presentation.
- `tests/test_v3b2_controller.py` — fake-runner command order, intent timing,
  recovery, collection, teardown, and publication tests.
- `tests/test_v3b2_documentation.py` — claim-boundary and operator-command
  documentation contract.
- `Makefile` — V3B-2 preflight, request-free, nominal, down, and view targets.
- `deploy/kind/README.md` and `tools/README.md` — operator boundary and command
  sequence.
- `docs/lab/V3-PROGRESS.md` — static, request-free, and nominal checkpoints
  without premature V3B-2b or V3C promotion.

### Task 1: Pin and validate the V3B-2 profile and Calico bytes

**Files:**

- Create: `deploy/kind/v3b2-profile.json`
- Create: `deploy/kind/calico-v3.32.0.yaml`
- Create: `src/kil/v3b2_contracts.py`
- Create: `tests/test_v3b2_contracts.py`

- [ ] **Step 1: Write the failing profile and schema tests**

```python
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from kil.v3b2_contracts import (
    APPLICATION_NAMESPACES,
    LAB_IDENTITY,
    PROFILE_FIELDS,
    SchemaError,
    V3B2Profile,
    dispatch_schema,
)

ROOT = Path(__file__).resolve().parents[1]


class V3B2ProfileTest(unittest.TestCase):
    def test_loads_only_the_kind_calico_profile(self):
        profile = V3B2Profile.load(ROOT / "deploy/kind/v3b2-profile.json")
        self.assertEqual(profile.schema_version, "kil.v3b2-profile.v1")
        self.assertEqual(profile.colima_profile, LAB_IDENTITY)
        self.assertEqual(profile.cluster_name, LAB_IDENTITY)
        self.assertEqual(profile.evidence_scope, "kind_calico_boundary")
        self.assertEqual(profile.application_namespaces, APPLICATION_NAMESPACES)
        self.assertEqual(
            profile.calico_manifest_sha256,
            "ac5ab7451dda57cfbf47d584ee901b896b1a9ff388d95b6f01b59f1e1130fdfa",
        )

    def test_profile_rejects_unknown_missing_and_cross_generation_fields(self):
        raw = json.loads((ROOT / "deploy/kind/v3b2-profile.json").read_text())
        self.assertEqual(set(raw), PROFILE_FIELDS)
        for mutation in (
            {**raw, "gateway_ports": [18080]},
            {key: value for key, value in raw.items() if key != "pod_subnet"},
            {**raw, "evidence_scope": "local_envoy_boundary"},
        ):
            with self.assertRaises(SchemaError):
                V3B2Profile.from_mapping(mutation)

    def test_profile_is_frozen(self):
        profile = V3B2Profile.load(ROOT / "deploy/kind/v3b2-profile.json")
        with self.assertRaises(FrozenInstanceError):
            profile.cluster_name = "foreign"  # type: ignore[misc]

    def test_campaign_dispatch_is_closed_until_v3b2b(self):
        with self.assertRaisesRegex(SchemaError, "campaign_not_implemented"):
            dispatch_schema({"schema_version": "kil.v3b2-campaign.v1"})
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_contracts -v
```

Expected: `ModuleNotFoundError: No module named 'kil.v3b2_contracts'`.

- [ ] **Step 3: Vendor and digest-pin Calico deterministically**

Fetch the exact approved URL to a newly created temporary directory, verify the
upstream checksum, replace only the three exact tag strings, then verify the
final checksum before moving the file into the repository:

```bash
tmp_dir="$(mktemp -d)"
curl --fail --location --proto '=https' --tlsv1.2 --max-filesize 10485760 \
  --output "$tmp_dir/calico.yaml" \
  https://raw.githubusercontent.com/projectcalico/calico/v3.32.0/manifests/calico.yaml
test "$(shasum -a 256 "$tmp_dir/calico.yaml" | awk '{print $1}')" = \
  bccabc607685551db918f66da724893eca3e69a50c5a3e3077029b02dbab8d35
cp "$tmp_dir/calico.yaml" deploy/kind/calico-v3.32.0.yaml
perl -pi -e 's#quay\.io/calico/cni:v3\.32\.0#quay.io/calico/cni\@sha256:1cfc6aa9c4dad3575fdf36b78185fd7d68bcd4acc95778f8342be4fb6a851a14#g; s#quay\.io/calico/node:v3\.32\.0#quay.io/calico/node\@sha256:f4fafd8ba641d96c5a91b01e5a519117d77d55dee789a3562ba3ad4aa125b36a#g; s#quay\.io/calico/kube-controllers:v3\.32\.0#quay.io/calico/kube-controllers\@sha256:adf0ac895796d21bca5383bc81c4cd2614be3a4308085b47857d7999f4cc2b1f#g' \
  deploy/kind/calico-v3.32.0.yaml
test "$(shasum -a 256 deploy/kind/calico-v3.32.0.yaml | awk '{print $1}')" = \
  ac5ab7451dda57cfbf47d584ee901b896b1a9ff388d95b6f01b59f1e1130fdfa
```

Remove the temporary directory after the two checksum assertions pass. Never
substitute a newer tag or registry result into this task.

- [ ] **Step 4: Add the closed profile document**

Create `deploy/kind/v3b2-profile.json` with these exact scalar and collection
values. `calico_images` is a closed object keyed by `cni`, `node`, and
`kube_controllers` using the digest references in the resolved table above.

```json
{
  "schema_version": "kil.v3b2-profile.v1",
  "host_os": "darwin",
  "host_arch": "arm64",
  "colima_version": "0.10.3",
  "colima_profile": "kil-v3-lab",
  "lima_version": "2.2.0",
  "docker_cli_version": "29.7.2",
  "kind_version": "0.32.0",
  "kubernetes_version": "1.36.1",
  "kind_node_image": "kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5",
  "kubectl_version": "1.36.3",
  "envoy_image": "docker.io/envoyproxy/envoy:v1.39.1",
  "calico_version": "3.32.0",
  "calico_upstream_url": "https://raw.githubusercontent.com/projectcalico/calico/v3.32.0/manifests/calico.yaml",
  "calico_upstream_sha256": "bccabc607685551db918f66da724893eca3e69a50c5a3e3077029b02dbab8d35",
  "calico_manifest_path": "deploy/kind/calico-v3.32.0.yaml",
  "calico_manifest_sha256": "ac5ab7451dda57cfbf47d584ee901b896b1a9ff388d95b6f01b59f1e1130fdfa",
  "calico_images": {
    "cni": "quay.io/calico/cni@sha256:1cfc6aa9c4dad3575fdf36b78185fd7d68bcd4acc95778f8342be4fb6a851a14",
    "node": "quay.io/calico/node@sha256:f4fafd8ba641d96c5a91b01e5a519117d77d55dee789a3562ba3ad4aa125b36a",
    "kube_controllers": "quay.io/calico/kube-controllers@sha256:adf0ac895796d21bca5383bc81c4cd2614be3a4308085b47857d7999f4cc2b1f"
  },
  "cluster_name": "kil-v3-lab",
  "pod_subnet": "10.244.0.0/16",
  "service_subnet": "10.96.0.0/16",
  "system_namespaces": ["default", "kube-node-lease", "kube-public", "kube-system", "local-path-storage"],
  "application_namespaces": ["kil-v3-baseline", "kil-v3-signed", "kil-v3-local-reduce"],
  "evidence_scope": "kind_calico_boundary"
}
```

- [ ] **Step 5: Implement exact profile and schema dispatch**

`v3b2_contracts.py` must expose frozen, slotted records and exact-key helpers.
Start the module with these exact public constants so later tasks do not invent
alternate names:

```python
LAB_IDENTITY = "kil-v3-lab"
TRACKS = ("credential_policy_baseline", "signed_state_only", "signed_plus_local_reduce")
APPLICATION_NAMESPACES = ("kil-v3-baseline", "kil-v3-signed", "kil-v3-local-reduce")
TRACK_NAMESPACES = tuple(zip(TRACKS, APPLICATION_NAMESPACES, strict=True))
NOMINAL_REQUEST_ID = "v3b1-central-request"
PROFILE_SCHEMA = "kil.v3b2-profile.v1"
JOURNAL_SCHEMA = "kil.v3b2-journal.v1"
PRIVATE_MANIFEST_SCHEMA = "kil.v3b2-private-manifest.v1"
PUBLIC_MANIFEST_SCHEMA = "kil.v3b2-public-manifest.v1"
CAMPAIGN_SCHEMA = "kil.v3b2-campaign.v1"


class SchemaError(ValueError):
    pass
```

Define `PROFILE_FIELDS`, `JOURNAL_FIELDS`, `PRIVATE_MANIFEST_FIELDS`,
`PUBLIC_MANIFEST_FIELDS`, and `CAMPAIGN_FIELDS` as frozensets copied exactly
from the Closed schema inventory, then expose `SCHEMA_FIELDS` as an immutable
mapping from each schema constant to its field frozenset.

Define `V3B2Profile` with one field for every profile key in the closed schema
inventory, converting JSON objects and arrays to sorted or fixed-order tuples.
Its `load(Path)` method reads at most 64 KiB with no-follow file checks and a
duplicate-key-rejecting JSON decoder, then calls `from_mapping()`. The mapping
constructor calls `require_closed_object(label, value, PROFILE_FIELDS)` before
validating values. `dispatch_schema()` reads only `schema_version`, dispatches
the four V3B-2a schemas to their exact validators, returns V3B-1 values to the
existing V3B-1 verifier, and raises `SchemaError("campaign_not_implemented")`
for the campaign schema.

Reject duplicate JSON keys, booleans as integers, noncanonical CIDRs, mutable
image references, symlinks, absolute or escaping manifest paths, reordered
namespace lists, foreign lab names, and any field set not exactly equal to the
declared constant.

- [ ] **Step 6: Verify GREEN and commit**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_contracts -v
git diff --check
git add deploy/kind/v3b2-profile.json deploy/kind/calico-v3.32.0.yaml \
  src/kil/v3b2_contracts.py tests/test_v3b2_contracts.py
git commit -m "feat: pin V3B-2 profile and Calico content"
```

Expected: focused tests pass; the commit contains no generated runtime state.

### Task 2: Render the exact Kind and application object set

**Files:**

- Create: `src/kil/v3b2_manifests.py`
- Create: `tests/test_v3b2_manifests.py`

- [ ] **Step 1: Write failing deterministic-render and security tests**

```python
import json
import unittest

from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_manifests import expected_policy_graph, render_kind_config, render_objects


class V3B2ManifestTest(unittest.TestCase):
    def test_kind_disables_default_cni_and_fixes_subnets(self):
        config = render_kind_config(self.profile)
        self.assertIn("disableDefaultCNI: true", config)
        self.assertIn("podSubnet: 10.244.0.0/16", config)
        self.assertIn("serviceSubnet: 10.96.0.0/16", config)
        self.assertNotIn("extraPortMappings", config)

    def test_application_object_set_is_exact_and_canonical(self):
        first = render_objects(self.profile, self.workload)
        second = render_objects(self.profile, self.workload)
        self.assertEqual(first, second)
        objects = json.loads(first)
        self.assertEqual(objects["apiVersion"], "v1")
        self.assertEqual(objects["kind"], "List")
        self.assertEqual(len(objects["items"]), 60)

    def test_every_namespace_is_default_deny_before_workloads(self):
        objects = json.loads(render_objects(self.profile, self.workload))["items"]
        for namespace in self.profile.application_namespaces:
            policies = [item for item in objects if item["kind"] == "NetworkPolicy" and item["metadata"]["namespace"] == namespace]
            self.assertEqual({item["metadata"]["name"] for item in policies}, {"default-deny", "allow-dns", "allow-driver-egress-envoy", "allow-envoy-ingress-egress", "allow-backends-ingress-envoy"})

    def test_pods_are_nonroot_bounded_and_have_no_host_escape(self):
        for pod_template in self.workload_templates:
            spec = pod_template["spec"]
            self.assertNotIn("hostNetwork", spec)
            self.assertNotIn("hostPID", spec)
            for container in spec["containers"]:
                security = container["securityContext"]
                self.assertTrue(security["runAsNonRoot"])
                self.assertFalse(security["allowPrivilegeEscalation"])
                self.assertEqual(security["capabilities"]["drop"], ["ALL"])
                self.assertIn("requests", container["resources"])
                self.assertIn("limits", container["resources"])
```

Define `self.profile`, `self.workload`, and `self.workload_templates` in
`setUp()` by loading the fixed profile, using a syntactically valid synthetic
V3B-2 run ID, immutable synthetic KIL image ID and Envoy digest, and selecting
each Deployment/Pod template from the rendered list.

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_manifests -v
```

Expected: import failure because `kil.v3b2_manifests` does not exist.

- [ ] **Step 3: Implement canonical renderers and fixed object names**

Define this input record and expose only `render_kind_config(profile)`,
`render_objects(profile, workload)`, `expected_object_keys(profile)`, and
`expected_policy_graph(profile)` as public construction functions:

```python
@dataclass(frozen=True, slots=True)
class WorkloadIdentity:
    run_id: str
    kil_image_id: str
    envoy_image_digest: str
```

The 60 application objects are exactly 3 Namespaces, 12 ServiceAccounts, 9
ConfigMaps, 9 Services, 9 Deployments, 3 waiting driver Pods, and 15
NetworkPolicies. Driver Pods start without an instruction and become ready
after emitting the V3B-1 canonical readiness record. Services are ClusterIP
only. ConfigMaps contain only canonical public JSON and Envoy configuration;
Secrets are absent. Each fixed-track namespace uses labels
`kil.dev/managed=v3b2` and `kil.dev/track` equal to its literal member of
`TRACKS`.

`WorkloadIdentity` accepts a `v3b2-` plus 64-lowercase-hex run ID, a
`sha256:` plus 64-lowercase-hex KIL image ID, and an Envoy repository digest.
The renderer derives the KIL Pod reference by concatenating
`kil.local/kil-v3b2:sha256-` with the image ID's 64 lowercase hexadecimal
characters and fixes
`imagePullPolicy: Never`; the controller must import that exact content and
later attest the realized `imageID`. The target ConfigMap binds `run_id`.
Authorization ConfigMaps reuse the reviewed fixed-track V3B-1 public keys and
fixture shape; signed state remains in the one-shot private driver instruction,
not a ConfigMap. Envoy ConfigMaps are rendered through `kil.v3b_envoy` using the
same-namespace `authz` and `target` Service DNS names.

The five policies per namespace are grouped by the workloads they select so
Kubernetes' additive ingress/egress semantics do not broaden an edge:

1. `default-deny` uses the standard empty `podSelector: {}` with both policy
   types and no allow rules, isolating every current or unexpected Pod in the
   namespace.
2. `allow-dns` selects only same-track driver and Envoy roles for egress to the
   exact `kube-system` / `k8s-app=kube-dns` peer on UDP and TCP 53.
3. `allow-driver-egress-envoy` selects only the driver and permits egress to the
   exact same-track Envoy on TCP 8080.
4. `allow-envoy-ingress-egress` selects only Envoy and permits ingress from the
   exact same-track driver plus egress to the exact same-track authz and target
   roles on TCP 8080.
5. `allow-backends-ingress-envoy` selects same-track authz and target roles and
   permits ingress only from the exact same-track Envoy on TCP 8080.

In each peer, `namespaceSelector` and `podSelector` occupy the same `from` or
`to` item, making them an AND rather than two OR alternatives. Every allow rule
includes the exact namespace track and Pod role labels. No allow policy may use
an empty selector. No IPBlock, SCTP, UDP application edge, or cross-track
selector is permitted.

- [ ] **Step 4: Add adversarial manifest tests**

Mutate one field at a time and assert rejection by `validate_rendered_objects`:

```python
for mutation, reason in (
    (("Service", "spec.type", "NodePort"), "ClusterIP"),
    (("Deployment", "spec.template.spec.hostNetwork", True), "hostNetwork"),
    (("Deployment", "spec.template.spec.containers.0.securityContext.privileged", True), "privileged"),
    (("NetworkPolicy/allow-driver-egress-envoy", "spec.podSelector", {}), "selector"),
):
    with self.subTest(reason=reason):
        with self.assertRaisesRegex(ManifestError, reason):
            validate_rendered_objects(mutated_objects(mutation), self.profile, self.workload)
```

- [ ] **Step 5: Verify GREEN and commit**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_manifests -v
git diff --check
git add src/kil/v3b2_manifests.py tests/test_v3b2_manifests.py
git commit -m "feat: render closed Kind Calico topology"
```

### Task 3: Validate Kubernetes, Calico, endpoint, and policy inventory

**Files:**

- Create: `src/kil/v3b2_inventory.py`
- Create: `tests/test_v3b2_inventory.py`

- [ ] **Step 1: Write failing inventory closure tests**

```python
class V3B2InventoryTest(unittest.TestCase):
    def test_accepts_exact_ready_inventory_and_cluster_binding(self):
        result = validate_inventory(self.snapshot, self.expected)
        self.assertEqual(result.cluster_incarnation_uid, KUBE_SYSTEM_UID)
        self.assertEqual(result.policy_graph, self.expected.policy_graph)

    def test_rejects_extra_namespace_workload_service_or_policy(self):
        for mutated in (
            add_namespace(self.snapshot, "foreign-in-cluster"),
            add_deployment(self.snapshot, "kil-v3-baseline", "extra"),
            add_service(self.snapshot, "kil-v3-signed", "public", "NodePort"),
            add_policy_edge(self.snapshot, "kil-v3-local-reduce", "driver", "target"),
        ):
            with self.assertRaises(InventoryError):
                validate_inventory(mutated, self.expected)

    def test_rejects_uid_resourceversion_or_image_identity_drift(self):
        for field in ("uid", "resourceVersion", "imageID"):
            with self.assertRaises(InventoryError):
                stable_source(self.before, replace_field(self.after, field))

    def test_rejects_unready_calico_or_unknown_system_namespace(self):
        with self.assertRaisesRegex(InventoryError, "Calico"):
            validate_inventory(mark_calico_unready(self.snapshot), self.expected)
        with self.assertRaisesRegex(InventoryError, "namespace"):
            validate_inventory(add_namespace(self.snapshot, "mystery-system"), self.expected)
```

- [ ] **Step 2: Verify RED**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_inventory -v
```

Expected: import failure for `kil.v3b2_inventory`.

- [ ] **Step 3: Implement strict typed snapshots**

Define frozen, slotted `ObjectIdentity`, `PodImageIdentity`,
`EndpointIdentity`, `PolicyEdge`, `InventorySnapshot`, `ExpectedInventory`, and
`InventoryAttestation` records. `ObjectIdentity` contains `api_version`, `kind`,
`namespace`, `name`, `uid`, and `resource_version`. `InventoryAttestation`
contains `cluster_incarnation_uid`, `node_container_id`, the four sorted record
tuples, and `calico_ready`.

Expose `parse_kubectl_list(payload, expected_kind)`,
`validate_inventory(snapshot, expected)`, and `stable_source(before, after)`.
The parser accepts at most 8 MiB, requires an exact Kubernetes List envelope,
and sorts items by `(apiVersion, kind, namespace, name)` before constructing
records. The validator compares those tuples directly with the expected
inventory and constructs the attestation only after all equality checks pass.

All JSON decoders must reject duplicate keys, non-objects, missing or extra
fields at every consumed level, list duplicates, unknown conditions, ambiguous
Endpoints/EndpointSlices, mutable-only image identity, and response bodies over
8 MiB. `kube-system` namespace UID is the cluster-incarnation binding. The Kind
node container full ID is supplied through an explicit Docker host bound to
`kil-v3-lab`, never the global Docker context.

- [ ] **Step 4: Prove the policy graph, not only policy names**

Add fixtures for all 12 allowed application edges including three DNS edges,
then assert that port, protocol, selector, namespace, or direction changes are
rejected. Also assert that Calico DaemonSet ready count equals desired count and
the kube-controllers Deployment has exactly one ready replica with the pinned
image references.

- [ ] **Step 5: Verify GREEN and commit**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_inventory -v
git diff --check
git add src/kil/v3b2_inventory.py tests/test_v3b2_inventory.py
git commit -m "feat: attest closed Kubernetes and Calico inventory"
```

### Task 4: Implement journal-bound commands, intent ordering, and recovery

**Files:**

- Create: `src/kil/v3b2_journal.py`
- Create: `tests/test_v3b2_journal.py`

- [ ] **Step 1: Write failing event-grammar and command-authority tests**

```python
class V3B2JournalTest(unittest.TestCase):
    def test_journal_exists_before_first_owned_mutation(self):
        journal = create_journal(self.path, self.inputs)
        self.assertTrue(self.path.exists())
        self.assertEqual(journal["events"], [])

    def test_every_colima_mutation_names_only_kil_profile(self):
        for command in owned_commands(self.identities):
            if command.argv[0] == "colima" and command.mutating:
                self.assertIn(("--profile", "kil-v3-lab"), adjacent_pairs(command.argv))
                self.assertNotIn("default", command.argv)

    def test_kind_delete_uses_exact_name_and_explicit_kubeconfig(self):
        command = kind_delete_command(self.identities)
        self.assertEqual(command.argv[0:4], ("kind", "delete", "cluster", "--name"))
        self.assertEqual(command.argv[4], "kil-v3-lab")
        self.assertNotIn("current-context", command.argv)

    def test_request_intent_is_terminal_and_never_replayed(self):
        claimed = append_event(self.path, "request_intent", self.request)
        with self.assertRaisesRegex(JournalError, "already claimed"):
            append_event(self.path, "request_intent", self.request)
        self.assertEqual(recovery_plan(claimed).requests_to_send, ())

    def test_foreign_profiles_never_appear_in_mutation_commands(self):
        plan = recovery_plan(self.journal_with_foreign_profiles)
        mutation_text = "\n".join(" ".join(command.argv) for command in plan.commands)
        self.assertNotIn("client-project", mutation_text)
```

- [ ] **Step 2: Verify RED**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_journal -v
```

Expected: import failure for `kil.v3b2_journal`.

- [ ] **Step 3: Implement the typed command boundary**

```python
@dataclass(frozen=True, slots=True)
class Command:
    argv: tuple[str, ...]
    timeout_s: int
    stdin: bytes | None = None
    env: tuple[tuple[str, str], ...] = ()
    mutating: bool = False


@dataclass(frozen=True, slots=True)
class OwnedIdentity:
    colima_profile: str
    docker_host: str | None
    kind_cluster: str | None
    kubeconfig: str | None
    cluster_incarnation_uid: str | None
    node_container_id: str | None


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    commands: tuple[Command, ...]
    requests_to_send: tuple[Command, ...] = ()
    publication_allowed: bool = False
```

Add a frozen `JournalInputs` record containing every non-event journal field.
Implement `create_journal(path, inputs)` with exclusive creation and durable
fsync; `load_journal(path)` with no-follow bounded canonical decoding and
event-grammar validation; `append_event(path, event, details)` with transition
validation before atomic replacement; and `recovery_plan(journal)` by deriving
commands only from `owned_identity` and completed journal events.

Writes use a contained private root, mode 0600, canonical JSON, fsync of the
file and parent directory, and atomic replacement. Each mutation has an
`*_intent` before execution and `*_complete` after postcondition attestation.
An `*_failed` event may close an intent only when an exact bound observation
proves the mutation did not occur. For an uncertain or partial non-request
mutation after exact ownership is established, an
`*_abandoned_for_teardown` event may only enter the permanently nonpromotable
diagnostic-freeze and exact-teardown path; it never claims completion or permits
forward work. Ambiguous ownership remains manual recovery, and request intent
continues to use the nonreplayable stranded-request freeze path.
The event grammar covers profile start/stop/delete, cluster create/delete,
image import/load, Calico apply, application apply, readiness, driver
start/cancel, Envoy quiescence, evidence
freeze, request intent/result, absence proofs, foreign snapshot comparison, and
publication.

Every Docker and Kind command carries the journal-bound `DOCKER_HOST` and an
isolated `DOCKER_CONFIG` through `Command.env`; neither value may be inherited
from the shell. Every kubectl command includes the journal-bound kubeconfig as
an argv flag. Tests must reject missing, duplicated, or overridden bindings.

- [ ] **Step 4: Enumerate crash boundaries and exact recovery outcomes**

Use a table-driven test over every intent/complete pair. Before an intent,
recovery may open a fresh lifecycle. After a mutation intent, recovery may only
attest or finish that exact journal-bound mutation. After request intent,
recovery cancels unopened drivers and freezes evidence but returns no send
command. A UID, node ID, cluster-incarnation UID, or Docker endpoint mismatch
must yield `manual_recovery_required` and must not delete anything.

- [ ] **Step 5: Verify GREEN and commit**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_journal -v
git diff --check
git add src/kil/v3b2_journal.py tests/test_v3b2_journal.py
git commit -m "feat: add V3B-2 journal-bound recovery"
```

### Task 5: Build bounded evidence, semantic joins, and offline verification

**Files:**

- Create: `src/kil/v3b2_evidence.py`
- Create: `tests/test_v3b2_evidence.py`

- [ ] **Step 1: Write failing evidence and public-boundary tests**

```python
class V3B2EvidenceTest(unittest.TestCase):
    def test_nominal_tuple_and_target_cardinality_are_exact(self):
        bundle = build_public_bundle(self.complete_private_evidence)
        self.assertEqual(
            tuple((item["decision"], item["http_status"], item["target_markers"]) for item in bundle["request_results"]),
            (("permit", 200, 1), ("permit", 200, 1), ("deny", 403, 0)),
        )

    def test_permit_and_denial_joins_are_rederived(self):
        joins = join_nominal_evidence(self.complete_private_evidence)
        self.assertEqual(len(joins), 3)
        self.assertTrue(all(join["decision_digest_equal"] for join in joins))
        self.assertFalse(joins[2]["envoy_upstream_attempted"])

    def test_request_free_bundle_is_diagnostic_and_contains_no_requests(self):
        bundle = build_public_bundle(self.request_free_private_evidence)
        self.assertEqual(bundle["result_class"], "diagnostic_request_free_kind_calico_readiness")
        self.assertEqual(bundle["promotion_status"], "not_promoted")
        self.assertEqual(bundle["request_results"], [])
        self.assertEqual(bundle["semantic_joins"], [])

    def test_public_projection_rejects_private_material_recursively(self):
        for value in ("/Users/name", "Bearer secret", "kil-private-nonce", "foreign-profile-name"):
            with self.assertRaises(PublicBoundaryError):
                validate_public_projection(inject_nested(self.public_manifest, value))

    def test_v3b1_and_v3b2_dispatch_are_independent(self):
        self.assertEqual(verify_bundle(self.v3b1_fixture).schema_family, "v3b1")
        self.assertEqual(verify_bundle(self.v3b2_fixture).schema_family, "v3b2-run")
        with self.assertRaises(EvidenceError):
            verify_bundle(hybridize(self.v3b2_fixture, self.v3b1_fixture))
```

- [ ] **Step 2: Verify RED**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_evidence -v
```

Expected: import failure for `kil.v3b2_evidence`.

- [ ] **Step 3: Implement stable bounded source capture**

```python
@dataclass(frozen=True, slots=True)
class SourceIdentity:
    logical_name: str
    object_uid: str
    resource_version: str
    container_id: str
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class CapturedSource:
    identity: SourceIdentity
    payload: bytes


```

Expose `capture_source(reader, expected, maximum=8 * 1024 * 1024)`,
`join_nominal_evidence(private)`, `build_public_bundle(private)`, and
`verify_bundle(path)`. `SourceReader` is a protocol returning identity-before,
bounded bytes, and identity-after. `VerifiedBundle` is a frozen record of
schema family, run ID, result class, promotion status, and public commitment.
Each implementation follows the exact capture, join, file-set, and verification
rules in Steps 3–5 rather than delegating semantic acceptance to checksums.

Capture reads object identity before and after bounded bytes, rejects identity
drift and duplicate or partial JSONL, and persists raw malformed bytes only in
the private area with a hash-bound diagnostic. The public bundle contains
`manifest.json`, `requests.jsonl`, `decisions.jsonl`, `envoy.jsonl`,
`targets.jsonl`, `kubernetes.jsonl`, `policies.jsonl`, `joins.jsonl`,
`summary.md`, `live.html`, and `SHA256SUMS`—each exactly once.

- [ ] **Step 4: Enforce V3B-2a claim language and foreign pseudonyms**

The complete result uses exactly:

```python
RESULT_CLASS = "intermediate_provisional_kind_calico_nominal"
REQUEST_FREE_RESULT_CLASS = "diagnostic_request_free_kind_calico_readiness"
PROMOTION_STATUS = "not_promoted"
CLAIM_EXCLUSIONS = (
    "complete_v3b2_validation",
    "complete_networkpolicy_validation",
    "repeated_reliability",
    "performance",
    "production_validation",
    "historical_prevention",
)
```

Foreign profiles are projected as sorted HMAC-SHA256 pseudonyms keyed by a
run-private projection key; the key and original names never enter the public
bundle. Before/after equality includes status and normalized resource fields.
Mismatch publishes only closed categories and forces a nonpromotable failure.

- [ ] **Step 5: Add checksum, atomic publication, and replacement tests**

Test missing, extra, symlinked, replaced-after-validation, duplicate-checksum,
wrong-order JSONL, malformed UTF-8, oversized, and repaired-hash semantic drift.
Publication must create a private sibling directory, fsync every file and the
directory, reverify semantics, atomically rename once, and re-attest the public
tree before journal completion.

- [ ] **Step 6: Verify GREEN and commit**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_evidence -v
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b1_local_envoy -v
git diff --check
git add src/kil/v3b2_evidence.py tests/test_v3b2_evidence.py
git commit -m "feat: verify V3B-2 nominal evidence bundles"
```

### Task 6: Compose the request-free and nominal controller

**Files:**

- Create: `src/kil/v3b2_controller.py`
- Create: `tools/v3b2_kind_calico.py`
- Create: `tests/test_v3b2_controller.py`

- [ ] **Step 1: Write failing preflight and foreign-snapshot tests**

```python
class V3B2ControllerTest(unittest.TestCase):
    def test_preflight_precedes_every_mutation_and_allows_foreign_profiles(self):
        controller = controller_with(
            profiles=[foreign("client-a", "Running"), foreign("client-b", "Stopped")]
        )
        result = controller.preflight()
        self.assertEqual(result["owned_profile"], "absent")
        self.assertEqual(self.runner.mutations, [])
        self.assertTrue(controller.journal_path.exists())

    def test_preflight_rejects_owned_presence_and_ambiguous_inventory(self):
        for profiles in ([foreign("kil-v3-lab", "Running")], duplicate_foreign_names()):
            with self.assertRaises(ControllerError):
                controller_with(profiles=profiles).preflight()

    def test_global_docker_context_is_read_only(self):
        controller_with(profiles=[]).preflight()
        self.assertFalse(any(command.argv[:2] == ("docker", "context") and command.mutating for command in self.runner.commands))
```

- [ ] **Step 2: Write failing request-free and nominal order tests**

```python
def test_request_free_sends_no_attach_stdin_or_http(self):
    result = self.controller.request_free()
    self.assertEqual(result["instructions_sent"], 0)
    self.assertFalse(any(command.stdin is not None for command in self.runner.commands))
    self.assertEqual(self.fake_sources.total_application_records, 0)


def test_nominal_persists_intent_before_each_single_attach(self):
    bundle = self.controller.nominal()
    self.assertEqual(self.runner.attach_count, 3)
    for track in TRACKS:
        request_key = (track, NOMINAL_REQUEST_ID)
        self.assertLess(self.journal.sequence("request_intent", request_key), self.runner.sequence("kubectl_attach", request_key))
        self.assertEqual(self.runner.attach_count_for(request_key), 1)
    self.assertEqual(bundle.result_tuple, (("permit", 200, 1), ("permit", 200, 1), ("deny", 403, 0)))


def test_post_intent_failure_cancels_later_drivers_and_never_retries(self):
    first = (TRACKS[0], NOMINAL_REQUEST_ID)
    second = (TRACKS[1], NOMINAL_REQUEST_ID)
    third = (TRACKS[2], NOMINAL_REQUEST_ID)
    self.runner.fail_after_send(first)
    with self.assertRaises(ControllerError):
        self.controller.nominal()
    self.assertEqual(self.runner.attach_count_for(first), 1)
    self.assertEqual(self.runner.attach_count_for(second), 0)
    self.assertEqual(self.runner.attach_count_for(third), 0)
    self.assertTrue(self.controller.owned_absence_proven)
```

- [ ] **Step 3: Verify RED**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_controller -v
```

Expected: import failure for `kil.v3b2_controller`.

- [ ] **Step 4: Implement injected execution and the exact phase machine**

Define `CommandRunner` as a protocol with `run(Command) -> CommandResult` and a
frozen, slotted `ControllerPaths` containing `repository`, `profile`, `tools`,
`private`, and `public` paths. Define `V3B2Controller(paths, runner)` with
`preflight()`, `up()`, `request_free()`, `nominal()`, `down()`, and `recover()`.
Only `SubprocessCommandRunner` may invoke processes; controller methods build
`Command` values from profile constants and journal-bound identities.

`up()` starts only `colima start --profile kil-v3-lab`, derives the explicit
profile Docker socket without changing global context, and creates only the
`kil-v3-lab` cluster using the journal's literal Kind-config path, pinned node
digest, and literal kubeconfig path. It installs the checksum-verified Calico
file, waits for the closed system inventory, applies NetworkPolicies before
workloads, then records all UIDs and runtime image IDs.

Before any runtime mutation, preflight requires the fixed
`.tools/v3b2-input/kil-image.tar` input and verifies its checksum against the
accepted V3B-1 manifest. The controller does not search other worktrees or
Docker daemons for content. An `image_import` intent binds the archive digest,
content-derived KIL tag, and exact Envoy repository digest. Through only the
owned profile's explicit Docker socket and private configuration, it loads
and tags the accepted KIL content, pulls the pinned Envoy content, and inspects
both identities before completing import. The separate `image_load` step loads
both images into only `kil-v3-lab` before `Never`-pull workloads are started.
An image-import failure cannot authorize workload startup or promotion.

`request_free()` creates fresh waiting drivers, captures readiness, sends no
instruction bytes, cancels them, freezes empty ledgers, deletes the exact cluster, verifies
absence, stops/deletes only `kil-v3-lab`, compares foreign state and global
context, then publishes a request-free diagnostic bundle.

`nominal()` refuses request-free mode or a reused lifecycle, requires a
different fresh run ID, performs aggregate readiness, and sends one instruction
per track through `kubectl attach` using the journal's literal kubeconfig,
namespace, and Pod name. It freezes evidence, proves the nominal tuple and
joins, tears down, then publishes.

- [ ] **Step 5: Prove teardown order and identity checks**

The fake runner must assert this order:

```text
cancel unopened drivers
quiesce all three Envoys
freeze driver, decision, Envoy, target, Kubernetes, and policy sources
reattest source UIDs/resourceVersions/container IDs
kind delete cluster --name kil-v3-lab using the journal-bound kubeconfig
prove cluster and node container absent through the bound Docker host
colima stop --profile kil-v3-lab
colima delete --profile kil-v3-lab --force --data
prove owned profile and private active-state paths absent
capture and compare foreign profiles and global Docker context
atomically publish
```

Test every boundary with the command succeeding but completion persistence
failing. Recovery may finish the exact action or attest its postcondition; it
may not issue a driver instruction or select a resource from discovery.

Cancellation and quiescence must leave driver and Envoy evidence readable
until freeze completes; deleting Pods or scaling away their containers is not
a source-preserving implementation. Any separate control command is fixed,
journal-bound, and incapable of carrying a consequential instruction. Read the
authorization and target files under `/evidence/` through a bounded fixed
source-read boundary, not their process stdout. Bind capture to freshly
observed Pod resource versions with stable before/after UID and container
incarnation checks. Raw Kubernetes responses are bounded and duplicate-safe
decoded before constructing canonical closed projections; live defaults and
terminal driver state must be represented in integration fixtures.

Apply service workloads before driver Pods. TCP readiness probes on Envoy,
authorization, and target port 8080 plus matching ready endpoints establish
listener readiness before a driver performs its single TCP connection; the
driver itself is never changed to reconnect or retry. EOF-only cancellation
uses a separately classified empty-stdin control attach and verifies successful
termination of the same Pod/container while retaining its logs. Envoy uses a
V3B-2-only loopback admin listener on port 9901 and a fixed identity-bound drain
command; completion requires listener refusal and zero relevant active gauges,
not merely an HTTP 200 response. It retains its process and Pod through freeze.
There is no admin Service or host exposure. Keep admin logs disabled and route
Envoy operational diagnostics to `/tmp/envoy.log`, separate from access stdout.

- [ ] **Step 6: Implement a thin fixed CLI**

```python
def make_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "up", "request-free", "nominal", "down", "recover"):
        subparsers.add_parser(name)
    view = subparsers.add_parser("view")
    view.add_argument("--bundle", required=True, type=Path)
    return parser
```

No CLI flag may accept a profile, cluster, namespace, kubeconfig, command
fragment, image, manifest, policy, case, or output class. Errors print one
closed stage code and never raw stderr, host paths, credentials, signed state,
or foreign names.

- [ ] **Step 7: Verify GREEN and commit**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_controller -v
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b1_request_driver tests.test_v3b1_local_envoy -v
git diff --check
git add src/kil/v3b2_controller.py tools/v3b2_kind_calico.py tests/test_v3b2_controller.py
git commit -m "feat: orchestrate V3B-2a Kind Calico lifecycle"
```

### Task 6 corrective pass: Shared observed-proof boundary

The 2026-09-07 independent review rejected the 753-test checkpoint. These
steps are required before Task 6 acceptance, not a new live phase. The root
cause is that normal execution and recovery have separate completion paths
which can substitute command status or unrelated observations for an operation's
postcondition. A second interface gap lets synthetic reduced source records
stand in for the actual producer schemas. Preserve the completed content-import,
source-preserving control, and publication work while replacing these gaps.

**Files:**

- Create: `src/kil/v3b2_proofs.py` and `tests/test_v3b2_proofs.py` for the shared
  immutable expected context, operation-specific observation validators, and
  typed proof decisions.
- Modify: `src/kil/v3b2_controller.py` and `src/kil/v3b2_journal.py` to route
  normal execution and recovery through that single proof boundary.
- Modify: `src/kil/v3b2_inventory.py` and `tests/test_v3b2_inventory.py` for
  independently derived expectations and the complete pinned platform inventory.
- Modify: `src/kil/v3b2_contracts.py`, `src/kil/v3b2_evidence.py`,
  `tests/test_v3b2_contracts.py`, and `tests/test_v3b2_evidence.py` for durable
  raw capture bindings and closed real-producer adapters.
- Modify: `tests/test_v3b2_controller.py` and `tests/test_v3b2_journal.py` for
  real-format observations, poisoned observations, and crash recovery.
- Create: `tests/test_v3b2_observed_lifecycle.py` for focused integration tests
  of immutable inputs, terminal-writer enforcement, and normal/recovery parity.
- Create: `src/kil/v3b2_profile_state.py` and
  `tests/test_v3b2_profile_state.py` for exact host-profile paths, closed saved
  configuration decoding, no-follow resource bindings, and deletion checks.
- Create: `src/kil/v3b2_api_defaults.py` and
  `tests/test_v3b2_api_defaults.py` for pure root-kind/exact-path Kubernetes
  default normalization, separate from inventory ownership and controller
  sequencing. Integrate that bounded contract before completing the finite
  generated-resource owner joins; normalization alone must not enable readiness.
- Create: `src/kil/v3b2_colima_inventory.py` and
  `tests/test_v3b2_colima_inventory.py` for one closed pinned Colima inventory
  decoder shared by controller, proofs, and private evidence validation.
- Create: `src/kil/v3b2_service_bindings.py` and
  `tests/test_v3b2_service_bindings.py` for the next bounded dynamic allocation
  contract: independently expected KIL Services, validated IPv4 allocation and
  immutable UID/address bindings. Keep static normalization and later generated
  owner/Pod admission contracts separate; this module alone cannot open readiness.
- Create: `src/kil/v3b2_bootstrap_inventory.py` and
  `tests/test_v3b2_bootstrap_inventory.py` for exact Namespace, platform
  ServiceAccount/ConfigMap identities, cardinality, incarnation and continuity.
  Platform ConfigMap content remains an explicitly unvalidated current digest in
  this module; bootstrap identities alone cannot open readiness.
- Create: `src/kil/v3b2_source_rendered_configmaps.py` and
  `tests/test_v3b2_source_rendered_configmaps.py` for the exact source-rendered
  CoreDNS and Kind local-path ConfigMaps, including client-side-apply annotation
  semantics. Keep CA/JWS and typed kubeadm/kubelet/kube-proxy relations in later
  focused validators, and keep generated ReplicaSet/Pod/EndpointSlice ownership
  and actual Pod admission separate.
- Create: `src/kil/v3b2_trust_configmaps.py` and
  `tests/test_v3b2_trust_configmaps.py` for the eight namespace root-CA
  publishers, extension-apiserver cluster/front-proxy trust roles and legacy
  token-tracking creation-era date. Keep `cluster-info` kubeconfig/JWS lifecycle
  and typed component documents separate; this trust proof cannot open readiness.
- Create: `src/kil/v3b2_cluster_info.py` and
  `tests/test_v3b2_cluster_info.py` for the closed internal kubeconfig, exact
  detached HS256 token signature and active-to-expired signer reconciliation
  transition. Token Secret shape/usage capture remains a separate private input;
  this proof alone cannot open readiness.
- Create: `src/kil/v3b2_closed_yaml.py` and
  `tests/test_v3b2_closed_yaml.py` as the dependency-free decoder for the
  deterministic kubeadm/component YAML subset. Bound bytes, lines, depth,
  semantic nodes, scalar bytes and integer conversion work before allocation;
  reject general YAML graph/type/block syntax and ambiguous YAML 1.1 scalars.
  This syntax layer returns exact built-in values and proves no component
  semantics or runtime readiness by itself.
- Create: `src/kil/v3b2_component_configmaps.py` and
  `tests/test_v3b2_component_configmaps.py` for the source-closed uploaded
  `kubeadm-config` and generic `kubelet-config` semantics. Compare the decoded
  observations to immutable generated/defaulted expected inputs, independently
  bind the pinned cluster/version/network/DNS relations and rootful-provider
  selection, and keep node-local CRI patching and kube-proxy credentials outside
  this proof. Retain only identity and raw/semantic commitments; readiness stays
  closed.
- Create: `src/kil/v3b2_kube_proxy_configmap.py` and
  `tests/test_v3b2_kube_proxy_configmap.py` for the remaining typed platform
  ConfigMap. Bind the generated/defaulted iptables configuration and the exact
  source-rendered one-cluster/context/user kubeconfig to the internal endpoint;
  require the service-account CA/token file references and reject every embedded
  credential or alternate authentication mechanism. Retain digest-only evidence
  and keep Pod volume/service-account admission as a later relation.
- Create: `src/kil/v3b2_deployment_ownership.py` and
  `tests/test_v3b2_deployment_ownership.py` for the fresh generated Deployment
  families. Derive the 12 exact Deployment identities and replica counts, then
  bind each sole revision-1 ReplicaSet and its 13 total Pods by namespace,
  controller UID, template hash and generated name. Cardinality fails before
  record traversal; this relation alone does not prove Pod readiness or images.
- Create: `src/kil/v3b2_node_ownership.py` and
  `tests/test_v3b2_node_ownership.py` for the two single-node DaemonSet Pods and
  four control-plane mirror Pods. Bind DaemonSet controller UIDs and the exact
  Node incarnation UID, component/source fields and equal config/mirror hashes;
  retain the Node-owner UID in every static binding so reconstructed proofs
  cannot substitute a different Node incarnation. Readiness and images remain
  separate.
- Create: `src/kil/v3b2_kil_endpoint_ownership.py` and
  `tests/test_v3b2_kil_endpoint_ownership.py` for the nine KIL Service target
  relations. Revalidate the accepted Service-allocation and Deployment-owner
  proofs, then bind each ready single-stack Pod IP to the exact controller-made
  EndpointSlice owner UID, manager, resolved port, address, target UID and
  node. Treat generated names as supplemental namespace-scoped evidence and
  keep platform Services, full Pod admission/CNI and image identity separate.
- Create: `src/kil/v3b2_platform_endpoints.py` and
  `tests/test_v3b2_platform_endpoints.py` for the source-distinct Kubernetes
  and kube-dns Service/Endpoints/EndpointSlice relations. Bind the special
  API-server-owned fixed-name endpoint to the sole Node InternalIP and bind the
  selector-managed DNS endpoints to the two role-preserved CoreDNS Pods. Keep
  producer-specific labels and owner rules distinct, compose a collision-free
  resource-UID domain, and leave complete Pod admission/images separate.

#### A. Establish the completion invariant test-first

- [ ] Add a proof decision with the four closed outcomes `complete`,
  `proved_not_applied`, `teardown_only`, and `unknown`. Inputs are an immutable
  expected context, exact pending intent, and bounded raw observations. The
  expected context binds run, intent sequence, source/profile/content
  commitments, fixed rendered objects, and previously established incarnations.
  A candidate response cannot supply its own expected values.
  Before the first mutation, persist private immutable `expected-inputs.json`
  and bind its digest in required journal field `expected_inputs_sha256`.
  It commits the reviewed profile, rendered Kind/application configuration,
  pinned Calico projection, accepted manifest/config image identities, fixed
  paths, and foreign-state baseline. Operation contexts may extend those inputs
  only with incarnation bindings rederived from hash-verified prior proof files.
  Journals lacking the commitment cannot authorize controller mutations or
  automated recovery; they must not be upgraded from current observations.
- [ ] Add an operation registry mapping each closed event family to its
  observation commands and pure validator. Normal execution and recovery call
  the same validator and terminal-event writer; remove the fallback that appends
  completion merely because an action returned. Unknown event families fail
  closed, not through a default completion branch.
- [ ] Persist the canonical bounded observation bundle privately before the
  terminal event, with no-follow/exclusive writes and fsync. Its commitment
  includes run, intent sequence, expected-input commitment, observation bytes,
  and bound resource identities. The terminal event binds that commitment.
  A hash of locally fabricated assertions is not observation evidence.
- [ ] Enforce one 64 MiB replayable proof-bundle budget distinct from individual
  32 MiB raw-observation limits; include hex expansion and expected inputs before terminal
  commitment. A valid profile JSON response with 17 MiB trailing whitespace
  must either be rejected before terminal or commit a proof that a fresh
  controller can revalidate. Never accept a bundle larger than its replay
  decoder permits.
- [ ] Write proof bytes to an owned private temporary file, flush/fsync, then
  atomically publish the complete digest-derived final name with no-replace
  semantics and fsync the parent before the terminal. A crash during the first
  100 bytes must not leave a partial final-name proof that blocks every retry.
  Preserve strict validation of an already-existing final file; do not silently
  overwrite corrupt evidence or foreign/symlink collisions. Test interrupted
  writing and completed-publication-before-terminal reuse separately.
- [ ] Preserve `TimeoutExpired` stdout/stderr buffers as original bytes, including
  malformed UTF-8. Reserve synthetic transport code -1000 for a timeout with
  all captured partial buffers retained and -1001 for a timeout whose retained
  buffers are explicitly bounded prefixes. Neither is an observed process exit
  or a successful transport; neither can satisfy a completion validator. Do not
  replace emitted stderr with a diagnostic label. Test the image-load case where
  a timed-out store read plus fresh exact cluster proof permits teardown-only:
  its private observation bundle must still retain the emitted timeout bytes.
- [ ] Write and run the following regression shape for every non-request
  event before implementing its successful validator:

```python
for family in CLOSED_NON_REQUEST_EVENT_FAMILIES:
    with self.subTest(family=family):
        scenario = self.scenario(family)
        for observation in scenario.unrelated_or_malformed_observations:
            self.assertNotEqual(
                scenario.validate(observation).outcome, "complete"
            )
        self.assertEqual(
            scenario.validate(scenario.exact_postcondition).outcome, "complete"
        )
        scenario.assert_same_normal_and_recovery_decision()
```

The test fixture's closed family set is the journal's event family set minus
`request`; each scenario supplies actual command-response shapes and immutable
expected inputs from the following matrix. No scenario may merely make an
unrelated command return zero. `scenario.validate` calls the production pure
validator, and `assert_same_normal_and_recovery_decision` exercises both
production callers against the same observation.

| Family | Required completion observation; recovery rule |
|---|---|
| `profile_start` | Valid closed Colima inventory and reviewed owned configuration show exactly one running `kil-v3-lab`; observe an existing result, never start a missing profile during failure cleanup. Proven absence can establish not-applied; uncertain ownership remains manual. |
| `cluster_create` | Exact bound Docker endpoint, fixed node name/Kind labels/pinned node image, full node ID, fixed Kind-config digest, and `kube-system` UID; persist the created incarnation before it can authorize cleanup. |
| `image_import` | Both exact image references resolve to the bound content through the owned daemon; retained archive bytes match the intent. Do not repair missing images after failure. |
| `image_load` | A fixed read of the exact journal-bound Kind node's image store proves both image contents/references. Host-daemon image inspection or node existence is insufficient. Incomplete load enters teardown-only. |
| `calico_apply` | Objects and reviewed configuration derived from every pinned manifest document match explicit server-default normalization. Calico/node readiness is separately proven before application work; broad `get all` is insufficient. |
| `application_apply` | Exact rendered objects/configuration, policy-before-workload stage proofs, and generated Pod owner/UID/container bindings. Driver Pods are created only after listener/endpoints readiness. Missing objects during recovery do not authorize more apply operations. |
| `readiness` | Independent expected namespace/object families, image contents, policy graph, Calico/node readiness, workload/container counts, and endpoint address/Pod-UID joins. Persist the canonical attestation; do not mirror the candidate into `ExpectedInventory`. |
| `driver_start` | The existing bound Pod/container and one canonical track-bound readiness record, with unchanged identity around capture. This registers readiness of an already-created driver; recovery never creates or forward-starts missing drivers. |
| `driver_cancel` | Same bound Pod UID/container incarnation and successful terminal exit after EOF-only cancellation, or already-observed successful terminal state. Nonzero terminal exit after EOF is teardown-only abandonment, not proof the mutation did not occur. |
| `envoy_quiesce` | Same live Pod/container, explicit listener refusal, and each required active gauge present exactly once and zero. An HTTP response or generic socket error alone is insufficient. Repeat only the fixed cleanup control when the exact same process remains serving. |
| `evidence_freeze` | Durable real source bytes plus stable capture-time identities and individual lengths/hashes; include each source boundary in the commitment, not only concatenated payloads. Reuse verified frozen bytes or capture still-readable bound sources. Missing/malformed sources stay explicit private diagnostics. |
| `cluster_delete` | Exact owned identity before deletion and positive cluster/node absence through a functioning owned endpoint afterward. Repeat deletion only against an already-established matching incarnation. |
| `cluster_absence_proof` | Successful authoritative inventory excludes both the bound node ID and fixed cluster/node name; transport, permission, malformed-response, or daemon errors are unknown. |
| `profile_stop` | Successful closed inventory proves the owned profile stopped; exact running ownership permits an idempotent stop. Do not require its deliberately stopped Docker daemon to be available before profile cleanup. |
| `profile_delete` | Successful closed inventory excludes the owned profile and the exact enumerated profile state paths are checked. Arbitrary `colima status` failure is not absence. |
| `profile_absence_proof` | Valid profile absence and no-follow absence of every enumerated active-state path, after authorized path cleanup. Retained private frozen evidence is explicitly distinct from active state. |
| `foreign_snapshot_comparison` | Newly observed full closed profile projection and global Docker context are compared to the immutable preflight snapshot. Preserve mismatch evidence; never reuse the intent's equality flag as proof or repair foreign state. |
| `publication` | Exact destination/run, valid owned-absence and foreign-comparison proofs, allowed result class, and reverified complete file/tree commitment. Failed lifecycles can expose only a supported calibrated diagnostic, never nominal success. |

Request intent remains outside generic recovery mutation. Never resend an
instruction; bind the original canonical result to the exact case and driver,
or preserve the stranded intent for diagnostic capture and teardown.

#### B. Close authority, absence, expectations, and failure transitions

- [ ] Preserve the accepted dedicated VM configuration: 4 CPUs, 8 GiB memory,
  60 GiB data disk, `aarch64`, Docker, and `vz`. Bind these independent values
  in expected inputs and compare raw Colima byte counts (8589934592 memory,
  64424509440 disk). Carry forward explicit non-activation, no SSH-config,
  no template, no agent-forwarding/emulation/embedded-Kubernetes, and restricted
  shared-network flags from the accepted V3B-1 command. Use `--mount none`
  because V3B-2 imports and applies via command input rather than a shared
  staging directory; verify saved configuration, not flags alone. Test that
  global-context activation and default home/tmp mounts cannot occur. The
  [pinned Colima start source](https://github.com/abiosoft/colima/blob/v0.10.3/cmd/start.go)
  defines the explicit no-mount option and otherwise enables activation and
  SSH-config generation by default.
- [ ] Reproduce the inherited-authority defect by setting a synthetic
  `DOCKER_CONTEXT` in a patched test environment and mocking the process boundary.
  Assert the child cannot inherit Docker authority/configuration overrides,
  `KUBECONFIG`, or alternate Colima/Lima homes that redirect reviewed commands.
  Preserve only reviewed process prerequisites; explicitly supply each command's
  owned authority. Inspect only the synthetic test keys, never dump real env.
- [ ] Replace generic return-code absence with typed present/absent/unknown/
  identity-mismatch observations. Add cases where permission denied, unavailable
  daemon, timeout, malformed JSON, or arbitrary stderr have the same exit status
  as a missing target: none may complete an absence event.
- [ ] Construct immutable expected topology/configuration from the reviewed
  profile, rendered application objects, pinned Calico documents, and explicit
  pinned Kind defaults. Include Calico ServiceAccounts `calico-node`,
  `calico-cni-plugin`, `calico-kube-controllers`, and ConfigMap `calico-config`;
  enumerate the remaining actual Kind objects from reviewed inputs rather than
  accepting arbitrary extras. Dynamic UIDs/IPs are validated observations bound
  to expected owners/selectors, not replacements for expected topology.
- [ ] Add one permanent failure/teardown latch to journal validation and command
  authorization. After it is set, permit only existing-resource cancellation,
  quiescence, diagnostics, exact teardown, positive absence proofs, comparison,
  and supported diagnostic publication. Remove failure cleanup that creates or
  registers missing drivers to satisfy nominal prerequisites. Allow available
  source capture/owned cleanup when only a subset of drivers was established;
  never manufacture successful start/cancel events for missing/failed drivers.

#### B.1 Pinned bootstrap inventory inputs

For the unchanged Kind 0.32.0 / Kubernetes 1.36.1 feature profile, settled
readiness requires 16 platform ConfigMaps and 48 platform ServiceAccounts,
before adding explicit Calico and KIL objects. Bootstrap observations may show
subsets while waiting, but may not declare settled readiness with missing
members or accept unlisted namespace extras. Bind the control-plane arguments
and feature settings that justify this finite inventory.

Required ConfigMaps, in addition to `kube-root-ca.crt` in each of the eight
fixed namespaces:

```text
kube-system/coredns
kube-system/extension-apiserver-authentication
kube-system/kube-apiserver-legacy-service-account-token-tracking
kube-system/kube-proxy
kube-system/kubeadm-config
kube-system/kubelet-config
kube-public/cluster-info
local-path-storage/local-path-config
```

Require `default` ServiceAccount in each fixed namespace, plus
`kube-system/coredns`, `kube-system/kube-proxy`, and
`local-path-storage/local-path-provisioner-service-account`. The remaining 37
platform ServiceAccounts are the following exact `kube-system` client names:

```text
attachdetach-controller
bootstrap-signer
certificate-controller
clusterrole-aggregation-controller
cronjob-controller
daemon-set-controller
deployment-controller
device-taint-eviction-controller
disruption-controller
endpoint-controller
endpointslice-controller
endpointslicemirroring-controller
ephemeral-volume-controller
expand-controller
generic-garbage-collector
horizontal-pod-autoscaler
job-controller
legacy-service-account-token-cleaner
namespace-controller
node-controller
persistent-volume-binder
pod-garbage-collector
pv-protection-controller
pvc-protection-controller
replicaset-controller
replication-controller
resource-claim-controller
resourcequota-controller
root-ca-cert-publisher
service-account-controller
service-cidrs-controller
statefulset-controller
token-cleaner
ttl-after-finished-controller
ttl-controller
validatingadmissionpolicy-status-controller
volumeattributesclass-protection-controller
```

These names derive from actual dynamic-client creation, not RBAC role suffixes.
Kubeadm enables `controllers=*,bootstrapsigner,tokencleaner` and
`use-service-account-credentials=true`; shared certificate/node clients do not
create a distinct account for every controller. The token controller uses the
root client, so `tokens-controller` is not an expected account. Under the
pinned defaults, do not permit accounts for resource-pool-status, PodGroup,
PodCertificateRequest, ClusterTrustBundle, storage-version API/migration,
SELinux-warning, or cloud route/service controllers. DRA device taints are
default-on in this tag. Source references:
[kubeadm arguments](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/controlplane/manifests.go),
[dynamic client builder](https://github.com/kubernetes/kubernetes/blob/v1.36.1/staging/src/k8s.io/controller-manager/pkg/clientbuilder/client_builder_dynamic.go),
[controller construction](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kube-controller-manager/app/controllermanager.go),
[core client names](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kube-controller-manager/app/core.go),
[bootstrap client names](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kube-controller-manager/app/bootstrap.go),
[feature defaults](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/features/kube_features.go),
and [apiserver feature defaults](https://github.com/kubernetes/kubernetes/blob/v1.36.1/staging/src/k8s.io/apiserver/pkg/features/kube_features.go).

ConfigMap provenance is the pinned kubeadm
[constants](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/constants/constants.go),
[DNS manifest](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/addons/dns/manifests.go),
[proxy manifest](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/addons/proxy/manifests.go),
[cluster-info bootstrap](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/bootstraptoken/clusterinfo/clusterinfo.go),
[apiserver startup](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/controlplane/apiserver/server.go),
[root-CA publisher](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/controller/certificates/rootcacertpublisher/publisher.go),
and [Kind storage manifest](https://github.com/kubernetes-sigs/kind/blob/v0.32.0/pkg/build/nodeimage/const_storage.go).
Dynamic CA material, kubeconfigs, signatures, and the tracking `since` date
remain private and require relationship/type validation, not equality to
invented static fixture bytes.

The fresh-producer ConfigMap contract is now source-closed. All 16 platform
objects are core/v1 ConfigMaps with string-valued `data`; none is produced with
`binaryData`, `immutable`, owner references, or finalizers. Require these exact
fresh data-key sets: `ca.crt` for each `kube-root-ca.crt`; `Corefile` for
`coredns`; `since` for the legacy-token tracker; `config.conf` and
`kubeconfig.conf` for `kube-proxy`; `ClusterConfiguration` for `kubeadm-config`;
`kubelet` for `kubelet-config`; `kubeconfig` plus the lifecycle-qualified JWS
key described below for `cluster-info`; and exactly `config.json`, `setup`,
`teardown`, and `helperPod.yaml` for `local-path-config`. The extension-apiserver
object has exactly `client-ca-file`, `requestheader-client-ca-file`,
`requestheader-username-headers`, `requestheader-group-headers`,
`requestheader-extra-headers-prefix`, and `requestheader-allowed-names` under
the fixed kubeadm arguments; `requestheader-uid-headers` is absent because
kubeadm supplies no UID header list. Require the root-CA publisher's exact
description annotation, `app: kube-proxy` on the proxy ConfigMap, and the
client-side-apply annotation on `local-path-config`; do not invent other
producer metadata.

Validate the content by producer relationship rather than text fragments.
Every root-CA PEM must parse and bind to the independently observed cluster CA;
the extension object must bind the cluster-client and distinct front-proxy CA
roles plus the four exact JSON header arrays. The legacy `since` value is a real
UTC `YYYY-MM-DD` creation-era date retained across later reconciliation, not
the observation date. Compare the entire CoreDNS `cluster.local` rendering.
Decode `kubeadm-config`, `kubelet-config`, and both kube-proxy values against the
generated/defaulted component inputs, while keeping the generic uploaded
kubelet configuration distinct from node-local CRI patching. Kind supplies both
component documents, so neither kubelet nor kube-proxy carries
`kubeadm.kubernetes.io/component-config.hash`. The cluster-info kubeconfig must
contain only the flattened internal cluster entry, with no authentication or
contexts, and must bind its HTTPS server and decoded CA to the internal admin
endpoint evidence.

The `cluster-info` signature count is lifecycle-bound, not permanently one.
With the single bootstrap token still valid and signer reconciliation settled,
require exactly `jws-kubeconfig-<six-lowercase-alphanumeric-token-id>` and verify
the detached compact HS256 JWS against the exact kubeconfig bytes and private
token evidence. After token expiry and cleaner/signer reconciliation, require
zero JWS keys. Syntax alone is not authenticity evidence. For
`local-path-config`, compare all four exact Kind-rendered values, including the
helper Pod using the pinned storage-helper image, and parse the last-applied
annotation as the original ConfigMap values without its own annotation or
server metadata.

The signature HMAC key is the 16-character token secret alone, never the full
`id.secret` token. Decode and require the exact protected `{alg: HS256, kid:
tokenID}` header, retain its original unpadded base64url segment, and verify
`HMAC-SHA256(tokenSecret, P + "." + base64url(exactKubeconfigBytes))` in constant
time. Kubernetes classifies the token expired when `expiration <= currentTime`.
Time passage alone does not prove signature removal: accepting the expired
zero-signature state requires a prior active signed proof for the same ConfigMap
UID/config/token and a strictly advanced ConfigMap resourceVersion after expiry.
The expired transition must also receive the transient prior raw `cluster-info`
ConfigMap and cryptographically revalidate its exact JWS against the private
token evidence at the prior capture time; a caller-constructible proof object or
digest alone cannot authorize removal. The returned proof retains neither raw
ConfigMap/JWS bytes nor the token secret.
Semantically parse the closed one-empty-name-cluster kubeconfig and bind its
HTTPS server and CA DER to independent internal-endpoint/trust evidence; verify
the JWS over the original string, not a reserialization.

The independently decoded fixture boundary is byte-exact. The Corefile is 420
UTF-8 bytes, retains one final LF, and has SHA-256
`22847ad9af7452500838865a67e018076226d8fbfcabf54f8673973571f470f6`.
The Kind `config.json`, `setup`, `teardown`, and `helperPod.yaml` values are
respectively 173, 45, 35, and 343 UTF-8 bytes, retain no final LF, and have
SHA-256 values `00112e23d095775fb664cbd04ca45734a237bbdd3fe8445c6b04857c702f0381`,
`b79c9a0bc2128407670551dc4086f4761bece38ca2aee95c23d307ac83ba99da`,
`b4567ea114784d0ab18a26d0057a0dc3e6945dc15ced1f40f6241e10f94b4d16`,
and `eb44d89e8e474527ec44571f5a2ba0c7bda81e13201124d225d2e9c5727c53be`.
The last-applied JSON may differ only in ordering/whitespace and may contain
either no `metadata.annotations` or an empty mapping; require exact core/v1
identity and the same four data values, with no self annotation or server
metadata.

The runtime observation must include ReplicaSets and Node identity so generated
Pods can be bound through exact controller UIDs: Deployment → ReplicaSet → Pod;
DaemonSet → Pod on the single bound node; static mirror Pod → Node UID plus
expected component/mirror annotation. EndpointSlices must bind exact owner UID,
manager label, ports, address, and target UID. Name prefixes alone do not prove
ownership. Include fixed CoreDNS/kube-proxy/local-path parents, the four fixed
control-plane mirror Pods, and the Kubernetes/kube-dns Services and endpoints.
No storage helper Pod is expected for these non-PVC KIL workloads.

Pinned fresh kubeadm creates two CoreDNS replicas; do not infer its count from
the one-node cluster size. Kind's single-node post-init removes the control-plane
taint and external-load-balancer exclusion label, not a DNS replica. Confirm
the generated kubeadm configuration contains no overriding DNS patch before
using this default. The kubeadm DNS Service input carries resourceVersion `"0"`
for create/update compatibility; that is a transient trusted-input field, not
permission to admit observed runtime resourceVersion zero. Source references:
[DNS initialization](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/addons/dns/dns.go),
[DNS manifests](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/addons/dns/manifests.go),
and [Kind post-init](https://github.com/kubernetes-sigs/kind/blob/v0.32.0/pkg/cluster/internal/create/actions/kubeadminit/init.go).

That confirmation is now source-backed for the fixed rendered Kind input:
Kind's beta-v4 kubeadm template has no DNS image/repository/patch-directory
override, and its patch generator applies only explicitly supplied cluster or
node patches; this profile supplies none. Omitted kube-proxy mode defaults to
iptables, rendered with `iptables.minSyncPeriod: 1s` and
`conntrack.maxPerCore: 0`. Rootless-only timeout/feature changes are not assumed:
the eventual runtime proof must bind whether the VZ provider is rootful before
selecting those values. Kubeadm supplies `registry.k8s.io/coredns/coredns:v1.14.2`
and `registry.k8s.io/kube-proxy:v1.36.1`, while Kind adds
`enable-hostpath-provisioner=true` without overriding
`controllers=*,bootstrapsigner,tokencleaner` or
`use-service-account-credentials=true`. Bind the actual generated kubeadm
configuration and effective arguments rather than treating these source-derived
references as observed image identities. Additional pinned sources:
[Kind kubeadm template](https://github.com/kubernetes-sigs/kind/blob/v0.32.0/pkg/cluster/internal/kubeadm/config.go),
[Kind configuration action](https://github.com/kubernetes-sigs/kind/blob/v0.32.0/pkg/cluster/internal/create/actions/config/config.go),
[Kind defaults](https://github.com/kubernetes-sigs/kind/blob/v0.32.0/pkg/apis/config/v1alpha4/default.go),
[kubeadm defaults](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/apis/kubeadm/v1beta4/defaults.go),
and [kubeadm image selection](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/images/images.go).

Adding the three pinned Calico ServiceAccounts and `calico-config` yields 51
SAs and 17 CMs before KIL-specific accounts/configuration. Full Calico apply
proof still covers all 38 documents. Public topology remains a deliberately
scoped projection; do not confuse its 67 explicit objects with the entire
platform resource count.

#### B.2 Kind/path-specific server normalization

Dispatch normalization by root API version/kind and exact structural path,
never by whether an arbitrary path contains `spec`. CRD schemas themselves
contain similarly named fields and must remain exact. Normalize desired
configuration, validate relational runtime additions separately, and compare
the resulting configurations. The pinned inputs require these rules:

- Ignore top-level `status` on both desired and observed objects for apply
  comparison; the last Calico CRD includes a status placeholder that the API
  replaces. Readiness still validates observed status independently.
- Root metadata admits validated UID/resourceVersion/timestamps/generation and
  bounded managedFields. Setup rejects deletionTimestamp. Template metadata
  admits only omitted/null creationTimestamp, not root identity fields.
  Last-applied annotations belong only at root and cannot prove configuration.
  Deployment revision is a positive bounded decimal joined to its ReplicaSet;
  fresh unchanged deployments settle at revision 1. Cluster-scoped kinds never
  acquire a default namespace.
- Namespace gets only its exact `kubernetes.io/metadata.name` label and
  `spec.finalizers=["kubernetes"]`; require separate Active status.
- The nine KIL Services get sessionAffinity None, internalTrafficPolicy Cluster,
  ipFamilyPolicy SingleStack, ipFamilies `["IPv4"]`, and a singleton clusterIPs
  equal to clusterIP. Validate usable, noncolliding addresses inside the bound
  Service CIDR and persist UID/IP bindings. Reject headless, external, NodePort,
  and load-balancer additions. Current desired type/ports/protocol are explicit.
  In the bounded static-only slice, normalize only sessionAffinity and
  internalTrafficPolicy. Keep IP-family policy/families and allocated address
  additions exact until the dynamic allocation validator supplies context;
  neither family value is an unconditional static API default.
- Current Deployments use Recreate: permit revisionHistoryLimit 10 and
  progressDeadlineSeconds 600, but no rollingUpdate configuration. Calico's
  DaemonSet uses RollingUpdate/maxUnavailable 1; permit only added maxSurge 0
  and revisionHistoryLimit 10 at its corresponding paths.
- PodSpec exists only at Pod.spec or Deployment/DaemonSet.spec.template.spec.
  Fill omitted dnsPolicy ClusterFirst, restartPolicy Always, securityContext
  `{}`, terminationGracePeriodSeconds 30, schedulerName default-scheduler, and
  deprecated serviceAccount alias equal to serviceAccountName. Preserve explicit
  driver Never and Calico termination grace 0.
  Omitted enableServiceLinks becomes true only on a direct Pod: it is set by
  `SetDefaults_Pod`, not `SetDefaults_PodSpec`, so it must not be inserted into
  Deployment/DaemonSet templates. Preserve KIL's explicit false. Pod-only
  request-from-limit and host-network host-port defaulting likewise belong to
  later actual/generated Pod validation, not template normalization.
- Existing containers/initContainers may acquire terminationMessagePath
  `/dev/termination-log`, terminationMessagePolicy File, omitted resources `{}`,
  existing-port protocol TCP, and fieldRef apiVersion v1. Image pull policies
  are already explicit and must not be relaxed. Existing probes acquire missing
  timeoutSeconds 1, periodSeconds 10, successThreshold 1, failureThreshold 3;
  do not admit a different probe action. Existing Calico hostPath type may
  become empty string, and omitted configMap defaultMode becomes 420; preserve
  KIL's explicit mode 292.
- Normalize only relevant scalar serialization omissions: container tty false,
  volumeMount readOnly false, and CRD preserveUnknownFields false may be omitted.
  Do not globally equate false/zero/empty/null with absence. Pointer-valued
  security false values, automount false, and all CRD schema defaults remain
  explicitly bound.
- CRD omitted conversion becomes exactly `{"strategy":"None"}`. Existing
  supplied names and every schema/version/subresource stay exact. A cleanup
  finalizer indicates deletion, not an ordinary create default. PDB v1 has no
  inserted default spec field in this tag; nil behavior is not an added
  IfHealthyBudget value. Existing NetworkPolicy and RBAC values are explicit.
- Directly applied driver Pods additionally admit priority 0, preemptionPolicy
  PreemptLowerPriority, and exactly two default Exists/NoExecute tolerations
  (not-ready/unreachable, 300 seconds); nodeName binds the single owned node.
  Calico podIP/podIPs annotations must agree with status and the Pod CIDR.
  Calico's containerID annotation identifies the CNI sandbox, not the app's
  containerStatuses containerID. No token mount or inherited imagePullSecret
  is permitted for KIL's automount-disabled Pods. Do not admit these Pod-only
  additions inside workload templates.
- Generated Calico Pods require separate owner-derived admission validation,
  including correlated token projection/mount, resolved priority class, and
  DaemonSet node affinity/tolerations. A generated name is not permission for
  an arbitrary volume or controller chain.

Assemble representative API-response fixtures independently of the production
normalizer. For each permitted default or omission, test the exact valid
transformation and a changed value/wrong-kind/wrong-path rejection. Include
CRD schema properties named like PodSpec defaults to prove normalization cannot
rewrite nested schema content. Include wrong owner UID, extra Pod/container,
duplicate Service address, missing bootstrap object, and deleting-object cases.

Primary sources for the finite rules:
[core defaults](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/apis/core/v1/defaults.go),
[core conversion](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/apis/core/v1/conversion.go),
[core JSON tags](https://github.com/kubernetes/kubernetes/blob/v1.36.1/staging/src/k8s.io/api/core/v1/types.go),
[apps defaults](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/apis/apps/v1/defaults.go),
[Service allocation](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/registry/core/service/storage/alloc.go),
[CRD defaults](https://github.com/kubernetes/kubernetes/blob/v1.36.1/staging/src/k8s.io/apiextensions-apiserver/pkg/apis/apiextensions/v1/defaults.go),
[CRD create strategy](https://github.com/kubernetes/kubernetes/blob/v1.36.1/staging/src/k8s.io/apiextensions-apiserver/pkg/registry/customresourcedefinition/strategy.go),
[PDB default registration](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/apis/policy/v1/zz_generated.defaults.go),
[default tolerations](https://github.com/kubernetes/kubernetes/blob/v1.36.1/plugin/pkg/admission/defaulttolerationseconds/admission.go),
[priority admission](https://github.com/kubernetes/kubernetes/blob/v1.36.1/plugin/pkg/admission/priority/admission.go),
[ServiceAccount admission](https://github.com/kubernetes/kubernetes/blob/v1.36.1/plugin/pkg/admission/serviceaccount/admission.go),
[DaemonSet additions](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/controller/daemon/util/daemonset_util.go),
and [Calico annotations](https://github.com/projectcalico/calico/blob/v3.32.0/libcalico-go/lib/backend/k8s/resources/workloadendpoint.go).

#### B.3 Complete owned profile state and shutdown proof

Use the focused profile-state module for this bounded slice; keep operation
sequencing in the controller and pure event decisions in the proof registry.
Let `H` be the passwd-derived home (not ambient `HOME`), `C=H/.colima`,
`L=C/_lima`, and `N=colima-kil-v3-lab`. Bind a private runtime TMPDIR before
starting Colima. The exact owned runtime paths are:

```text
C/kil-v3-lab/              # saved colima.yaml, docker.sock, daemon files
L/N/                       # lima.yaml, runtime colima.yaml, root disk, VM state
L/_disks/N/                # datadisk and intentional in_use_by symlink
C/_store/N.json            # Colima disk/runtime bookkeeping
BOUND_TMPDIR/N.yaml        # generated startup configuration
```

- [ ] Preflight rejects any owned profile/instance/disk/store/startup remnants
  before creating the journal's mutation authority. Derive paths from passwd
  home plus the fixed identity and private TMPDIR, never from discovered names
  or caller-supplied paths. Reject symlinked parents with no-follow component
  checks. Shared `_config`, `_networks`, templates/caches and shared SSH config
  are not owned instance paths and must never be removed.
  Repeat the pristine check before recording startup intent and immediately
  before actual start dispatch, including resumed prepared journals. If the
  latter check refuses, durably latch that exact intent as refused so neither
  the ordinary error handler nor fresh recovery can adopt the rejected state
  as a creation binding. This authority-reducing refusal is not fabricated
  command output or proof that an attempted mutation was not applied. Recovery
  remains observe-first for legitimate pending starts without a refusal marker.
  The required nullable `profile_start_refused_sequence` is tied to that exact
  sole pending startup intent and is monotonic once set, alongside the permanent
  teardown latch. Missing-field older journals fail closed rather than acquiring
  authority through automatic migration. This is not an atomic exclusion lock
  against an uncooperative external Colima invocation between check and dispatch.
- [ ] Bind HOME consistently in controller and runner; remove ambient
  COLIMA_HOME/XDG_CONFIG_HOME/LIMA_HOME/COLIMA_SAVE_CONFIG authority and supply
  the exact LIMA_HOME only to a reviewed Lima fallback. Bind private
  DOCKER_CONFIG for Colima host setup/teardown as well as owned Docker/Kind
  operations; global Docker context observation remains a separate read of the
  original global context. Use private bound TMPDIR so interrupted startup does
  not leave untracked active configuration in a shared temporary directory.
- [ ] Parse bounded saved `C/kil-v3-lab/colima.yaml` and `L/N/colima.yaml`
  with a closed, duplicate-rejecting inert YAML subset; reject tags, aliases,
  custom scripts/environment/daemon overrides and ambiguous scalar forms.
  Follow the existing safe fixed-profile parsing approach, without introducing
  a runtime YAML dependency. Require 4 CPU/8 GiB memory/60 GiB data disk,
  aarch64/docker/vz, 20 GiB root disk, virtiofs, no activation/SSH-config/agent/
  emulation/nested virtualization/embedded Kubernetes, and the restricted
  shared network with pinned defaults. The no-mount representation is exactly
  `mounts: null`: `mounts: []` means default writable HOME mounting and must
  fail. `--template=false` is a CLI control, not a saved YAML field.
- [ ] Successful profile creation must persist verified configuration hashes,
  exact resource identities, data-disk size, and lock relation as proof-derived
  bindings for later operations. Inspect the intentional `in_use_by` symlink
  only with readlink and require its exact target `L/N`; never follow it.
  Extend the closed private event/binding contract deliberately as required;
  do not infer an expected resource identity from a later candidate.
- [ ] Profile deletion requires positive list absence and no-follow absence of
  the entire profile, instance, and disk directories, plus startup artifact.
  A zero-valued Colima store residue may be classified explicitly as inactive,
  but is never evidence that its disk disappeared. Private Docker configuration
  created by Colima must be cleaned only through exact owned, validated entries,
  not an assumed empty-directory rmdir or broad recursive removal.
  Pure capture validation must enforce parent/child presence and exact known
  directory-entry membership, not merely validate each record separately.
  Absent profile/instance/disk parents cannot coexist with present child config,
  disk, or lock records. Reject these contradictions through direct absence,
  orphan authorization, terminal decisions, and retained-proof replay.
- [ ] Normal cleanup uses only the existing exact Colima delete command.
  If its already creation-bound data disk remains, allow the registry's scoped
  fallback `limactl disk delete colima-kil-v3-lab` with exact bound LIMA_HOME,
  never `--force`. Recheck directory absence afterward; exit zero alone can
  skip a referenced or corrupt disk. Require established disk provenance and
  no foreign lock/reference before authorizing this fallback. Lost provenance,
  replacement/symlink, unreadable/corrupt disk, protected VM or malformed
  instance remains manual recovery rather than guessed deletion.
  Do not classify all non-QCOW2 bytes as raw: match the pinned Lima reader's
  recognized image-container formats (including VHDX/VMDK/VDI/Parallels/VPC/ASIF)
  before accepting raw. In-place unsupported-header changes with the same inode
  and size must block both ordinary deletion and orphan fallback. This is bounded
  container-format/metadata validation, not a guest filesystem integrity scan.
  The initial fallback may conservatively refuse when another Lima instance
  prevents proving absence of references; classify this as unproved reference
  absence, not a confirmed foreign reference. Normal owned Colima deletion must
  still work with unrelated profiles present, and no fallback may operate on
  those other instances.
- [ ] Use temporary isolated home fixtures, not real host state, for tests.
  Cover ambient HOME/Colima/Lima/TMPDIR redirection, mounts null versus empty,
  config mismatch between both saved files, pre-existing orphan refusal,
  Colima exit zero with disk still present, exact orphan cleanup, foreign lock,
  replaced inode, post-delete store zero-state, and interrupted profile startup.
  Keep readiness fail-closed pending B.1/B.2/resource proof completion.

Pinned sources:
[profile paths](https://github.com/abiosoft/colima/blob/v0.10.3/config/profile.go),
[environment-sensitive paths](https://github.com/abiosoft/colima/blob/v0.10.3/config/files.go),
[saved template](https://github.com/abiosoft/colima/blob/v0.10.3/embedded/defaults/colima.yaml),
[nil-preserving YAML](https://github.com/abiosoft/colima/blob/v0.10.3/util/yamlutil/yaml.go),
[mount semantics](https://github.com/abiosoft/colima/blob/v0.10.3/config/config.go),
[Colima delete](https://github.com/abiosoft/colima/blob/v0.10.3/app/app.go),
[configuration teardown](https://github.com/abiosoft/colima/blob/v0.10.3/config/configmanager/configmanager.go),
[store reset](https://github.com/abiosoft/colima/blob/v0.10.3/store/store.go),
[startup temporary config](https://github.com/abiosoft/colima/blob/v0.10.3/environment/vm/lima/lima.go),
[Lima disk state](https://github.com/lima-vm/lima/blob/v2.2.0/pkg/store/disk.go),
[pinned image-format dispatch](https://github.com/lima-vm/go-qcow2reader/blob/v0.7.1/qcow2reader.go),
[bounded first-sector probes](https://github.com/lima-vm/go-qcow2reader/blob/v0.7.1/image/stub/stub.go),
[Lima filenames](https://github.com/lima-vm/lima/blob/v2.2.0/pkg/limatype/filenames/filenames.go),
and [disk CLI](https://github.com/lima-vm/lima/blob/v2.2.0/cmd/limactl/disk.go).
Colima 0.10.3 removes the saved profile directory during deletion, but its data
disk deletion depends on `disk_formatted`; missing/malformed store can leave an
orphan. This is why configuration removal and runtime-disk absence are separate
postconditions.

Fresh CLI defaults are not identical to the commented template: the reviewed
`cmd/start.go` flag-to-config path supplies empty `cpuType` and `hostname`, null
DNS and provision slices, and an empty `dnsHosts` map. The saved serializer
overlays template fields and preserves those nil slices as null. The profile
fixtures must represent this CLI path, not the template alone. The current
profile slice conservatively accepts only raw disks, as used by the pinned
Linux VZ driver; unsupported disk formats and interrupted startup without a
completed creation binding require manual recovery. These limitations do not
authorize discovering or deleting resources from their names alone.

#### B.4 Preserve the pinned foreign-profile inventory schema

The pinned Colima `list --json` emits one `InstanceInfo` per line, with `dir`
removed and `network` cleared. `address` is optional but legitimate for foreign
profiles. Runtime can be docker/containerd/incus, their `+k3s` variants, or none;
an unrecognized configuration yields an omitted runtime, not a safe default.
The present exact-seven-field/docker-or-containerd decoders therefore reject
some ordinary unrelated profiles and need a shared corrected boundary before
live validation. This does not weaken the owned profile's exact docker/no-address
configuration contract or permit mutation of another profile.

- [ ] Decode bounded duplicate-free JSONL (and retained test/legacy array form)
  with one closed schema. Validate known optional address as a single IP literal;
  retain presence/value in private before/after comparison. Accept only the
  pinned nonempty runtime forms for foreign records. Missing/invalid required
  fields and unknown fields remain unknown/fail-closed, never inferred defaults.
- [ ] Reuse the decoder in controller, pure proofs and private evidence checks,
  keeping the owned configuration stricter. Explicitly project public fields:
  private foreign addresses and names must not leak through a wholesale copy.
  Changes in optional address/runtime must affect the private equality result.
  Add a domain-separated keyed commitment of each full private normalized record
  to its public projection, using the existing private per-run projection key.
  This preserves public before/after equality checking when a hidden address
  changes; simply dropping addresses before comparison would lose that signal.
  Do not publish the key/nonce, raw address, or an unkeyed low-entropy address
  hash. Public verification compares the opaque commitments but cannot
  independently reconstruct private address values or recompute their HMAC.
  Bind the terminal attestation commitment and private after-snapshot to the
  same retained proof observation. A preliminary controller sample must not
  supply evidence while a later registry sample supplies only the equality
  flag. Recovery and hydration must derive the final snapshot/commitment from
  the validated proof, including when state changed after the initial intent.
- [ ] Test JSONL/arrays, absent/present address, all supported runtime forms,
  invalid address, duplicate fields, missing runtime, unexpected fields, and
  before/after drift. Preserve exact observed raw bytes in existing proof files.
- [ ] Assess completeness against the existing no-follow Lima directory roster
  before declaring a foreign snapshot complete. `Instances` uses a Scanner and
  does not propagate its final error; a truncated underlying listing must not
  silently become a complete empty foreign inventory. Use read-only exact
  roster reconciliation or fail closed; never operate on discovered foreign
  names. Do not inspect unrelated guest contents.

Sources: [JSONL command](https://github.com/abiosoft/colima/blob/v0.10.3/cmd/list.go)
and [InstanceInfo/Instances/getRuntime](https://github.com/abiosoft/colima/blob/v0.10.3/environment/vm/lima/limautil/instance.go).

#### C. Bind actual producer bytes before deriving reduced evidence

- [ ] Replace nominal FakeRunner source rows with real producer-format records
  from `kil.v3b1_request_driver`, `kil.ext_authz_http`, `kil.target_http`, and the
  reviewed Envoy access-log format. First demonstrate that unchanged raw records
  fail the old reduced-schema publication path.
- [ ] Add closed validators/adapters for each actual producer schema. Driver
  `attempt_count`/`response_status`, authorization `outcome`, Envoy access
  fields, and actual target records are validated before deriving the existing
  reduced joins. Derive decisions/digests from observed authorization and
  correlated sources, never from the expected result tuple. Bind any fixed
  transport-to-V3B-2 run/request mapping explicitly to the durable instruction
  and case identities; retain original record values.
- [ ] Persist each `CapturedSource` payload and a closed capture manifest before
  teardown. Bind kind/track, exact Pod/container location, UID, capture-time
  resourceVersion, container incarnation, full byte count, and full digest.
  Retain driver readiness bytes even though readiness is not an application
  request. Distinguish initial readiness RV from the later stable capture RV.
- [ ] Extend the private/public source-attestation validators together so public
  claims bind the full captured source and its reduced projection separately.
  Keep exactly eleven public files. Safe canonical source records may be bound
  within the manifest; malformed or sensitive bytes remain private with only
  permitted sanitized metadata exposed. Public verification must rederive both
  raw-source commitments and reduced joins; a checksum over reduced rows is not
  a raw-source commitment. Update every exact-field contract and privacy path
  allowlist deliberately, with repaired-hash tampering tests.
- [ ] Request-free verification must retain all twelve source bindings,
  including three readiness records and nine empty service ledgers, while still
  proving zero application requests/results/joins. Missing source capture must
  never become a synthetic empty attestation.

##### C.1 Durable instruction, case, and result association

- [ ] Persist canonical private case bytes before request intent. Each case
  includes its existing safe expectations and the actual private instruction's
  SHA-256 and byte count. Define `case_sha256` as the digest of those canonical
  case bytes, not an alias for the instruction digest. Extend the closed request
  intent with a separate `instruction_sha256`; repeat the case/instruction
  association in its terminal result.
- [ ] Persist exact attach stdout privately before its terminal event. Define
  `attach_sha256` over those actual bytes and `result_sha256` over the canonical
  parsed terminal record. Accept only the existing terminal-only or
  readiness-plus-terminal framing, with no extra records. If attach includes
  readiness, require equality with the captured driver readiness record.
- [ ] Private replay reads the actual bounded canonical instruction, applies
  `parse_instruction`, recomputes its digest, and checks the exact run-prefix,
  track, and request-ID mapping. Recompute case bytes and join the unique journal
  intent/result, attach terminal, and captured driver terminal. Repaired hashes
  cannot bypass inconsistent contents, incarnation, or missing/duplicate events.
- [ ] Public `manifest.json` carries a closed safe `request_bindings` projection
  with case facts and case/instruction/result commitments; source attestations
  reference the same association. Explicitly project public fields rather than
  copying the private record wholesale. Public verification rederives case and
  driver-result commitments and their consistency. It cannot recompute a private
  sensitive instruction's digest without private bytes, and must say so.
- [ ] Keep the shared V3B-1 driver protocol unchanged. Its terminal does not echo
  a consumed-instruction digest: the supported claim is controller/journal-bound
  association, not producer-attested consumption. Stronger consumption evidence
  would require a separately reviewed protocol change, not inference from a hash.
- [ ] Cover changed instructions, wrong run/track/request, swapped cases,
  changed journal commitments, changed attach/captured terminal, duplicate or
  missing intent/result, both valid attach framings, readiness mismatch, extra
  lines, truncation, and noncanonical bytes. No private Q-state or instruction
  bytes may enter the public eleven-file bundle.

##### C.2 Partial capture and calibrated failure publication

- [ ] Version the private capture manifest with `schema_version`, `run_id`,
  `capture_outcome`, and twelve ordered logical source-status entries. A
  `captured` entry binds actual identity/bytes; an `unavailable` entry has a
  closed reason (`not_established`, `read_failed`, `identity_drift`, `truncated`,
  or `invalid_records`) and a diagnostic observation commitment where applicable.
  Never turn a failed or unattempted read into empty source records.
- [ ] Persist each successful source immediately. Finalize a diagnostic-partial
  manifest when later sources fail, retain malformed bytes privately, and reuse
  immutable captures after restart. Freeze observes files actually committed in
  this manifest and validates statuses against established identities and actual
  diagnostic observations. It cannot demand twelve successful captures after a
  driver never started. A diagnostic-partial freeze is teardown-only and latches
  non-promotion; only a complete verified capture may claim all boundaries frozen.
  Read at least one overflow-sentinel byte beyond the accepted source limit
  for bounded Kubernetes logs as already done for ledger-file reads. A read
  capped at exactly the accepted byte limit cannot establish completeness at
  that boundary. Update command builders/allowlists together and preserve
  oversized returned bytes privately as explicitly truncated diagnostics.
  On retry or hydration, derive reduced records and counts once from retained
  captures; do not accumulate `_application_records` again or reread live
  sources to reconstruct already-frozen evidence.
- [ ] Known-owned cancellation/deletion and foreign-state comparison must remain
  possible before readiness, after an absent later driver, or after a failed
  source read. Failure classification does not relax ownership or postcondition
  checks and does not authorize application retries or further forward work.
- [ ] Private partial capture and safe cleanup may be implemented/reviewed as an
  intermediate slice, but Task 6 still requires the approved calibrated failure
  publication path. Add a distinct nonpromotable partial-diagnostic result class
  within the same eleven public files. Its closed sanitized projection records
  which boundaries were captured versus unavailable, valid commitments and
  failure categories; it must not manufacture complete topology, nominal joins,
  request-free success, or empty-capture attestations for missing observations.
  The public verifier independently rejects these invalid claims. Empty derived
  output files signify unavailable derivation under this result class, not proof
  of zero source events. Private sensitive/malformed bytes remain private.
- [ ] Test failures before readiness, before any driver, after a failed first
  request, with a missing later driver, unreadable source, identity drift, and
  restart after individual capture or manifest persistence. Test public/private
  schema separation and repaired-hash attempts to relabel partial as complete.

##### C.3 Exact Envoy refusal observation

- [ ] Preserve the reviewed plain HTTP drain/stats control and retained Envoy
  incarnation. The producer must classify exact `ECONNREFUSED`, not arbitrary
  TCP or shell failure, before emitting `listener_refused: true`. Use bounded
  control/observation and fixed diagnostic locale; do not synthesize the boolean
  in the controller. Timeout, permission failure, unreachable network, reset,
  or malformed/truncated admin response remains unsuccessful observation.
  The repository establishes Bash, not Python/curl/timeout availability inside
  the pinned Envoy image. A fixed-command Bash probe may classify an exact
  complete C-locale diagnostic as explicit refusal, with reviewed exit status,
  zero stdout, bounded stderr, fixed script name/line numbering, and suppressed
  startup/environment execution. Never substring-match refusal text or claim
  Bash exposes numeric errno. Independently supplied grammar fixtures prove
  fail-closed classification; the actual pinned-image grammar remains a later
  live compatibility gate, and unfamiliar output must fail closed. Bound HTTP
  headers/body and reads; an outer kubectl timeout alone does not prove the
  remote shell terminated. Do not add unproved runtime-binary dependencies.
- [ ] Preserve the existing accepted proof rule: every one of the four active
  gauges appears exactly once as integer zero. Cover open listener, exact
  refusal, timeout/EACCES/ENETUNREACH/reset, admin non-200, truncated response,
  and active/missing/duplicate gauges through the actual producer command path.

#### D. Reverify the real interfaces and return to independent review

- [ ] Replace the legacy tiny-archive fixture's patched digest function with a
  self-consistent synthetic accepted-input fixture. Its manifest, archive size,
  archive SHA-256, and image identities must describe the actual fixture bytes;
  scope any test-only substitutions to the fixed acceptance constants, never
  the production digest/streaming verifier. Separately assert the real pinned
  acceptance constants and reject mismatched bytes, size, and repaired manifest
  claims. Do not add a production caller-selected acceptance override, a large
  checked-in archive, or a dependency on another worktree's private runtime
  directory. Keep Docker config IDs, node-store targets, and public Pod imageID
  fixtures distinct according to the pinned representation contract above.
- [ ] For each matrix family, simulate command success plus invalid/missing
  postcondition and crash after mutation but before completion persistence.
  Assert the exact permitted transition and absence of forward work. Include
  wrong cluster/Pod/container identities, wrong image contents, missing pinned
  Calico objects, mismatched endpoint UID/address, poisoned inherited authority,
  unknown absence observations, and partial-source capture.
- [ ] Run focused and full gates on the stable corrected tree:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_v3b2_proofs tests.test_v3b2_contracts tests.test_v3b2_manifests \
  tests.test_v3b2_inventory tests.test_v3b2_journal tests.test_v3b2_evidence \
  tests.test_v3b2_controller tests.test_v3b2_observed_lifecycle \
  tests.test_v3b2_profile_state tests.test_v3b2_api_defaults \
  tests.test_v3b2_colima_inventory -v
make docs-html PYTHON=../../.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 make validate PYTHON=../../.venv/bin/python
git diff --check
```

Expected: all tests and readers pass; no live runtime command was executed and
no private/runtime artifact is tracked. Root handles staging/commits so an
implementer cannot silently stall on Git approval. Repeat independent
specification and then quality review on the complete corrected Task 6 delta.
Only after both accept does Task 7 open. The already selected subagent workflow
continues; this correction does not reopen V3B-2b or V3C.

### Task 7: Wire documentation, Make targets, and static acceptance

**Files:**

- Create: `tests/test_v3b2_documentation.py`
- Modify: `Makefile:1-45`
- Modify: `deploy/kind/README.md:1-7`
- Modify: `tools/README.md:51-104`
- Modify: `docs/lab/V3-PROGRESS.md`

- [ ] **Step 1: Write failing documentation and command-safety tests**

```python
class V3B2DocumentationTest(unittest.TestCase):
    def test_make_targets_are_fixed_and_profile_scoped(self):
        makefile = (ROOT / "Makefile").read_text()
        for target in ("v3b2-preflight", "v3b2-request-free", "v3b2-nominal", "v3b2-down"):
            self.assertIn(f"{target}:", makefile)
        self.assertNotIn("PROFILE ?=", makefile)
        self.assertNotIn("CLUSTER ?=", makefile)

    def test_docs_state_nominal_and_campaign_boundaries(self):
        text = (ROOT / "deploy/kind/README.md").read_text()
        self.assertIn("intermediate_provisional_kind_calico_nominal", text)
        self.assertIn("not_promoted", text)
        self.assertIn("V3B-2b", text)
        self.assertNotIn("complete NetworkPolicy validation achieved", text)

    def test_no_example_mutates_an_unscoped_colima_profile(self):
        corpus = "\n".join((ROOT / path).read_text() for path in ("Makefile", "deploy/kind/README.md", "tools/README.md"))
        for line in corpus.splitlines():
            if "colima " in line and any(word in line for word in ("start", "stop", "delete")):
                self.assertIn("kil-v3-lab", line)
```

- [ ] **Step 2: Verify RED**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.test_v3b2_documentation -v
```

Expected: failures for missing Make targets and V3B-2 operator documentation.

- [ ] **Step 3: Add fixed Make targets**

```make
v3b2-preflight: check-python
	PATH="$(CURDIR)/.tools/bin:$$PATH" PYTHONPATH=src $(PYTHON) tools/v3b2_kind_calico.py preflight

v3b2-request-free: check-python
	PATH="$(CURDIR)/.tools/bin:$$PATH" PYTHONPATH=src $(PYTHON) tools/v3b2_kind_calico.py request-free

v3b2-nominal: check-python
	PATH="$(CURDIR)/.tools/bin:$$PATH" PYTHONPATH=src $(PYTHON) tools/v3b2_kind_calico.py nominal

v3b2-down: check-python
	PATH="$(CURDIR)/.tools/bin:$$PATH" PYTHONPATH=src $(PYTHON) tools/v3b2_kind_calico.py down
```

The controller supplies every fixed identity; Make accepts only the existing
`PYTHON` override.

- [ ] **Step 4: Document exact operator gates and claim limits**

Document preflight, request-free, down/recover, view, and nominal commands.
State that `v3b2-nominal` is forbidden until the accepted request-free bundle
is merged and local/remote `main` equality is proven. State that neither static
tests nor request-free evidence proves a consequential result, and nominal
evidence does not prove the V3B-2b failure matrix, repetition, latency,
production readiness, or historical prevention.

- [ ] **Step 5: Run focused and full static validation**

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.test_v3b2_contracts \
  tests.test_v3b2_manifests \
  tests.test_v3b2_inventory \
  tests.test_v3b2_journal \
  tests.test_v3b2_evidence \
  tests.test_v3b2_controller \
  tests.test_v3b2_documentation -v
make validate PYTHON=../../.venv/bin/python
```

Expected: all focused and repository tests pass, generated readers are current,
and `git diff --check` reports no issue.

- [ ] **Step 6: Commit the static acceptance checkpoint**

```bash
git add Makefile deploy/kind/README.md tools/README.md docs/lab/V3-PROGRESS.md \
  tests/test_v3b2_documentation.py
git commit -m "docs: define V3B-2a operator gates"
```

### Task 8: Complete review, public CI, merge, and exact synchronization

**Files:**

- Modify only artifacts required by concrete review findings.
- Regenerate tracked `.htm` readers for every changed Markdown source.

- [ ] **Step 1: Run specification-compliance review**

Review every section of
`docs/superpowers/specs/2026-09-06-v3b2-kind-calico-validation-design.md`
against Tasks 1–7. Record each requirement as implemented, intentionally
deferred to V3B-2b, or failed. Any V3B-2a failure returns to the owning task.

- [ ] **Step 2: Run quality and security review**

Inspect command injection, current-context use, path containment, symlink and
replacement races, canonical decoding, type confusion, sensitive error text,
foreign-resource mutation, request replay, ambiguous ownership, and incomplete
publication. Fix validated findings test-first and commit each coherent fix.

- [ ] **Step 3: Re-run the complete gate**

```bash
make docs-html PYTHON=../../.venv/bin/python
make validate PYTHON=../../.venv/bin/python
git diff --check
git status --short
```

Expected: full validation passes and status contains only intended tracked
changes. No `.tools/`, kubeconfig, journal, private evidence, or runtime object
is tracked.

- [ ] **Step 4: Publish the implementation branch and require public CI**

Push the branch, open a PR describing static-only scope, wait for all required
checks, and merge only after reviews pass. Do not squash away reviewed commit
boundaries if evidence references them.

- [ ] **Step 5: Prove exact source synchronization before runtime**

```bash
git fetch origin
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain)"
```

Expected: both assertions pass in a fresh execution worktree. Record the full
40-character commit in the new private journal before any owned mutation.

### Task 9: Execute and publish the request-free lifecycle

**Files:**

- Create after successful live execution: one content-addressed request-free
  bundle under `artifacts/generated/v3b2-kind-calico/`.
- Modify: `docs/lab/V3-PROGRESS.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

- [ ] **Step 1: Prove the live preconditions without mutation**

```bash
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src ../../.venv/bin/python \
  tools/v3b2_kind_calico.py preflight
```

Expected: exact public-main synchronization, verified tool bytes, owned profile
absent, closed foreign snapshot captured, global Docker context captured,
Calico bytes verified, and journal created. Stop if `kil-v3-lab` already exists
or the foreign inventory is ambiguous.

- [ ] **Step 2: Execute the request-free lifecycle**

```bash
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src ../../.venv/bin/python \
  tools/v3b2_kind_calico.py request-free
```

Expected: one fresh cluster reaches closed Kind/Calico/application readiness,
three drivers emit readiness, zero instructions and zero HTTP requests occur,
empty service ledgers are frozen, only the `kil-v3-lab` cluster/profile are
deleted, foreign state and Docker context compare equal, and one diagnostic
bundle path is printed.

- [ ] **Step 3: Independently verify absence and the bundle**

```bash
colima list --json
```

Inspect the Colima JSON read-only: `kil-v3-lab` must be absent and every foreign
profile from the before snapshot must have the same normalized status and
resources. Run `tools/v3b2_kind_calico.py view --bundle` with the literal path
printed by Step 2; do not use a glob or select the newest directory.

- [ ] **Step 4: Publish only the request-free checkpoint**

Update progress and lineage with the exact run ID, source commit, bundle
digest, zero-request count, teardown proof, foreign comparison, and limitations.
Generate readers, run full validation, complete specification and security
reviews, push, pass public CI, merge, and prove local/remote `main` equality.
The checkpoint must state that nominal proof remains unauthorized until this
merge is synchronized.

### Task 10: Execute and publish the one-shot nominal lifecycle

**Files:**

- Create after successful live execution: one content-addressed nominal bundle
  under `artifacts/generated/v3b2-kind-calico/`.
- Modify: `docs/lab/V3-PROGRESS.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`

- [ ] **Step 1: Re-prove the live preconditions from synchronized main**

Run the exact synchronization assertions from Task 8 and the preflight command
from Task 9. Expected: the source now includes the accepted request-free public
checkpoint, `kil-v3-lab` is absent, and a new journal has a new run ID and
execution nonce.

- [ ] **Step 2: Execute one nominal lifecycle**

```bash
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src ../../.venv/bin/python \
  tools/v3b2_kind_calico.py nominal
```

Expected: exactly one instruction per fixed track, no retry, decisions
`permit / permit / deny`, statuses `200 / 200 / 403`, target markers
`1 / 1 / 0`, complete Kubernetes/policy/semantic joins, exact owned teardown,
unchanged foreign state and Docker context, and one content-addressed bundle
path printed only after publication re-attestation.

- [ ] **Step 3: Independently verify the public bundle and absence**

Run `colima list --json`, then call `view --bundle` with the literal path printed
by Step 2. Verify every `SHA256SUMS` entry, the result class
`intermediate_provisional_kind_calico_nominal`, `promotion_status=not_promoted`,
the six exclusions, three request identities, one attempt each, and owned
teardown before publication.

- [ ] **Step 4: Publish and synchronize V3B-2a without broader claims**

Commit the exact bundle, progress record, lineage source, and generated readers.
Run full validation and separate specification and security reviews, push, pass
public CI, merge, and prove exact local/remote `main` equality. Do not describe
the result as complete V3B-2 or complete NetworkPolicy validation.

- [ ] **Step 5: Open the V3B-2b planning gate**

Only after Step 4 succeeds, write a separate V3B-2b implementation plan that
maps every approved case to an exact fixture, outcome, evidence join, poisoning
classification, clean-lifecycle assignment, and campaign-index entry. V3C
remains closed until that campaign is accepted.

## Plan self-review record

| Approved design section | Plan coverage |
|---|---|
| 1. Decision and purpose | Scope split plus Tasks 9–10 implement request-free and V3B-2a nominal only. |
| 2. Scope and non-goals | Hard gates and Task 7 documentation tests preserve every claim exclusion. |
| 3. Environment and ownership | Tasks 1, 4, 6, 8, 9, and 10 pin content, isolate `kil-v3-lab`, and compare foreign state. |
| 4. Cluster topology | Task 2 renders the exact three-namespace, 60-object application set. |
| 5. NetworkPolicy | Tasks 2–3 render and attest deny-first policy and the closed edge graph. |
| 6. Consequential request flow | Tasks 4 and 6 bind readiness, intent, one attach, result, and no retry. |
| 7. Evidence contract | Tasks 1, 3–5 enumerate schemas, identities, sources, private/public projection, and dispatch. |
| 8. V3B-2a acceptance | Tasks 5–7 test the exact tuple, joins, teardown, checksums, verifier, and claim class. |
| 9. V3B-2b matrix | Deferred as a whole to the sequential V3B-2b plan after Task 10. |
| 10. Failure and recovery | Tasks 4–6 cover pre/post-intent failure, cancellation, recovery authority, and nonpromotable output. |
| 11. Teardown/publication | Tasks 4–6 fix the order; Tasks 9–10 independently verify absence before publication. |
| 12. Test strategy/gates | Every implementation task is RED/GREEN/commit; Tasks 8–10 impose review, CI, merge, and synchronization. |
| 13. Campaign acceptance | Campaign field closure is declared in Task 1; runtime validation is deferred to V3B-2b. |
| 14. V3C relationship | Task 10 leaves V3C closed pending accepted V3B-2b. |
| 15. Acceptance summary | The hard gates and resolved identities restate every confirmed design decision. |

- **Spec coverage result:** No V3B-2a requirement is unassigned. V3B-2b and
  V3C are explicitly deferred at their approved sequential gates rather than
  partially implemented here.
- **Closed identities:** The plan fixes the unique owned profile and cluster,
  application and system namespaces, CIDRs, Calico source bytes, digest-pinned
  Calico images, schema names, field sets, result class, promotion status, and
  claim exclusions.
- **No-replay coverage:** Journal tests, controller tests, recovery rules, and
  live gates all forbid resending after durable request intent.
- **Foreign noninterference:** Preflight allows well-formed running or stopped
  foreign profiles; every mutation is exact-name checked; before/after mismatch
  is sanitized and never repaired.
- **Type consistency:** `V3B2Profile`, `Command`, `OwnedIdentity`,
  `RecoveryPlan`, `WorkloadIdentity`, `ObjectIdentity`, `InventoryAttestation`,
  `SourceIdentity`, and `V3B2Controller` retain the same names and roles in all
  tasks.
- **Placeholder scan:** Runtime values are either literal, derived by named
  functions from committed inputs, or captured into the journal before use.
  No discovered resource becomes deletion authority.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
