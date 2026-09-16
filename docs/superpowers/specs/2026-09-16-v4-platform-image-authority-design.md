# V4 independent platform image authority: source admission

Date: 2026-09-16

Status: The user approved the image-authority-first direction with "do next"
after the proposal recorded in T-326. This written design awaits user review.
Approval of the direction is not approval of unknown image identities or live
collection. This first sub-project admits independent expected identities;
observed-image composition and component-specific status/readiness follow it.

## Purpose and decomposition

The accepted configuration proof covers ten owned platform Pod incarnations,
but requested image strings do not establish effective content identities.
Before comparing runtime observations, establish an auditable verifier-owned
mapping from the ten fixed requested image references to independently sourced
content identities for linux/arm64.

The immediate deliverable is a reviewed source-admission receipt and retained
content-addressed descriptor evidence, not a new runtime proof. Do not implement
a platform image validator against guessed config digests, caller-supplied
acceptance tables, candidate Pod status or the candidate Node's image store.

The subsequent sequence is explicit: source admission, reconstructable platform
node/container image observations, then same-inventory image composition against
the accepted configuration proof. Component-specific status/readiness remains
a separate design and implementation cycle. These dependencies prevent image
membership, observation provenance and readiness from becoming interchangeable.

## Why this approach

Recommended: independently admit fixed expectations before designing their
runtime observation adapter. This resolves the missing authority rather than
building an adapter whose acceptance table comes from the candidate evidence.

Status/readiness-first would leave image content authority unresolved. A single
image/status/readiness adapter would couple independently sourced expectations,
runtime reference representations and component-specific state semantics.
Neither alternative is selected. Do not generalize the existing two-role
KIL/Envoy node-image API or weaken the legacy inventory representation contract.

## Fixed coverage domain

These are verifier-owned expected placements, not a set inferred from candidate
status arrays. Exact Pod names, UIDs and resourceVersions remain supplied by the
reconstructed configuration proof at the later observation/composition gate.

| Component | Container placement | Container name | Placements | Authority family |
| --- | --- | --- | ---: | --- |
| calico-node | regular | calico-node | 1 | calico-node |
| calico-node | init | upgrade-ipam | 1 | calico-cni |
| calico-node | init | install-cni | 1 | calico-cni |
| calico-node | init | ebpf-bootstrap | 1 | calico-node |
| calico-kube-controllers | regular | calico-kube-controllers | 1 | calico-kube-controllers |
| coredns | regular | coredns | 2 | coredns |
| local-path-provisioner | regular | local-path-provisioner | 1 | local-path-provisioner |
| kube-proxy | regular | kube-proxy | 1 | kube-proxy |
| kube-scheduler | regular | kube-scheduler | 1 | kube-scheduler |
| etcd | regular | etcd | 1 | etcd |
| kube-apiserver | regular | kube-apiserver | 1 | kube-apiserver |
| kube-controller-manager | regular | kube-controller-manager | 1 | kube-controller-manager |

Total: thirteen container placements in ten Pods, using ten authority families.
Repeated CoreDNS and Calico placements do not create extra image descriptors.
Pause/sandbox images, ephemeral containers and application images are outside
this coverage and cannot compensate for a missing platform placement.

Requested references are the exact references already admitted by the component
configuration validators: the three digest-pinned Calico references from
`deploy/kind/v3b2-profile.json`, and the seven Kind-supplied Kubernetes, etcd,
CoreDNS and local-path tagged references listed in the accepted execution
synopsis. Preserve those requests; do not replace their configuration contracts
with new digest requests merely to simplify identity comparison.

## Independent source roots

Use the exact requested Kind image root already pinned in the profile:
`kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5`.
For each of the seven Kind-supplied families, the audit must demonstrate the
association between its fixed requested tag and retained image content through
that immutable artifact's bundled image metadata/content. A current public
registry lookup of the tag alone is insufficient: a mutable tag could have
changed since the pinned Kind artifact was built.

For Calico, start at each exact profile-pinned repository/digest reference.
Retain its descriptor bytes, verify their content hash, and select linux/arm64
through its verified index/manifest chain. The committed Calico source/projection
continues to govern which requested reference belongs to each placement.

For either root, identify the root media type from verified bytes. Do not assume
the root is an index, that it is a platform manifest, or that a config digest is
equal to either. Verify every descriptor digest and size on each admitted path.
Verify config bytes and platform fields; mismatched platform metadata fails.
Layer descriptors remain committed by their manifest, but this receipt does not
claim unpacked filesystem equivalence or that an observed container used them.

If a required tagged image's association cannot be established from the pinned
Kind artifact, stop source admission. Report the precise missing source edge;
do not silently substitute a mutable-tag lookup or candidate Node observation.
Selecting another independent source root requires a documented design change.
Source admission cannot be partial or label an unresolved row as accepted.

## Receipt and retained evidence

The source audit produces one finite, closed receipt with exactly ten canonical
family rows. Proposed artifact location is
`deploy/kind/v4-platform-image-authority.json`, with retained small descriptor/
config blobs under `deploy/kind/v4-platform-image-authority/blobs/sha256/` and
an audit Markdown record under `docs/specialist/`.

