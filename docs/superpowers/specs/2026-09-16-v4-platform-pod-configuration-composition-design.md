# V4 platform Pod configuration composition

Date: 2026-09-16

Status: Written specification approved by the user on 2026-09-16. Approval
authorizes implementation planning for this static configuration-only slice;
it does not authorize live execution or any broader completion claim.

## Purpose and claim boundary

Compose the existing platform configuration validators into one reconstructable
proof that exactly ten owned platform Pod incarnations satisfy their respective
configuration contracts in the same retained runtime inventory. This is the
first slice of the all-ten-platform-Pod configuration/image/status/readiness gate,
not completion of that gate.

The aggregate adds coverage and authority continuity, not stronger component
semantics. It does not certify effective platform image realization, Pod status,
readiness, availability, observation freshness, mounted configuration contents,
certificate contents, historical filesystem provenance, or application behavior.
All existing limitations of the component validators remain in force, including
the scheduler/etcd API-output comparison's narrower source boundary.

No live calls, collector changes, controller lifecycle integration, journal or
checkpoint changes, inventory/publication schema changes, or completion changes
are included. The existing sixteen deferred lifecycle tests remain deferred.
Overall runtime/application completion, V4 completion and V3C remain unclaimed.

## Selected approach

Use an explicit, typed aggregate over existing proofs. It retains the proofs
and reconstructs every dependency before checking same-source joins and exact
coverage. Do not copy component configuration factories or introduce a generic
plugin registry.

Two alternatives were considered: a single configuration/image/status adapter
would couple several as-yet-undesigned authorities; live validation would add a
separate authorization and evidence boundary. Both remain later work. A small
configuration aggregate provides a reviewable foundation without promoting
configuration evidence into runtime evidence.

## Interface and retained records

Add `src/kil/v3b2_platform_pod_configuration.py` with public names
`PlatformPodConfigurationError`, `PlatformPodConfigurationBinding`,
`PlatformPodConfigurationProof` and `validate_platform_pod_configuration`.

The keyword-only validator accepts `ownership` and these nine explicit inputs:

| Input | Exact proof type | Pods | Ownership path |
| --- | --- | ---: | --- |
| `calico_node` | `CalicoNodeConfigurationProof` | 1 | `revision.ownership` |
| `calico_controller` | `CalicoControllerConfigurationProof` | 1 | `ownership` |
| `coredns` | `CoreDNSPodConfigurationProof` | 2 | `parent.ownership` |
| `local_path` | `LocalPathPodConfigurationProof` | 1 | `parent.ownership` |
| `kube_proxy` | `KubeProxyPodConfigurationProof` | 1 | `revision.parent.ownership` |
| `scheduler` | `SchedulerMirrorConfigurationProof` | 1 | `ownership` |
| `etcd` | `EtcdMirrorConfigurationProof` | 1 | `ownership` |
| `apiserver` | `KubeAPIServerMirrorConfigurationProof` | 1 | `ownership` |
| `controller_manager` | `KubeControllerManagerMirrorConfigurationProof` | 1 | `ownership` |

`ownership` must be exactly `RuntimeOwnershipProof`. Pre-driver ownership and
arbitrary lookalike/subclass proofs are not accepted in this slice. Retain all
ten input objects as named fields in the aggregate; preserve their existing
public APIs and heterogeneous component binding names.

The new frozen, slotted binding has exactly `component`, `namespace`, `pod_name`,
`pod_uid` and `pod_resource_version`. Its fixed component vocabulary is
`calico-node`, `calico-kube-controllers`, `coredns`, `local-path-provisioner`,
`kube-proxy`, `kube-scheduler`, `etcd`, `kube-apiserver` and
`kube-controller-manager`. Validate exact strings, reviewed namespace/component
pairs and existing UID/resourceVersion grammar using established helpers.

