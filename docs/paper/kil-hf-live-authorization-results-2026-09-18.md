<!-- reader-layout: wide -->
# Local Trust Reduction at a Live Authorization Boundary

## Results of the KIL HuggingFace Incident (HF) Exploratory Test

**Author and creator:** Mike Storm, Distinguished Engineer\
**Date:** September 18, 2026\
**Edition:** Final results paper for the completed three-track exploratory experiment\
**Protocol baseline:** Kinetic Trust Protocol v2.0.0\
**Evidence classification:** Exploratory local Kind/Calico result; platform-image provenance unverified; full Kind/Calico acceptance not established.

## Abstract

The Kinetic Infrastructure Layer (KIL) separates signed authority state from the local conditions encountered when an action executes. This paper reports a completed live experiment testing whether a fixed administrative-action example retains its expected behavior in an isolated Kubernetes laboratory using Kind, Calico, Envoy, and KIL authorization. Three tracks issued the same harmless administrative POST: a credential-policy baseline, signed state alone, and signed state with local reduction. The complete run produced permit/HTTP 200/one target record, permit/HTTP 200/one target record, and deny/HTTP 403/zero target records, respectively. The denial carried the reason `insufficient_charge`, and Envoy recorded no upstream attempt. Each result joined the driver, authorization, Envoy, and target sources with bound runtime identities; complete source captures preceded teardown. Independent verification checked the sealed receipt's 1,354 files and confirmed the expected results and owned-resource cleanup. These observations support a narrow conclusion: the configured local reduction produced the expected denial at the tested live authorization boundary while the other two tracks permitted the fixture. The study contains one complete three-request run, uses configured local evidence, and does not establish historical incident prevention, repeated reliability, NetworkPolicy enforcement, platform provenance, or production readiness.

**Keywords:** infrastructure authorization; signed authority state; local trust reduction; KIL; KTP; Envoy; exploratory validation.

## 1. Research question and contribution

An authentic credential and an otherwise permissive policy can coexist with conditions under which an administrative action should be withheld. KIL explores an infrastructure boundary that consumes signed authority state and can reduce the authority available to a specific action using local evidence. The architectural motivation and its relationship to KTP are developed in the [KIL architecture manuscript](kinetic-infrastructure.md). This paper reports the new experimental result without changing that manuscript's earlier evidence record.

The question was specified before the live result: **does the accepted administrative-action fixture retain its permit/permit/deny behavior when placed in an isolated Kind/Calico laboratory?** The [approved experimental design](../superpowers/specs/2026-09-16-hf-exploratory-kind-calico-design.md) fixed the three tracks, request, expected status codes, and target counts. It also explicitly separated exploratory execution from full platform acceptance.

The contribution is a traceable live observation of that bounded comparison. It moves the example onto an actual Kubernetes substrate with an in-cluster driver and Envoy authorization path, rather than relying only on an offline decision or a simulated controller. **HF = HuggingFace Incident.** The repository uses this abbreviation for the selected modeled incident cut point. This experiment does not replay the original incident or all its phases.

## 2. System and decision model

KIL's proposed architecture has two timescales. An authoritative loop issues and refreshes signed state; an action-time loop consumes that state at an infrastructure boundary. Local reduction may withhold authority without creating authority beyond the signed state. The protocol lineage is KTP v2.0.0; its canonical attribution is [Chris Perkins, *Kinetic Trust Protocol (KTP): RFC Series*, v2.0.0, DOI 10.5281/zenodo.21938282](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

This experiment exercises the action-time consumption example. Signed state is a laboratory fixture, and local evidence is supplied by the server's versioned configuration. An operating telemetry pipeline and a continuously refreshing authoritative loop were not evaluated.

The three configured tracks were:

| Track | Authority input | Local-reduction behavior | Prespecified result |
|---|---|---|---|
| Credential-policy baseline | Matching lab credential and permissive fixture policy | Signed state is not required | Permit; 200; target count 1 |
| Signed state only | Matching credential and valid signed fixture state | Local reduction is not applied | Permit; 200; target count 1 |
| Signed state + local reduction | Matching credential and equivalent signed fixture state | Apply configured fresh local evidence | Deny; 403; target count 0 |

The baseline represents this fixture's limited credential-policy check. It is not a benchmark of every zero-trust product or authorization policy. The signed tracks use equivalent numerical authority inputs with track-specific state identifiers and audiences; they do not reuse an identical audience-bound token across namespaces.

