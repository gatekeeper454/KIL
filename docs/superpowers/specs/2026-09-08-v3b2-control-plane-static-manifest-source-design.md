# V3B-2 Control-Plane Static-Manifest Source Design

**Date:** 2026-09-08

**Status:** Recommended disk-manifest approach approved; written specification
pending review

**Parent design:** `2026-09-06-v3b2-kind-calico-validation-design.md`

## 1. Decision and purpose

V3B-2 will authenticate the effective on-disk kubeadm manifests for
`kube-apiserver` and `kube-controller-manager` on the exact owned
`kil-v3-lab-control-plane` node. Those two bounded sources close the remaining
filesystem-conditional CA-volume input without treating API mirror-Pod mounts
as their own expected authority.

The design does not predict the published Kind image filesystem before cluster
creation. Kind v0.32.0 source inherits mutable Debian/package inputs, and the
currently retained node-image evidence has no pathname inventory. A complete
OCI-layer reconstruction would be stronger pre-creation evidence but would add
platform-index, layer, whiteout, hardlink and symlink semantics that are not
needed to prove kubeadm's effective output in this fixed local laboratory.

## 2. Scope and claim boundary

The new source proves only that:

1. two exact manifest files were read from the identity-bracketed owned node;
2. each file has a closed, source-valid configuration for the fixed profile;
3. its conditional CA mounts are a subset of kubeadm's five pinned candidates;
4. the corresponding API mirror Pod agrees with the validated disk source after
   pinned kubelet/API defaulting; and
5. all retained identities and source commitments reconstruct during replay.

It does not prove the historical root filesystem, the reason a conditional path
existed, package provenance, certificate contents, image realization, container
status, readiness, availability, application completion, V3B-2 completion or
V3C authorization. Raw manifests stay private. Completion flags remain false.

## 3. Capture timing and ownership

Capture occurs immediately after `cluster_create` has established the exact
owned node container and `kube-system` cluster incarnation, and before image
loading, Calico apply or application apply. It is a required cluster-create
postcondition, not a preflight input.

The closed observation sequence is:

1. inspect `kil-v3-lab-control-plane` through the isolated Docker endpoint;
2. read `/etc/kubernetes/manifests/kube-apiserver.yaml` from the literal
   64-lowercase-hex container ID;
3. read `/etc/kubernetes/manifests/kube-controller-manager.yaml` from that same
   ID; and
4. inspect the named owned node again.

Both inspections must agree exactly on container ID, requested digest-pinned
Kind image, realized image config ID, owned cluster/name/role labels and running
state. The source binds the `kube-system` namespace UID already established for
the cluster incarnation. No current Docker context, discovered container name,
Pod field, foreign profile or caller-provided path can select a target.

Only `kil-v3-lab` may be started, stopped or deleted. These reads neither query
nor mutate another Colima profile. The exact Docker endpoint and private
`DOCKER_CONFIG` remain bound to the owned profile.

## 4. Closed command and source format

The command builder admits only these two non-mutating argv forms:

```text
docker exec <owned-64hex-id> /bin/cat -- /etc/kubernetes/manifests/kube-apiserver.yaml
docker exec <owned-64hex-id> /bin/cat -- /etc/kubernetes/manifests/kube-controller-manager.yaml
```

There is no shell, wildcard, relative path, stdin or arbitrary component name.
Each stdout is at most 1 MiB; stderr is bounded separately. Nonzero return,
truncation, invalid UTF-8 or extra output framing fails the source gate.

Each file must be one YAML document with no aliases, custom tags or duplicate
mapping keys. The parser accepts JSON-compatible scalar/container types only,
then validates a closed `v1/Pod` root. The private source record retains:

- schema version and run identity;
- cluster-incarnation UID and owned node container/config identities;
- ordered before/read/read/after raw observations;
- component, literal path, byte count and SHA-256 for each manifest;
- canonical semantic digest for each parsed Pod; and
- strict false runtime/application completion flags.

The whole source record is capped at 4 MiB. It is written with the existing
private no-follow, exclusive, mode-0600, flush/fsync and atomic-publication
rules. Its digest is bound to a terminal journal event before any later
mutation. Replay uses retained bytes only; it never repairs or replaces a
committed source from a live node.

An interrupted or invalid capture cannot authorize image load or apply work. A
fully persisted source with a missing terminal may be revalidated and have only
its already-determined terminal recovered. Otherwise the lifecycle becomes
teardown-only; recovery does not recollect manifests.

## 5. Conditional CA-volume authority

Kubernetes v1.36.1 fixes these candidate path/name pairs:

