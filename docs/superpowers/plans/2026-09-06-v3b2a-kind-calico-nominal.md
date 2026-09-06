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
- `kil.v3b2-journal.v1`: `schema_version`, `run_id`, `execution_nonce`,
  `source_commit`, `profile_sha256`, `phase`, `global_context_before`,
  `foreign_profiles_before`, `expected_objects`, `owned_identity`, and `events`.
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
The event grammar covers profile start/stop/delete, cluster create/delete,
Calico apply, application apply, readiness, driver start/cancel, evidence
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

`request_free()` creates fresh waiting drivers, captures readiness, sends no
stdin, cancels them, freezes empty ledgers, deletes the exact cluster, verifies
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