The frozen, slotted aggregate retains `bindings` as an exact tuple of ten exact
binding objects, canonically sorted by the five fields in their declared order.
It exposes `runtime_contract_complete` and
`full_application_contract_complete`, both constrained to the singleton `False`.
Do not add a readiness or overall configuration-complete boolean.

## Reconstruction and authority joins

Check exact dependency types and fixed tuple cardinalities before iteration or
raw decoding. Invoke existing dependency reconstruction; do not trust a frozen
record merely because its type is correct. Each component's complete retained
ownership must equal the explicit reconstructed `ownership`, including profile,
workload/run, rendered expectations, full `OwnedIdentity`, raw inventory bytes
and derived ownership bindings. Matching only cluster UID or Node ID is
insufficient. Independently valid inventories differing only in whitespace or
status cannot be mixed.

Require byte equality between the Calico source/projection pair retained by
`calico_node.revision` and that retained by `calico_controller`. Their existing
validators remain responsible for each pair's semantics. Require equality of
the complete reconstructed manifest source retained by `apiserver` and
`controller_manager`, not merely equal disk document subsets. Existing mirror
validators retain responsibility for source run, complete identity, requested
Kind image and optional full-profile joins. Minimal source contexts remain
accepted under their current contracts.

Normalize only already-validated component bindings into the new five-field
projection. Never normalize candidate configuration or derive expectations
from candidate Pod commands, images, annotations or status.

Independently derive the expected platform Pod set from the reconstructed
ownership: the CoreDNS, Calico controller and local-path Deployment bindings,
the two daemon Pod bindings and the four static Pod bindings. This must yield
exactly ten unique namespace/name pairs and ten distinct Pod UIDs, with the
component multiplicities in the table. Compare the projected component proofs
to that set using component, namespace/name, UID and resourceVersion. Require
one corresponding raw Pod incarnation for each expected identity; do not count
application Pods or unrelated retained objects as coverage. Existing ownership
validation governs inventory closure; do not broaden its accepted object set.

The aggregate constructor recomputes these joins and the full binding tuple
from its retained dependencies, rejecting altered, omitted, duplicate, reordered
or forged bindings and forged nested dependencies. The validator and constructor
use the same computation path. Expected malformed evidence errors are wrapped
as `PlatformPodConfigurationError` with exception chaining; do not catch all
exceptions or hide programming defects.

## Tests and acceptance

Add `tests/test_v3b2_platform_pod_configuration.py`. Build a test-owned combined
inventory with independently specified component observations, pinned Calico
source/projection and authenticated manifest source. Existing test fixtures may
supply surrounding ownership scaffolding, but production expected-spec factories
must not manufacture the observed Pod configurations. All nine component proofs
must validate against this same inventory before exercising the aggregate.

Establish failing tests before implementation. Cover exact ten-Pod acceptance,
two CoreDNS incarnations, deterministic ordering, retained dependency fields,
constructor replay and strict false flags. Reject wrong/missing dependency types,
subclasses, forged nested proofs and binding count/type/identity drift. Exercise
independently valid cross-inventory mixes, including changed status and raw-byte
formatting, run/full owned identity/profile differences, unequal Calico pairs
and unequal manifest source records. Where an earlier component validator
necessarily rejects a mutation, distinguish that failure from aggregate join
rejection rather than claiming independent validity.

Mutate component configurations and confirm existing validation cannot be
bypassed by aggregate construction. Verify that arbitrary Pod status remains
uninterpreted when accepted by the component contracts, provided every input
is reconstructed from that same changed inventory. No ready/running status is
required for configuration acceptance.

Run focused aggregate and adjacent configuration/ownership/source tests, then
independent specification and quality review during implementation. Run the full
repository validation and reader/diff checks before recording static acceptance.
Report total methods, actual successful methods and skips separately. No new
skip, weakened validator or terminal completion bypass is permitted.

## Next gates

User review of this written specification precedes the implementation plan.
After this slice is implemented and accepted, design independent platform image
authority and component-specific status/readiness semantics before composing
them. Neither this design nor its eventual tests authorize live execution.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