### 2.1 Source-derived explanation of the denial

The [versioned instruction fixture](../../src/kil/hf_exploratory_case.py) sets signed charge to 80, the action threshold to 40, passive decay rate to 0, and validity to ten seconds. The [server configuration](../../src/kil/v3b2_manifests.py) supplies fresh local divergence of 0.9, a divergence threshold of 0.25, loss rate 25, exponent 3, and coupled loss 0.

For this above-threshold fixture, the [implemented arithmetic](../../src/kil/decay.py) gives:

```text
local_loss = 25 × (0.9 / 0.25)^3 = 1166.4
effective_charge = clamp(80 − 1166.4 − 0, 0, 80) = 0
effective_charge < action_threshold: 0 < 40
```

The [decision engine](../../src/kil/engine.py) adds `insufficient_charge` when effective charge is below the action threshold. This calculation explains the configured expected behavior; effective charge was not independently measured as live telemetry in this experiment. The observed authorization reason was `insufficient_charge`. The study did not estimate or calibrate the divergence threshold, loss rate, or exponent.

## 3. Experimental method

### 3.1 Laboratory and request path

The experiment used a fresh, owned, single-node Kind cluster inside an isolated Colima VM. The requested VM allocation was four CPUs, 8 GiB memory, and a 60 GiB data disk. The host was Darwin/arm64. Each track ran in its own namespace with an in-cluster one-shot driver, Envoy, an authorization service, and a harmless target service.

```text
in-cluster driver → Envoy → authorization decision
                         → target, only when permitted
```

Envoy's external authorization mechanism consults an authorization service before allowing a request to proceed. Its HTTP filter can reject an unauthorized request with HTTP 403. This is the transport mechanism used here, rather than a novel HTTP denial mechanism. [Envoy external authorization documentation](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/security/ext_authz_filter).

| Component | Recorded observation or requested input |
|---|---|
| Colima / Lima | Observed tool versions 0.10.3 / 2.2.0 |
| Docker CLI | Observed version 29.7.2; Docker daemon version unobserved |
| Kind | Observed tool version 0.32.0 |
| Kubernetes | Observed node kubelet version v1.36.1 |
| kubectl | Observed client version 1.36.3 |
| Node container runtime | Observed containerd version 2.3.1 |
| Envoy | Content-pinned application image selected from the v1.39.1 input |
| Calico | Requested v3.32.0 with pinned, vendored manifest inputs |

Observed versions and reported image identifiers are not an independently admitted platform-image provenance proof. The precise profile is preserved in the [versioned laboratory configuration](../../deploy/kind/v3b2-profile.json).

### 3.2 Fixed action and controls

The consequential action was a harmless `POST /consequential/admin` with an empty body. The same fixed method, path, lab credential, and request identifier were used across tracks. The driver had application retries disabled and sent one durable instruction per track. Signed-state inputs were generated immediately before their track's dispatch.

The instructions also contained fixed attacker-shaped lab headers for claimed issuer, local evidence, mode, track, and subject. These were part of the configured case; the local divergence used by the authorization fixture came from server configuration. This input case does not constitute a comprehensive header-injection test.

The applied configuration included default-deny policies and explicit same-track edges. Application readiness, object ownership, image bindings, selected Pod/container incarnations, Service allocations, and ready EndpointSlices were checked before dispatch. Merely applying NetworkPolicy objects does not prove their enforcement. No bypass matrix or direct-target adversarial probe was performed.

### 3.3 Evidence capture and completion rule

Each track had four sources: driver readiness/result records, authorization decisions, Envoy access records, and the target ledger. Before instructions, complete request-free captures established that application-result sources were empty. After a driver completed, the harness drained the same Envoy process, required listener refusal and four exact zero activity gauges, and collected bounded final source bytes. Two source reads had to agree, with the same bound Pod/container identity across capture.

A permit result required HTTP 200, a joined permit decision, and exactly one target record. A denial required HTTP 403, a joined deny decision, absent upstream execution in the Envoy record, and zero matching target records in the complete frozen target source. Missing, changing, truncated, or ambiguously joined evidence would be inconclusive rather than counted as a successful denial.

