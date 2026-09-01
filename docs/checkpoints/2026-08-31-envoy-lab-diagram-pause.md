# Envoy lab breach-model diagram — shutdown checkpoint

Date: 2026-08-31

## Current state

The founder requested a graphical diagram showing how the Envoy laboratory was
configured to model a consequential action from the disclosed Hugging Face
incident and how the KIL comparison changes the modeled result.

The deliverable is confirmed for both uses:

1. integration into the synchronized Presenter/Audience demonstration; and
2. a standalone presentation-quality diagram.

Three visual structures were compared. The founder selected the
**counterfactual-first** direction. The selected concept places the source-cited
incident sequence first, maps the first mediated worker-to-control-plane action
into the three isolated Envoy tracks, and ends with the modeled KIL cutoff and
conditionally unreachable descendants.

## Selected concept

The current concept contains three visual bands:

1. **Observed incident** — the disclosed worker foothold and downstream
   escalation remain the dominant narrative.
2. **Envoy lab model** — the same harmless normalized action runs through the
   credential-policy, signed-state-only, and signed-state-plus-local-reduction
   tracks. Each track shows the driver/Envoy frontend and Envoy/authz/target
   backend boundary.
3. **KIL counterfactual result** — the modeled comparison is `200 / 200 / 403`
   with target markers `1 / 1 / 0`; downstream phases are conditionally
   unreachable rather than separately detected.

The exact visual companion concept is preserved at:

- `docs/design-drafts/envoy-lab-counterfactual-first-concept.fragment.html`

Its SHA-256 digest at this checkpoint is:

`ccb30a51def275a27b75683f580c0c19b1846d3b3c6e5aa06964aedebb844bb6`

## Evidence boundary

- The incident sequence is source-cited observed context.
- The `0.95` local divergence and historical KIL cutoff are modeled.
- The `200 / 200 / 403` and `1 / 1 / 0` comparison is V3A modeled
  process-contract evidence.
- The V3B-1 topology is implemented and has request-free lifecycle evidence,
  but the accepted live enforcement result remains pending.
- V3B-2 Kind/Calico remains future work.
- The diagram must not imply that the original application foothold was
  mediated by the current Envoy rail.

## Approval status

The counterfactual-first macro direction is confirmed. The refined composition
was displayed for review immediately before shutdown, but final composition
approval and the formal written design specification remain pending. No
production demo page or laboratory behavior was changed during this design
turn.

## Resume gate

On resumption:

1. confirm or revise the refined three-band composition;
2. write and commit the formal diagram design specification;
3. self-review the specification and obtain founder approval;
4. create the implementation plan; and
5. implement the standalone diagram and the new or updated demo scene under
   test-first verification.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