Each row records family, exact requested reference, source kind (Kind bundle or
Calico registry root), immutable source-root reference and digest, root media
type, selected linux/arm64 manifest digest/media type/size, config digest/size,
and evidence paths/hashes for the root-to-manifest-to-config and requested-tag
association. If the root is already the selected manifest, record that fact
without fabricating an index edge. Retain verified config bytes; do not promote
a registry digest header or a runtime inspection's id field into config authority.

The receipt header records its schema version, profile-source SHA-256,
configuration-base revision, platform linux/arm64 and audit evidence commitments.
Its checksum is computed only after source review; runtime callers cannot select
another receipt, override its rows or supply arbitrary allowed reference sets.
A later authority factory reads the one committed, reviewed receipt and replays
its retained hash/descriptor associations. That factory is not implemented by
this source-admission sub-project.

The implementation plan must freeze the exact closed JSON schema, decoder and
descriptor/config byte bounds and download/disk budgets before fetching bulk
artifacts. These are plan acceptance requirements, not permission for unlimited
downloads. Large node layers need not be committed, but their source association
must have retained reproducible audit evidence; inability to retain an adequate
commitment path fails admission rather than yielding a bare asserted table.

Source selection is verifier-owned; raw content is still untrusted parser input.
Reject duplicate JSON keys, duplicate families, missing/extra rows, out-of-scope
repositories, malformed digests/sizes, ambiguous platform selection, inconsistent
descriptor edges and evidence paths outside the fixed evidence directory.
Do not extract untrusted archives into the repository or invoke candidate image
contents. Any archive audit uses isolated temporary storage and bounded parsing.

## Runtime representations: constraint on the later adapter

The later image adapter must distinguish requested reference, registry/index
target, selected platform manifest, image config identity, CRI Image, CRI
ImageRef, CRI ImageId and Kubernetes public status imageID. They are not aliases
for one universal digest.

In the pinned containerd source, ContainerStatus begins with the container's
config identity and may replace Image with the first repository tag and ImageRef
with the first repository digest. It also returns a separate config ImageId.
ImageStatus exposes the local image ID and parsed repository references.
[containerd ContainerStatus](https://github.com/containerd/containerd/blob/v2.3.1/internal/cri/server/container_status.go),
[containerd ImageStatus](https://github.com/containerd/containerd/blob/v2.3.1/internal/cri/server/images/image_status.go).

Kubernetes passes the resolved image reference separately from the user's
request, maintains internal ImageID/ImageRef distinctions, and maps internal
ImageRef to the public Pod container status imageID. Consequently, observing a
public imageID does not by itself identify the selected platform config bytes.
[Kubernetes runtime conversion](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/kuberuntime/kuberuntime_container.go),
[Kubernetes public status conversion](https://github.com/kubernetes/kubernetes/blob/v1.36.1/pkg/kubelet/kubelet_pods.go).

These are checked source semantics, not fresh proof of the user's installed
containerd binary. The later observation design must attest the actual reviewed
runtime/version, reference ordering and schema; it cannot generalize the existing
Never-pull KIL/Envoy fallback rule to every platform pull-policy branch.

The future observation proof must retain complete run/owned identity/source
context and same-Node bracketing, bounded raw image/container observations and
exact configuration Pod/container incarnation joins. Candidate container IDs may
select inspection queries but cannot define expected image content. Runtime
container metadata must corroborate the owned Pod UID and container placement.
Missing evidence for exited/removed init containers is not inferred successful
image realization from a regular container's status or a source descriptor.
The command allowlist, quiet JSON schema and all reference branches belong to
that separate observation design after source admission, not this receipt.

## Failure and test boundaries

Before source admission, independently test hash/size/descriptor association and
platform selection against small test-owned index/manifest/config bytes. Candidate
fixtures must not be constructed by the production expected-authority factory.
Test valid direct-manifest and index paths, repeated placement references, and
wrong platform, substituted config, wrong size, broken hashes, absent tag
association, duplicate/extra/missing family and ambiguous selection rejection.

Do not patch a production acceptance digest to claim native artifact admission.
Synthetic hash-consistent fixtures establish parser/reconstruction behavior only;
the real ten-row receipt needs its own independently reviewed provenance audit.
No check of ready, running, restart count or terminated exit status belongs to
receipt admission. The existing configuration proof's completion flags remain
singleton False and its fourteen plan checkpoints remain accepted unchanged.

Acceptance requires the complete ten-row receipt, reproducible source paths,
retained hash-verified descriptor/config evidence, independently checked fixed
placement coverage and independent source/specification then quality review.
Record exact method results, reader/diff checks and lineage before a source
admission claim. A document or schema alone cannot claim actual image admission.

## Authorization and next checkpoint

This turn writes and reviews a design only. It performs no source artifact
download, live Colima/Docker/Kind/kubectl operation, runtime collection or request.
No production/test/collector/controller/journal/checkpoint/publication-schema
change is included. The sixteen deferred lifecycle tests remain deferred.
Runtime/application completion, readiness, effective observed images, V4 and V3C
remain unclaimed. The accepted configuration synopsis is not rewritten.

After written-design approval, create a source-audit implementation plan with
explicit artifact/network/byte/disk scope and evidence schema. Only a successful
independently reviewed source admission permits planning the subsequent platform
observation and image-composition adapter. Status/readiness comes afterward.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
