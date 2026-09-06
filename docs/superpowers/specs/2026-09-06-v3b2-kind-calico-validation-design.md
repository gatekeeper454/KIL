# V3B-2 Kind/Calico Cluster Validation Design

**Date:** 2026-09-06

**Status:** Approved in collaborative design review; implementation not started

**Depends on:** accepted V3B-1 public proof at
`fd3ce6bb24f5c63644c07cfe1e34b244f02ff617`

**Next phase:** V3C repetition and performance measurement, only after V3B-2
passes

## 1. Decision and purpose

V3B-2 moves the accepted V3B-1 semantic workload from a local Docker/Envoy
boundary into one isolated, single-node Kind cluster using Calico NetworkPolicy.
It preserves the three fixed comparison tracks and the in-network one-shot
request driver while adding Kubernetes object identity, namespace isolation,
policy enforcement, and exact cluster teardown to the evidence chain.

V3B-2 is split into two ordered sub-gates:

1. **V3B-2a nominal parity** proves that the exact `permit / permit / deny`, HTTP
   `200 / 200 / 403`, and target-marker `1 / 1 / 0` workload traverses the
   intended Kind/Calico topology once without retry.
2. **V3B-2b failure matrix** starts from a fresh reviewed lifecycle and exercises
   the closed policy, identity, state, availability, and evidence-failure suite.

V3B-2a must be accepted and publicly synchronized before V3B-2b may execute.
V3B-2b must pass before V3C may repeat or measure the cluster workload.

## 2. Scope and non-goals

V3B-2 establishes only a local single-node Kind/Calico laboratory boundary. It
does not establish:

- production Kubernetes readiness, capacity, availability, or performance;
- multi-node, multi-host, cloud, or service-mesh behavior;
- historical prevention of the Hugging Face incident;
- accuracy of modeled local features for an undisclosed historical event;
- repeated reliability or latency distributions, which belong to V3C; or
- authority beyond the KTP v2.0.0 references and KIL extension boundary already
  approved for V3A and V3B-1.

The first approved V3 design described controller-to-Envoy localhost port
forwards. The later accepted V3B-1 in-network request-driver design supersedes
that consequential path. V3B-2 uses `kubectl` only as a control and evidence
channel; the host never originates the consequential HTTP request.

## 3. Environment and ownership boundary

The implementation reuses the resolved profile in
`deploy/kind/v3b-profile.json`:

- Colima 0.10.3 on Lima 2.2.0;
- Docker CLI 29.7.2;
- Kind 0.32.0;
- `kindest/node:v1.36.1` at the already pinned official digest;
- kubectl 1.36.3;
- Envoy 1.39.1 resolved to an immutable registry digest;
- Calico 3.32.0 from a vendored, checksummed manifest; and
- the content-identified KIL service image built from the reviewed source.

The implementation must version the current profile contract rather than
silently reinterpret its `local_envoy_boundary` scope. The V3B-2 profile adds
the Kind configuration, fixed CIDRs, vendored Calico identity, closed system
namespace inventory, and `kind_calico_boundary` evidence scope. V3B-1 profile
and verifier dispatch remain independently readable.

KIL owns exactly one Colima profile and one Kind cluster, both named
`kil-v3-lab`. The controller may start, stop, or delete only that exact profile
and may create or delete only that exact cluster through journal-bound commands.
Every other Colima profile, Docker context, Kind cluster, and Kubernetes context
is foreign state and must remain untouched.

Before any mutation, preflight must:

1. prove source is the exact reviewed, merged, synchronized public `main`;
2. verify locked tool bytes and version outputs;
3. prove `kil-v3-lab` is absent;
4. capture the closed foreign-profile inventory and global Docker context;
5. allow closed, well-formed foreign profiles to remain running or stopped,
   while refusing ambiguous inventory and never attempting to change them;
6. verify the node, Envoy, KIL, and Calico content identities; and
7. create the private lifecycle journal before the first owned mutation.

## 4. Cluster topology

The topology is one single-node Kind cluster with these application namespaces:

- `kil-v3-baseline`;
- `kil-v3-signed`; and
- `kil-v3-local-reduce`.

Each namespace contains exactly one fixed-track instance of:

- a waiting, readiness-capable one-shot request-driver Pod created fresh for
  each nominal run, failure case, or request-free readiness gate;
- an Envoy gateway Service and workload;
- an authorization Service and workload;
- a harmless target Service and workload;
- immutable ConfigMaps containing only approved public lab configuration;
- dedicated ServiceAccounts; and
- append-only decision and target ledgers on bounded ephemeral volumes.