| Path | Volume and mount name |
|---|---|
| `/etc/pki/ca-trust` | `etc-pki-ca-trust` |
| `/etc/pki/tls/certs` | `etc-pki-tls-certs` |
| `/etc/ca-certificates` | `etc-ca-certificates` |
| `/usr/share/ca-certificates` | `usr-share-ca-certificates` |
| `/usr/local/share/ca-certificates` | `usr-local-share-ca-certificates` |

For each component, the disk validator derives the conditional subset only
after proving that every selected pair uses its literal name and path,
`readOnly: true`, and hostPath `DirectoryOrCreate`. Missing candidates are
allowed; duplicates, renamed paths, unexpected candidates, partial
volume/mount pairs and type drift fail. Final volumes and mounts follow kubeadm's
lexicographic name ordering.

Unconditional volumes/mounts and every other manifest field come from pinned
verifier-owned expectations, not from the disk candidate. API-server always has
`ca-certs` and `k8s-certs`; controller-manager also has `kubeconfig`. The disk
source selects only the five-way conditional subset. Tests cover all 32 subsets
for each component so no likely Debian layout becomes an unreviewed constant.

## 6. Disk-to-API transformation

Separate pure validators handle the two stages:

- `ControlPlaneManifestSourceProof` authenticates the bracket, raw bytes,
  closed disk Pods, fixed producer configuration and conditional subset.
- The API-server and controller-manager mirror configuration proofs retain and
  reconstruct both exact `RuntimeOwnershipProof` and the source proof, then
  compare the sole API mirror with an independently transformed expectation.

The transformation adds only pinned kubelet/API behavior: owned `nodeName`,
file-source/mirror/hash/seen metadata, five-field Node ownership, generation and
API metadata, file-source toleration, priority/default serialization and other
reviewed static-Pod defaults. It never copies arbitrary API fields into the
expected document. `config.seen` is syntax-checked without freshness authority;
opaque config/mirror hashes remain ownership joins unless a later proof
independently recomputes them.

API-server address fields must still bind to the same retained owned-Node
InternalIP rule used by etcd. Any other dynamic input needs its own retained
source; the disk manifest cannot silently widen the fixed profile.

## 7. Failure handling and replay

The gate fails closed on identity drift, command drift, missing/extra source,
oversize bytes, YAML ambiguity, source digest mismatch, malformed fixed fields,
unapproved conditional mounts, incomplete pairings or disk/API disagreement.
Failure records the bounded diagnostic and allows only exact owned teardown,
absence proof, foreign-state comparison and nonpromotable publication.

No failure authorizes changing a foreign profile, switching Docker context,
recreating a cluster, rewriting a manifest or repairing candidate state. A
later successful live run must start with a fresh run ID and absent owned
profile.

## 8. Test and review gates

Implementation is test-first and split into three sequential tasks:

1. closed command/source proof and journal/replay wiring;
2. kube-apiserver disk/API configuration proof; and
3. kube-controller-manager disk/API configuration proof.

Tests must cover command injection and scope, identity changes at every bracket,
byte limits and hashes, duplicate YAML keys/tags/aliases/documents, missing and
extra roots, all 32 conditional subsets, mismatched pair/order/type/readOnly,
source reconstruction/forgery, disk/API coordinated tampering, dynamic-address
mismatch, arbitrary status retention and strict false flags. Lifecycle tests
prove source completion precedes image load/Calico/application mutations and
that recovery never recollects or repairs source bytes.

Each task receives independent specification and quality review. Focused and
combined platform tests must pass before the next task. Full repository tests,
request-free execution, nominal execution and publication remain later gates;
this design alone does not authorize live execution.

## 9. Primary sources

- [Kubernetes v1.36.1 control-plane volumes](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/controlplane/volumes.go)
- [Kubernetes v1.36.1 static-Pod utilities](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/util/staticpod/utils.go)
- [Kubernetes v1.36.1 control-plane manifests](https://github.com/kubernetes/kubernetes/blob/v1.36.1/cmd/kubeadm/app/phases/controlplane/manifests.go)
- [Kubernetes v1.36.1 kubelet file defaults](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/config/common.go)
- [Kubernetes v1.36.1 mirror client](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/pod/mirror_client.go)
- [Kind v0.32.0 base image](https://github.com/kubernetes-sigs/kind/blob/v0.32.0/images/base/Dockerfile)
- [Kind v0.32.0 node-image build](https://github.com/kubernetes-sigs/kind/blob/v0.32.0/pkg/build/nodeimage/buildcontext.go)

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
