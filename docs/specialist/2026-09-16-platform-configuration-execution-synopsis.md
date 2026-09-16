# Platform configuration execution: environment and KIL actions

Date: 2026-09-16. Scope: static configuration composition for the future
Kind/Calico demonstration. This document distinguishes the observed execution
host, the configured target, and the synthetic observations used by tests.

## Actual execution host

Read-only host checks returned macOS 26.6.2, build 25G83, architecture arm64,
and Python 3.12.13. Work was performed in the externally managed detached linked
Git worktree at
`/Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL`.
The interpreter is the existing project virtual environment at
`/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python`.
The main checkout and other registered worktrees were not moved or removed.

No live Colima, Docker, Kind or kubectl operation is authorized by this slice.
The running state of any cluster/profile is therefore unknown from this run.
The software versions below are the pinned configuration, not fresh verification
of installed binaries or running container images.

## Configured target, not a newly launched lab

The committed `deploy/kind/v3b2-profile.json` and manifest renderer define:

| Item | Fixed target |
| --- | --- |
| Host profile | Darwin/arm64 |
| Colima/Lima | Colima 0.10.3; Lima 2.2.0 |
| Colima resources | 4 CPUs, 8 GiB memory, 60 GiB data disk; separate 20 GiB root disk |
| Docker CLI | 29.7.2 |
| Cluster | Kind 0.32.0, named `kil-v3-lab`, one control-plane Node |
| Node | `kil-v3-lab-control-plane`, Kubernetes 1.36.1 |
| Requested Node image | `kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5` |
| kubectl | 1.36.3 |
| Networking | Default Kind CNI disabled; vendored Calico 3.32.0 |
| IPv4 Pod range | `10.244.0.0/16` |
| IPv4 Service range | `10.96.0.0/16` |
| System namespaces | `default`, `kube-node-lease`, `kube-public`, `kube-system`, `local-path-storage` |
| Envoy application image | `docker.io/envoyproxy/envoy:v1.39.1`; runtime content identity is a separate contract |

The application design has three fixed namespaces: `kil-v3-baseline`,
`kil-v3-signed` and `kil-v3-local-reduce`. Each has driver, Envoy, authorization
and harmless-target roles. Its intended policy graph is default-deny plus DNS,
driver-to-Envoy, and Envoy-to-authorization/target paths on TCP 8080, with no
cross-track traffic or public application Service. These are renderer/design
facts; this configuration aggregate does not establish live policy enforcement.

## Exact inventory exercised by the new fixture

The test-owned combined List contains 57 records, not a comprehensive capture
of a live Kubernetes API. It deliberately contains only the retained objects
needed by these ownership/configuration contracts:

| Kind | Records |
| --- | ---: |
| Deployment | 12 |
| ReplicaSet | 12 |
| Pod | 22 |
| Node | 1 |
| DaemonSet | 2 |
| Namespace | 1 |
| ControllerRevision | 2 |
| ServiceAccount | 5 |

Ten Pods are platform Pods; twelve are application scaffolding. Nine Deployment
chains are application scaffolding (Envoy, authorization and harmless target in
each track); the three drivers are directly owned Pods. Three Deployment chains
are platform chains. The sole raw
Namespace record is the owned `kube-system` identity anchor; this List is not
evidence that only one namespace exists. No Service, ConfigMap or NetworkPolicy
record is certified by the new aggregate.

The exact platform Pod names and incarnation fields in the baseline fixture are:

| Component | Namespace / Pod | UID | resourceVersion |
| --- | --- | --- | --- |
| Calico controller | `kube-system/calico-kube-controllers-h000000010-p0000` | `pod-uid-10-0` | `320` |
| CoreDNS 1 | `kube-system/coredns-h000000011-p0000` | `pod-uid-11-0` | `322` |
| CoreDNS 2 | `kube-system/coredns-h000000011-p0001` | `pod-uid-11-1` | `323` |
| Local-path | `local-path-storage/local-path-provisioner-h000000012-p0000` | `pod-uid-12-0` | `324` |
| Calico Node | `kube-system/calico-node-a1b22` | `uid-pod-2` | `4` |
| Kube-proxy | `kube-system/kube-proxy-a1b23` | `uid-pod-3` | `5` |
| Etcd | `kube-system/etcd-kil-v3-lab-control-plane` | `uid-static-6` | `6` |
| API server | `kube-system/kube-apiserver-kil-v3-lab-control-plane` | `uid-static-7` | `7` |
| Controller manager | `kube-system/kube-controller-manager-kil-v3-lab-control-plane` | `uid-static-8` | `8` |
| Scheduler | `kube-system/kube-scheduler-kil-v3-lab-control-plane` | `uid-static-9` | `9` |