The workload reuses the V3B-1 application and Envoy bytes. Kubernetes manifests
fix the track at deployment; request data cannot select or downgrade the track.
Every workload is non-root, drops Linux capabilities, disables privilege
escalation, uses a read-only root filesystem where compatible, has bounded
ephemeral storage and resources, and has no host mount, host network, host PID,
privileged mode, NodePort, LoadBalancer, or public host binding.

The Kind configuration disables its default CNI and fixes the Pod and Service
CIDRs before cluster creation. The controller installs only the vendored Calico
manifest whose bytes and image references match the reviewed content identity,
then waits for the closed Calico and node readiness inventory before applying
application namespaces or recording request intent.

## 5. NetworkPolicy contract

Default-deny ingress and egress policies must exist in all three application
namespaces before any application workload becomes ready. Explicit policy edges
permit only:

1. request driver to the same-track Envoy Service on TCP 8080;
2. Envoy to the same-track authorization Service on TCP 8080;
3. Envoy to the same-track target Service on TCP 8080; and
4. the minimum same-cluster DNS path required for fixed Service discovery.

There is no cross-track application traffic. Drivers cannot reach targets or
authorization services directly. Authorization services cannot reach targets.
Targets initiate no application traffic. No application Service is public.

Policies select exact namespace and workload labels. The controller persists a
canonical expected policy graph and a closed allowlist for Kind, Kubernetes,
Calico, and application namespaces. It rejects extra application namespaces,
workloads, Services, endpoints, ServiceAccounts, policy edges, or selector
ambiguity, and rejects system inventory outside that reviewed allowlist. Calico
node readiness, CNI identity, and applied policy inventory are attested before a
request intent can be recorded.

V3B-2a proves the closed policy inventory and the allowed nominal paths.
V3B-2b supplies the negative probes required to claim observed NetworkPolicy
blocking behavior.

## 6. Consequential request flow

For each track, the host controller:

1. attests aggregate workload and policy readiness;
2. starts a fresh one-shot driver through an exact `kubectl` operation;
3. reads its canonical readiness record;
4. persists a durable case and request intent in the private journal;
5. sends exactly one canonical instruction through `kubectl attach` stdin;
6. reads exactly one canonical terminal driver result; and
7. never retries after request intent, regardless of the observed outcome.

The consequential data path is entirely in cluster:

`driver -> Envoy -> authorization -> target or withhold`.

The controller never sends the HTTP request itself. It supplies control,
captures Kubernetes identity, freezes evidence, and performs exact teardown.

The implementation keeps a thin CLI separate from focused units for profile
and schema validation, manifest rendering, policy-graph validation, Kubernetes
inventory, lifecycle journaling/recovery, evidence collection, semantic joins,
public projection, and offline verification. Kubernetes and Colima commands are
constructed from closed typed records; no component accepts arbitrary command
fragments, current-context authority, or discovery-selected deletion targets.

## 7. V3B-2a evidence contract

The private manifest and journal bind, before mutation or request as applicable:

- source commit, execution nonce, run identity, and phase;
- locked tool hashes and versions;
- Colima profile and Kind cluster configuration digests;
- node image, Calico manifest, Envoy image, and KIL image digests;
- the before-mutation foreign-profile snapshot and Docker context;
- the expected namespaces, workloads, Services, ServiceAccounts, ConfigMaps,
  volumes, labels, policy graph, and request cases;
- the Kind cluster configuration and node-container identity, the
  `kube-system` namespace UID as the cluster-incarnation binding, and exact node,
  application-namespace, Pod, container, and Kubernetes object UIDs;
- realized image IDs, readiness state, Service endpoints, and policy inventory;
- one driver readiness/result pair and one request intent per track; and
- authoritative driver, authorization, Envoy, target, Kubernetes, and policy
  source locations.

Evidence collection must use bounded, no-follow reads where the host filesystem
is involved, closed canonical JSON, exact byte counts and SHA-256 digests, and
stable Kubernetes UID/resourceVersion or container identity checks before and
after each source read. Missing, replaced, duplicated, noncanonical, oversized,
or ambiguous evidence invalidates the affected run.

The public manifest exposes only safe, run-scoped identities. Foreign profile
names, host paths, execution nonces, credentials, signed state, private journal
content, and raw control-plane secrets are excluded. Foreign resources appear
only through pseudonymous before/after attestations.