Envoy resolved the configured target Service, so the logged upstream address was its ClusterIP. The primary run bound that address to the exact original target Service allocation and continuously checked the nine expected Services' UIDs, addresses, and configuration. It also required the original target EndpointSlice and target Pod/container identity. Kubernetes Services expose a stable Service IP separately from their backend endpoints; treating every upstream log address as a Pod IP would misdescribe this path. [Kubernetes Service documentation](https://kubernetes.io/docs/concepts/services-networking/service/).

### 3.4 Development history and sample accounting

A complete request-free rehearsal preceded consequential testing. Recovery and harness compatibility work addressed actual SSH, Docker/image, registry-access, Kubernetes mount/readiness, and Envoy response-framing mismatches. These steps established execution and evidence readiness; they are not additional HF success observations.

An earlier partial action attempt dispatched one baseline instruction. It returned HTTP 200 and produced one target record, but its overall report remained inconclusive because the evidence validator incorrectly required a Pod-subnet upstream address despite the configured Service route. That attempt was retained and cleaned up. The corrected validator requires the exact bound target Service address; it does not accept an arbitrary address in the Service subnet. The failed attempt was not rewritten as a complete run or silently combined with later tracks.

The primary result below comes from a fresh run after that fix. Thus the documented action attempts comprise four consequential requests: one in the earlier partial attempt and three in the complete primary run. The partial attempt is disclosed as development history, not a reliability replicate. The final experiment remains one observation per track, performed sequentially in a shared single-node laboratory.

## 4. Results

**All three primary-run tracks matched the prespecified decision, HTTP response, and target count.**

| Track | Observed decision | HTTP status | Target records | Authorization reason | Envoy upstream |
|---|---|---|---|---|---|
| Credential-policy baseline | Permit | 200 | 1 | `baseline_permitted` | Yes |
| Signed state only | Permit | 200 | 1 | `permitted` | Yes |
| Signed state + local reduction | Deny | 403 | 0 | `insufficient_charge` | No |

There were exactly three durable instruction intents and three attempts in the primary run. Each driver result reported attempt count 1. The run reached `complete_capture`, returned status `complete` with no error, and classified each track as `expected`.

The denial's zero target count was supported by a complete frozen target source and a matching Envoy record with no upstream attempt. It was not inferred from HTTP 403 alone. In both permitted tracks, authorization, driver, Envoy, and target evidence joined by their expected decision identity, with one target record each.

| Track | Joined decision digest |
|---|---|
| Credential-policy baseline | `80f0ac0b7a8a8b9331579ddf681c1a5e1ee9e1198a6a7c9bfb24358a31a8dbea` |
| Signed state only | `906b624c770a5e966a21268f46a5f9cceb8fd0cbd01cf89700cd304ac44e4533` |
| Signed state + local reduction | `c132a2bc550a6cb54ee906d39a9a2c686f62122e9fee1a1d19668220391abdc2` |

Cluster removal, owned profile deletion, native-owned teardown, and final wrapper closure were verified. The read-only global-state comparison matched the original foreign state. No manual recovery was required for the primary run. Configuration and namespace directories remained explicitly recorded; native-owned teardown is not a claim that every associated filesystem directory was removed.

## 5. Interpretation and limitations

The result supports the configured mechanism at the tested boundary: the baseline and signed-state-only fixtures permitted the action, while the local-reduction fixture denied it for insufficient charge and did not execute the target. This is evidence that the selected comparison can operate through the live in-cluster path with joined source records.

The result does not establish that KIL would prevent the historical HF incident. It tests one modeled administrative-action cut point with a harmless target. No original exploit was executed, and no end-to-end incident sequence was reproduced.

The main limits are:

1. **Sample size and development selection.** One complete run contains one request per track. Engineering evolved through failures before the complete run. No repeated-run reliability, confidence interval, false-positive rate, or statistical treatment effect is reported.
2. **Configured evidence.** Local divergence and freshness were server-side fixture inputs. The experiment does not show detection of malicious behavior from operational telemetry or resilience against a compromised evidence producer.
3. **Scope of the comparison.** Three namespaces and modes form a controlled implementation example, not a randomized or blinded study. The baseline is deliberately narrow; superiority over production authorization products is untested.
4. **Platform acceptance.** Independent platform-image provenance remains unverified, and full Kind/Calico acceptance remains false. This exploratory receipt is not an accepted V3B-2/V4 publication-verifier bundle and does not promote the earlier accepted local-Envoy result.
5. **Enforcement coverage.** The applied policies and observed request path do not establish NetworkPolicy enforcement, all-route mediation, or no-bypass behavior. No lateral-movement, direct-target, or failure-injection matrix was executed.
6. **Performance and scale.** No end-to-end latency, throughput, saturation, production scale, or long-running two-timescale behavior was measured. Driver timestamps are execution records, not a performance benchmark.