The four Deployment-backed platform Pods have no `nodeName` in this baseline;
configuration acceptance therefore cannot mean they are scheduled or ready.
The two daemon Pods and four static mirrors use host networking and the owned
Node name. The synthetic Node reports InternalIP `172.18.0.2` and Hostname
`kil-v3-lab-control-plane`. Those address facts are fixture inputs, not a
measurement of the user's network.

The fixture's complete owned identity is profile/cluster `kil-v3-lab`, Docker
endpoint `unix:///tmp/colima/kil-v3-lab/docker.sock`, kubeconfig
`/tmp/kil-private/kubeconfig`, cluster UID
`4b9f7ce2-9876-4f55-9a23-a9f00fbbde11`, and Node container ID consisting of 64
lowercase `a` characters. Its run ID is `v3b2-` followed by 64 lowercase `c`
characters. These are intentionally synthetic identifiers; the paths do not
demonstrate actual files or a usable Docker socket.

The exact requested platform container images in the accepted fixture are:

| Container family | Requested image |
| --- | --- |
| Calico CNI init containers | `quay.io/calico/cni@sha256:1cfc6aa9c4dad3575fdf36b78185fd7d68bcd4acc95778f8342be4fb6a851a14` |
| Calico Node and eBPF init | `quay.io/calico/node@sha256:f4fafd8ba641d96c5a91b01e5a519117d77d55dee789a3562ba3ad4aa125b36a` |
| Calico controller | `quay.io/calico/kube-controllers@sha256:adf0ac895796d21bca5383bc81c4cd2614be3a4308085b47857d7999f4cc2b1f` |
| CoreDNS | `registry.k8s.io/coredns/coredns:v1.14.2` |
| Local-path | `docker.io/kindest/local-path-provisioner:v20260521-9fb22683` |
| Kube-proxy | `registry.k8s.io/kube-proxy:v1.36.1` |
| Etcd | `registry.k8s.io/etcd:3.6.8-0` |
| API server | `registry.k8s.io/kube-apiserver:v1.36.1` |
| Controller manager | `registry.k8s.io/kube-controller-manager:v1.36.1` |
| Scheduler | `registry.k8s.io/kube-scheduler:v1.36.1` |

Calico Node has three init containers:
`upgrade-ipam`, `install-cni` and `ebpf-bootstrap`. Checking these spec fields is
not checking effective runtime image IDs or successful init completion.

## What KIL does in this slice

The independent fixture combines existing literal component observations by
identity, retaining only changes against each fixture's own sparse baseline and
rejecting conflicting observations. It builds simulated identity-bracketed
manifest observations from independent API-server/controller-manager disk
literals. These observations are passed to the existing validators; no real
Docker reads or disk captures occur here.

The new `validate_platform_pod_configuration` function reconstructs the nine
exact component proofs, requires their complete retained ownership/raw inventory
to agree, joins the shared Calico source/projection and the same validated,
identity-bound manifest-source record, and derives exactly ten unique platform
Pod incarnations from ownership.
Its canonical bindings contain component, namespace, Pod name, UID and
resourceVersion. Forged or mismatched dependencies must not bypass replay.
Same retained List bytes do not establish an atomic or temporally fresh live
Kubernetes snapshot.

Tests and read-only diagnostics invoke the aggregate on this synthetic fixture
and construct an in-memory typed proof. This is not a new live capture or a newly
published runtime checkpoint. The existing controller is not wired to this new
aggregate by this slice and was not modified.

The production change is confined to
`src/kil/v3b2_platform_pod_configuration.py`. The fixture and persisted regression
suite are `tests/v3b2_platform_configuration_fixture.py` and
`tests/test_v3b2_platform_pod_configuration.py`. Existing component validators,
the controller, collectors, journal, inventory schemas and authorization kernel
were not modified. The regression suite exercises both validation and retained
proof reconstruction, including independently valid alternate inventories/runs/
endpoints that must not be mixed, forged identities, malformed evidence,
configuration drift and prohibited completion flags. Immutable-profile and
Calico-content mutations are rejected at their existing earlier boundaries;
those contracts were not relaxed to create test inputs.