V3B-2 uses `kil.v3b2-profile.v1`, `kil.v3b2-journal.v1`,
`kil.v3b2-private-manifest.v1`, `kil.v3b2-public-manifest.v1`, and
`kil.v3b2-campaign.v1`. The offline verifier dispatches V3B-1, V3B-2 run, and
V3B-2 campaign schemas explicitly and rejects hybrid field sets. The
implementation plan must enumerate each closed field set and its validator
before runtime code is written.

## 8. V3B-2a acceptance and claims

V3B-2a is accepted only when:

1. every pinned identity and canonical manifest matches the reviewed contract;
2. all three namespaces and every object have exact name/UID/digest bindings;
3. Calico and the closed deny-first policy inventory are ready before requests;
4. each track has exactly one request attempt and no retry;
5. the joined result is `permit / permit / deny`, HTTP `200 / 200 / 403`, and
   target markers `1 / 1 / 0`;
6. each permit joins one driver result, one KIL decision, an Envoy upstream
   response, and exactly one target marker with equal decision digests;
7. the denial joins one driver result, one KIL denial, Envoy no-upstream
   evidence, and zero target markers;
8. all Kubernetes, policy, source, and semantic joins are complete and valid;
9. exact owned teardown completes before publication;
10. before/after foreign-profile snapshots and Docker context are unchanged;
11. every `SHA256SUMS` entry verifies; and
12. the offline presenter rederives and accepts the bundle.

The proposed public bundle class is
`intermediate_provisional_kind_calico_nominal` with
`promotion_status=not_promoted`. It may be described as an accepted observed
intermediate Kind/Calico nominal-parity result. It may not be described as the
complete V3B-2 validation result, complete NetworkPolicy validation, repeated
reliability, performance, production validation, or historical prevention.

## 9. V3B-2b failure matrix

V3B-2b begins only at the exact reviewed public source that incorporates
V3B-2a. It is a closed campaign of immutable run bundles, not an assumption that
every case can safely share one cluster. Each run starts from a clean lifecycle,
uses the same topology and evidence contract, and binds unique request/case
identities from this ordered case set.

### 9.1 Policy-isolation probes

- cross-track driver to another track's Envoy is blocked;
- driver to same-track target bypass is blocked;
- unauthorized workload identity to authorization service is blocked;
- no cross-track Envoy, authorization, or target record appears; and
- no public Service or host-originated consequential path exists.

Each network denial requires the exact probe identity and destination, a closed
terminal connection result, the attested policy graph and Calico readiness, and
absence of a corresponding destination application record. An HTTP status alone
is not NetworkPolicy evidence.

### 9.2 State and authority failures

- absent and malformed state;
- incorrectly signed, expired, and not-yet-valid state;
- revoked and replayed state;
- wrong audience, subject, class, and action;
- immutable veto and KTP envelope violation;
- declared rare action; and
- attempted local authority increase.

### 9.3 Availability and evidence failures

- cold start and insufficient history;
- stale local evidence;
- false reduction and signed-state recovery;
- authorization timeout or unavailability;
- collector loss; and
- target-ledger conflict.

Expected permit, policy denial, fail-closed denial, or terminal nonpromotable
outcome is fixed per case before execution. The implementation plan must map
every case to an exact fixture and evidence join; it may not add live cases by
discovery.

Non-poisoning cases in the same approved group may run in one fresh cluster in
fixed order. A normal completed case may advance to the next unopened case. Any
topology poison, unexpected request result, evidence ambiguity, or recovery
anomaly terminates that run; its remaining cases remain `not_attempted`.

An unopened campaign case may later execute only in a new clean lifecycle with
a new run identity. This is continuation of the closed campaign, not retry of
the terminal case. Collector-loss, target-ledger-conflict, and any other case
whose expected behavior poisons evidence or topology execute in their own fresh
lifecycle. A canonical campaign index binds the reviewed case list to exactly
one terminal public bundle per case, records expected diagnostic failure bundles
as nonpromotable, and refuses duplicates or omitted cases.

## 10. Failure and recovery behavior

Before request intent, setup failure may produce only diagnostic evidence and
exact owned teardown. It does not authorize a consequential request. A later
attempt requires a fresh lifecycle and new run identity from an otherwise valid
reviewed source.

After case or request intent:

- the consequential request is never replayed;
- the case is never retried in that run;
- uncommanded drivers or probes are canceled without instruction;
- raw malformed or partial evidence is preserved privately and hash-bound;
- the public result remains nonpromotable unless every required join is valid;
  and
- mandatory evidence freeze and exact teardown continue.

