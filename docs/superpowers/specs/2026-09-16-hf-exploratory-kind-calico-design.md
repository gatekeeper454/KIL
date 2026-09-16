# Exploratory HF action test in Kind/Calico

Date: 2026-09-16

Status: Approved by "approved proceed" on 2026-09-16 after the concrete scope
was written. The user authorized running the exploratory test when ready, with
platform-image provenance explicitly unverified. Implementation is now in
progress; approval alone establishes no runtime readiness or live result.

## Question and bounded experiment

Does the already accepted two-timescale administrative-action example retain
its permit / permit / deny behavior when placed in an isolated Kind/Calico
laboratory? This is one representative modeled HF cut point, not replay of all
eight historical phases or reproduction of an original exploit.

Reuse the harmless POST /consequential/admin fixture and three fixed tracks:
credential-policy baseline, signed-state-only, and signed-plus-local-reduction.
Use the same action and equivalent inputs across tracks. Expected decisions
are permit / permit / deny, HTTP results 200 / 200 / 403, and target markers
1 / 1 / 0. These expectations are hypotheses, not promised results.

## Alternatives and selected direction

Recommended: a separate, explicitly exploratory Kind/Calico lifecycle and
report. It exercises the desired substrate without modifying the strict
acceptance verifier or disguising evidence gaps.

A repeat local-Envoy run is smaller but does not answer the cluster question;
do not silently substitute it. Disabling strict-controller proof checks would
blur safety and acceptance boundaries; do not add a bypass switch to that
controller.

## Retained safety controls

- Own only the absent kil-v3-lab profile and cluster. Bind their concrete
  identities before mutation; refuse any existing resource without established
  ownership. Preserve foreign profiles and the global Docker/Kubernetes context.
- Retain the pinned target versions and node request, vendored Calico bytes,
  application source/configuration commitments and verified KIL/Envoy content
  requirements. The omission concerns independent platform-image provenance,
  not arbitrary application software or mutable-profile substitution.
- Use the established single-node target with 4 CPUs, 8 GiB memory and 60 GiB
  data disk, no host mounts, no published application endpoint and no real
  credentials. Do not use production services or historical exploit payloads.
- Retain default-deny and explicit same-track policy edges. Record the applied
  policies and observed application readiness before authorizing the request.
  Applied policy objects alone are not proof of policy enforcement or no bypass.
- The consequential request originates in the in-cluster one-shot driver,
  through Envoy to authorization and the harmless target. No host-originated
  consequential HTTP request, direct-target shortcut or caller-selectable track.
- Record durable request intent before each instruction. Send at most one
  instruction per track, three total; no automatic retry, repetition or failure
  matrix. An uncertain request outcome stops later instructions.
- Capture bounded evidence before exact owned teardown. An uncertain cleanup
  target means stop and report, not broad deletion or discovery-selected cleanup.

## Evidence and result interpretation

Keep the source revision, dirty-state refusal, target-profile hash, tool/version
observations, rendered/applied configuration commitments, run identity and owned
cluster/Pod/container incarnations. An exploratory source can be a reviewed
clean local checkpoint; it need not claim synchronized public-main acceptance.

Record reported platform image references/IDs as observations only. Explicitly
state that their independently expected manifest/config identities have not
been admitted; no platform-image receipt or implied matching assertion.

For each track join driver, Envoy, authorization decision and target evidence
by run, fixed track, request ID and container incarnation. A permit requires
its decision, HTTP 200 and exactly one target marker. A policy denial requires
its deny decision, HTTP 403 and no matching target marker in a complete frozen
target source. Missing/truncated evidence, container replacement or ambiguous
transport is inconclusive, not a successful denial. Unexpected complete evidence
is reported as an unexpected result, never corrected through a retry.

Produce a private exploratory report and source checksums, not an accepted
V3B-2/V4 bundle or a publication-verifier input. The report must say:
"Exploratory local Kind/Calico result; platform-image provenance unverified;
full Kind/Calico acceptance not established." Preserve the accepted local-Envoy
result and all existing strict completion flags and lifecycle deferrals.

No claim of historical HF prevention, full incident execution, complete
NetworkPolicy/no-bypass validation, repeated reliability, performance or V3C.

## Readiness and ordered next steps

1. Review this concrete experimental scope before implementation planning.
2. Plan and implement a separate small exploratory lifecycle/evidence path;
   specify exact commands, byte/time limits, retained files, recovery and tests.
   Reuse safe existing units, but do not weaken or call the strict launcher as
   though it already supports this scope.
3. Verify intent-before-instruction, no retries, foreign-state preservation,
   scoped teardown and evidence joins with test-owned observations. Independent
   specification and quality review precede any live mutation.
4. Establish a clean reviewed local source, content-verified tools/application
   inputs and an absent owned profile; inventory foreign state read-only.
5. Complete a request-free setup/evidence/teardown rehearsal. This is readiness
   evidence, not enforcement. Failure stops progression to requests.
6. From a fresh owned lifecycle, run the single three-track action once under
   the user's run-when-ready authorization; retain results and tear down.

Current read-only checks found kil-v3-lab absent and two stopped foreign
profiles. The worktree lacks .tools; its HEAD differs from origin/main and
contains documentation changes. The existing strict launcher would refuse its
source preflight. Two controller-boundary guard tests passed and confirm the
unchanged sixteen deferred lifecycle methods; they do not establish exploratory
or strict runtime readiness. No launch command is ready to invoke this design.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
