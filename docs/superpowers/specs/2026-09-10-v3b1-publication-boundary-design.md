# V3B-1 Publication Boundary Design

## Decision

KIL will publish on the strength of the accepted V3B-1 local-Envoy evidence.
V3B-1 is complete for its declared `local_envoy_boundary`; this does not claim
Kubernetes validation, historical prevention, production readiness, or
performance results.

The public milestone sequence becomes:

1. V1 — model invariants;
2. V2 — historical replay;
3. V3A — modeled signed-state authorization;
4. V3B-1 — complete local-Envoy validation;
5. Publication; and
6. V4 Future — the post-publication work previously labeled V3B-2.

## Scope

This is a publication-governance and presentation change. It updates current
status, roadmap, paper, and presentation surfaces so they agree on the new
boundary. It does not change authorization behavior, evidence bytes, accepted
run contents, schemas, or runtime controllers.

Existing V3B-2 implementation commits, plans, specifications, and specialist
lineage remain preserved under their historical names. Current-facing roadmap
text calls that work **V4 Future** and explicitly places it after publication.
No V3B-2 implementation code is merged into the publication branch merely to
support the renamed future milestone.

## Publication claim

The primary publication claim is narrow:

> KIL reproduced the intended permit / permit / deny decision tuple at an
> observed local Envoy enforcement boundary under the documented laboratory
> conditions.

The publication must retain these limitations beside the claim:

- the result is not proof that KIL would have prevented the historical Hugging
  Face incident;
- Kind, Calico, NetworkPolicy, cluster transport, repetition, and performance
  remain outside the accepted evidence boundary; and
- the accepted bundle's existing `not_promoted` value is not rewritten. Phase
  completion and publication eligibility do not retroactively change evidence
  recorded by the experiment.

## V3B-1 detail as additional validation

V3B-1 must not be reduced to a status badge. A visible additional-validation
section preserves the accepted run identity and the evidence readers needed to
audit it. At minimum it retains:

- run `v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94`;
- `permit / permit / deny`, HTTP `200 / 200 / 403`, and target markers
  `1 / 1 / 0`;
- one attempt per track and no retry;
- all nine authoritative service sources;
- exact teardown of all fifteen containers and six networks before
  publication;
- equal pseudonymous foreign-resource snapshots; and
- checksum and offline-presenter verification.

The concise publication narrative links to the detailed V3 progress record and
accepted evidence bundle rather than duplicating their full technical history.

## Authoritative surfaces

The implementation updates only current-facing publication sources:

- `README.md` for repository status and scope;
- `docs/lab/V3-PROGRESS.md` for the authoritative validation status and detailed
  V3B-1 evidence;
- the publishable paper and its README where their current-results or future-
  work language conflicts with this decision;
- the current milestone/timeline presentation represented by the supplied
  screenshot, once its repository source is resolved; and
- focused documentation tests that enforce the exact sequence, claim boundary,
  and retained V3B-1 detail.

Historical plans, specifications, evidence manifests, and lineage entries are
not bulk-renamed. Generated `.htm` readers are regenerated only from their
canonical Markdown sources.

## Verification and failure behavior

Publication remains blocked if any authoritative surface:

- calls V3B-1 Kubernetes-validated or historically preventive;
- places V4 Future before publication;
- calls the post-publication milestone V3B-2 in current-facing status text;
- omits the accepted V3B-1 run identity or its explicit limitations;
- changes the immutable evidence bundle; or
- has a missing or stale generated reader.

Focused documentation tests, reader freshness checks, link checks, and diff
hygiene run before commit and push. No Colima, Docker, Kind, Kubernetes, or live
network experiment is required for this publication-only change.

## Delivery

The change is developed on `codex/v3b1-publication`, reviewed as a bounded
publication delta, and pushed without altering the preserved V4 Future
implementation branch. Publication deployment or release promotion occurs only
after the repository publication checks pass.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