Recovery authority is limited to bounded source reads and idempotent actions on
exact names, UIDs, container IDs, cluster identity, and profile identity already
committed to the private journal. Discovery-based deletion, wildcard deletion,
current-context deletion, foreign-resource repair, and foreign-profile mutation
are prohibited.

If owned teardown cannot prove the exact Kind cluster and `kil-v3-lab` profile
absent, the lifecycle remains active and publication cannot claim complete
teardown. If foreign state differs, KIL records a sanitized mismatch and does
not attempt restoration.

## 11. Teardown and publication order

The controller must:

1. stop or cancel every journal-bound driver/probe without replay;
2. quiesce Envoy before freezing authorization and target sources;
3. freeze all required application, Kubernetes, policy, and driver evidence;
4. verify frozen identities and construct semantic joins;
5. delete only the exact journal-bound `kil-v3-lab` Kind cluster;
6. verify the cluster absent;
7. stop/delete only the exact `kil-v3-lab` Colima profile;
8. verify the profile and every owned state path absent;
9. capture and compare the foreign-resource after snapshot; and
10. atomically publish the complete or calibrated failure bundle.

No result is publicly presentable before exact owned teardown and foreign-state
comparison complete.

## 12. Test strategy and implementation gates

Implementation is test-first and ordered:

1. **Pure contracts:** closed schemas, canonical manifest rendering, profile and
   cluster identities, object inventory, policy graph, case matrix, and public
   projection.
2. **Controller state machine:** fake-runner command sequences, intent ordering,
   no replay, crash boundaries, bounded evidence collection, recovery authority,
   exact teardown, foreign noninterference, and proof that every Colima command
   names only `kil-v3-lab`.
3. **Static workload security:** namespace and label closure, deny-first policy,
   non-root/read-only settings, resource bounds, no host mounts, and no public
   ports.
4. **Existing semantic components:** V3B-1 driver, authorization, Envoy, target,
   canonical evidence, and offline verifier compatibility remain green.
5. **Request-free live gate:** after code review, public CI, merge, and exact main
   synchronization, create a fresh cluster, prove readiness and policy inventory,
   send zero driver instructions and zero HTTP requests, freeze empty sources,
   and tear down exactly.
6. **V3B-2a live gate:** only after the request-free gate is published and
   synchronized, execute one newly authorized nominal lifecycle with no retry.
7. **V3B-2b live gate:** only after V3B-2a is published and synchronized, execute
   the closed failure campaign through its required clean lifecycles.

Every code or runtime publication requires focused tests, full repository
validation, generated-reader verification, public-boundary scanning, separate
specification and quality/security reviews, public CI, merge, and exact local /
remote main equality.

## 13. V3B-2b campaign acceptance

The V3B-2b campaign is complete only when its canonical index:

- covers every reviewed case exactly once;
- binds each case to its assigned run, source, fixture, expected outcome, and
  verified public bundle digest;
- proves every normal permit, policy denial, and fail-closed denial through its
  required semantic and policy joins;
- preserves expected collector/evidence failure bundles as explicitly
  nonpromotable diagnostics rather than relabeling them successful evidence;
- records no retry for any case or request identity;
- proves exact teardown and foreign noninterference for every lifecycle; and
- passes checksums, offline verification, claim-language review, public CI, and
  exact main synchronization.

The campaign may support a calibrated complete V3B-2 cluster-boundary claim only
for the behaviors whose evidence joins are complete. Expected diagnostic-failure
cases prove the controller failed closed; they do not become positive
enforcement evidence. The immutable V3B-2 campaign remains `not_promoted`;
V3C may later publish a separate promotion index only if its independent
repetition and measurement requirements pass.

## 14. Relationship to V3C

V3C starts only after V3B-2b produces an accepted complete campaign index with
the calibrated evidence limits above. It will define the thirty-repeat
functional protocol and the warm-up and measured latency protocol against the
accepted V3B-2 topology. V3C must have a separate design and implementation plan
and may not silently broaden V3B-2 claims.

## 15. Design acceptance summary

The approved design choices are:

- V3B-2 before V3C;
- V3B-2a nominal parity before V3B-2b failure matrix;
- one KIL-owned Colima profile and Kind cluster named `kil-v3-lab`;
- one cluster with three isolated fixed-track namespaces;
- in-cluster one-shot drivers and no host-originated consequential HTTP;
- deny-first Calico NetworkPolicy and a closed policy graph;
- exact Kubernetes plus V3B-1 semantic evidence joins;
- no retry after durable request intent;
- recovery limited to journal-bound KIL resources; and
- exact teardown and foreign noninterference before publication.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