These limits define the next research questions; they do not erase the observed three-track result. Repeated runs, independently validated telemetry, bypass probes, and admitted platform provenance would answer different questions and need their own experimental scope.

## 6. Evidence availability and reproducibility

The [machine-readable results extract](kil-hf-live-authorization-results-2026-09-18.results.json) accompanies this paper. It preserves the primary run's reported joined results, raw final source records and their hashes, source-capture bindings, completion fields, and receipt-manifest identity. It is an extract for checking this paper, not a substitute for the full private receipt or a platform acceptance attestation.

| Evidence identity | Value |
|---|---|
| Primary run | `v3b2-0e5499817224447843f17d437e9dda29d76be9f5f169281fa90245f194d79127` |
| Reviewed execution source | `b0d99415bde5ffdd3419b805a098b70555a53a7b` |
| Independently verified retained files | 1,354 |
| Independently verified retained bytes | 6,786,556 |
| SHA256 of canonical receipt manifest | `9914e920cc2796218e4392725f8777dc83f17a86d8b715a127426e10f8227968` |

The private receipt is retained under `.tools/hf-exploratory-private/hf-exploratory-0e5499817224447843f17d437e9dda29d76be9f5f169281fa90245f194d79127`. Its `report.json`, `synopsis.md`, journal, raw captures, command records, and `SHA256SUMS` were independently checked after native execution closed. Verification included bounded file reads, ownership and mode checks, no-follow handling, complete roster equality, file identity closure, and the three expected joined results. A checksum records byte integrity; it is not a hardware attestation or proof of platform trustworthiness.

The [specialist lineage](../specialist/KIL-KTP-SPECIALIST-LINEAGE.md) records preparation, actual failures, source corrections, complete rehearsal, partial action, and final action in entries T464–T466. The [recorded recovery/testing conversation](../transcripts/KIL-HF-residual-vm-recovery-transcript-2026-09-18.md) provides the saved task history through its stated export cutoff. The [approved design](../superpowers/specs/2026-09-16-hf-exploratory-kind-calico-design.md), versioned fixture, manifest renderer, native lifecycle, and decision arithmetic provide the implementation context. Reproducing the native experiment requires a separately owned laboratory and authorization; this paper does not launch another run.

## 7. Conclusion

The completed KIL HF exploratory experiment produced its specified permit/permit/deny behavior on a live Kind/Calico substrate. Baseline and signed-state-only requests each returned HTTP 200 and reached the harmless target once. Signed state with configured local reduction returned HTTP 403 for insufficient charge, recorded no Envoy upstream attempt, and left the complete target source empty.

The result is a verified implementation milestone for the fixed action-time example. Its value lies in the live execution path, joined evidence, explicit treatment of inconclusive attempts, and confirmed resource closure. It supports further evaluation of local authority reduction while keeping historical prevention, broader enforcement coverage, and production acceptance as open questions.

## References

1. Chris Perkins. *Kinetic Trust Protocol (KTP): RFC Series*. Version 2.0.0, August 14, 2026. DOI 10.5281/zenodo.21938282. [Canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
2. Mike Storm. [*Kinetic Infrastructure: Ambient Enforcement for Agent-Speed Cybersecurity*](kinetic-infrastructure.md). KIL architecture manuscript and prior local-Envoy evidence record.
3. KIL project. [*Exploratory HF action test in Kind/Calico*](../superpowers/specs/2026-09-16-hf-exploratory-kind-calico-design.md). Prespecified experimental question, hypotheses, and evidence limits, September 16, 2026.
4. KIL project. [Primary-run results extract](kil-hf-live-authorization-results-2026-09-18.results.json) and [specialist lineage](../specialist/KIL-KTP-SPECIALIST-LINEAGE.md), T464–T466. Recorded native evidence and completion verification, September 18, 2026.
5. Envoy project. [*External Authorization*](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/security/ext_authz_filter). Retrieved September 18, 2026; explanatory documentation, not a runtime-version observation.
6. Kubernetes project. [*Service*](https://kubernetes.io/docs/concepts/services-networking/service/). Retrieved September 18, 2026; explanatory documentation for Service and endpoint addressing.