Test-scaffolding corrections did not demonstrate a production defect. The fixed
Kind-profile image cannot be turned into an independently valid alternate
profile; its mutation remains an earlier schema rejection. The independently
valid alternate Docker endpoint retains the required
`/kil-v3-lab/docker.sock` suffix; an initially malformed endpoint is separately
asserted as an earlier identity rejection. Runtime ownership comparisons use
the existing deployment/node subproofs, not a nonexistent aggregate bindings
field. No validator was loosened to make these inputs pass.

`runtime_contract_complete` and `full_application_contract_complete` remain
exactly `False`. Arbitrary Pod status can remain retained and uninterpreted.
Platform image realization and component-specific status/readiness composition
remain later gates.

This is infrastructure-evidence preparation for V4, not a newly executed
Hugging Face counterfactual or an end-to-end intrusion-prevention result. It
does not supply new demonstration HTTP allow/deny outcomes, target markers, or claims about
what would have prevented a historical incident. The separate authorization
kernel's baseline/signed/local-reduce comparison remains unchanged.

## Fresh static regression verification

Decision status: **Verified static regressions; final review pending**. The code
under regression is Task 3 revision `88d4b25`; its specification and quality
reviews preceded this preliminary evidence record. Final specification, quality
and holistic review are separate gates, not inferred from passing tests.

The approved existing Python interpreter above ran with
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src`. Actual unittest method results were:

| Gate | Total methods | Passes | Skips | Elapsed seconds | Exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| Adjacent component/revision/ownership/source suite, exact 18 modules in Task 4 Step 1 | 225 | 225 | 0 | 79.392 | 0 |
| Full `-m unittest discover -s tests -v` | 1612 | 1596 | 16 | 835.159 | 0 |

Both runs had zero failures and errors. The exact full footer was
`Ran 1612 tests in 835.159s` followed by `OK (skipped=16)`; `Ran N` includes
skips, so actual passes are `1612 - 16 = 1596`. Subtests are not additional
unittest methods. The full run was not interrupted or duplicated.

Full discovery used approved subprocess and `/dev/fd` access for existing
isolated tests. Complete stdout/stderr was captured by
`2>&1 | tee "$task4_full_log"` after `set -o pipefail`; the final execution
result was exit zero, so a successful `tee` did not mask a failed Python process.
The retained local log is `/private/tmp/kil-task4-full-unittest-XXXXXX.log`,
execution session `57577`. This temporary filename is literal on this host and
was exclusively created by `mktemp`; it is not a published evidence bundle.
Whole-log result scanning independently counted 1612 methods, 1596 successful
results, 16 skips and zero failure/error sections, and reviewed the remaining
diagnostic output. Two successful results are standalone `ok` lines after
intentional argparse rejection diagnostics; those diagnostics are not test errors.

All sixteen skipped names exactly match the unchanged `DEFERRED_METHODS` set in
`tests/test_v4_future_controller_gate.py`; its default-gate regression also
passed. They are existing V4 Future controller lifecycle deferrals, not new
skips introduced or enabled by this slice.

The full suite includes existing isolated unit, temporary subprocess and local
HTTP-server fixtures. These are regression checks, not a newly run live
Kind/Calico lab or Hugging Face demonstration. No live Colima, Docker, Kind or
kubectl operation, application demonstration request, push or publication was
performed. Platform coverage stays exactly ten incarnations; both completion
flags stay singleton `False`, and platform effective-image/status/readiness
authority remains outside this checkpoint.

All 79 tracked Markdown readers are regenerated and byte-checked for this
preliminary documentation handoff, with clean working and staged diff checks.
Task 4 Steps 1 and 2 record verification; Steps 3 and 4 remain pending review
and a separate bounded acceptance record.

## Next evidence gate

Design platform effective-image authority and component-specific status/readiness
composition. Only separately authorized live collection could establish what
cluster is actually running. This static configuration evidence does not authorize
launching the lab, issuing application requests, publishing results or declaring
V4 complete.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
