# KIL Executive Cinematic Spine Design

## 1. Decision and scope

Create a separate, native, editable, 16:9 PowerPoint containing only the
14-slide executive spine of the KIL ambient-enforcement presentation. Preserve
the existing 30-slide technical deck. Do not change the live lab, protocol,
model, canonical scenario, evidence records, or validation status.

The user-supplied PowerPoints are visual references only. Their factual claims,
diagrams, typography, masters, and slide structures are not adopted as
authoritative source material. The approved direction is a new cinematic
causality system inspired by their use of strong visual metaphors and visible
action paths.

## 2. Communication job

By the end, an executive audience should understand why valid credentials can
no longer distinguish service from attack at autonomous speed, how KIL proposes
to make fresh bounded authority enforceable at consequential transport, where
that boundary changes the disclosed incident path, and why the claim remains a
bounded counterfactual pending further validation.

The central takeaway is:

> Ambient breach requires ambient enforcement: authority must remain a fresh,
> class-bound property of consequential traffic rather than a privilege
> inherited from a valid credential.

## 3. Narrative architecture

The deck contains exactly 14 slides and no technical drill-ins:

| ID | Executive claim | Primary graphical job |
|---|---|---|
| C | Ambient enforcement for agent-speed cybersecurity | Cinematic opening boundary with Mike Storm byline. |
| F1 | Cybersecurity has crossed from ambient threat into ambient breach | Service and attack trajectories visually converge until indistinguishable. |
| F2 | Credential validity cannot establish behavioral legitimacy | A valid credential crosses a checkpoint and explodes into novel machine-speed actions. |
| F3 | KIL makes fresh authority enforceable where actions become consequences | A luminous authority field interrupts one consequence-bearing trajectory. |
| F4 | KIL derives authoritatively and enforces at infrastructure speed | A slow orbital derivation loop feeds a fast linear enforcement rail. |
| 1 | The disclosed incident turns ambient breach into a concrete sequence | Establish the observed multi-stage incident rail and bounded counterfactual question. |
| 2 | A trusted worker became the foothold before the tested boundary | Show the foothold entering the worker, then approaching the first mediated boundary. |
| 3 | The first mediated divergence occurs at the cluster API request | Split the observed continuing path from the modeled KIL cutoff. |
| 4 | The observed path cascaded into multiple high-consequence branches | Expand the red trajectory into node, secrets, cross-cluster, mesh, token, and CI branches. |
| 5 | KIL tightens authority in motion without expanding KTP | Transform the branch explosion into a bounded cobalt authority corridor. |
| 6 | The lab reproduces one enforcement boundary, not the intrusion | Morph incident roles into request driver, Envoy, authorization service, and harmless target. |
| 7 | The same request yields modeled permit / permit / deny tracks | Present three large parallel trajectories ending in `200 / 200 / 403` and target `1 / 1 / 0`. |
| 8 | The evidence ladder prevents the story from outrunning the proof | Turn the three-track result into a rising evidence path from V1 through pending V3B-1 toward V4. |
| Z | Ambient enforcement makes trust an active property of traffic | Resolve the opening question and state the proposed KTP-extension boundary. |

Each slide must independently communicate its claim without animation. Speaker
notes provide a 20–35-second talk track and a direct transition to the next
slide.

## 4. Cinematic visual system

### 4.1 Visual grammar

- midnight navy and near-black establish the environment;
- crimson represents observed adversarial pressure and disclosed incident
  movement;
- electric cobalt represents KTP/KIL-derived authority, constraints, and
  transport boundaries;
- green is reserved for confirmed permit/arrival effects inside the declared
  model or evidence sequence;
- amber identifies modeled or pending states;
- graphite and desaturated silver represent neutral infrastructure.

Every color meaning also receives a visible text label. Evidence categories
must never depend on color alone.

### 4.2 Persistent story objects

The deck uses three recurring graphical objects:

1. a crimson adversarial trajectory that persists from F1 through Scene 4;
2. a cobalt kinetic boundary introduced at F3 and reused at Scenes 3, 5, 6,
   and 7; and
3. a white-to-cobalt evidence path that emerges in Scene 6 and resolves in
   Scene 8.

This continuity makes slide progression feel like one evolving visual system,
not fourteen independent infographics.

### 4.3 Composition rules

- One dominant visual metaphor per slide.
- Low visible word count; titles are complete executive claims.
- No dashboards, card grids, generic padlocks, hooded figures, fake telemetry,
  or decorative code.
- Large cinematic imagery may be raster; titles, evidence labels, results, and
  annotations remain editable PowerPoint objects.
- All artwork is embedded so the deck presents offline.
- Meaning-bearing change is communicated through slide-to-slide visual
  handoffs; the founder may later add PowerPoint transitions and timings.

## 5. Evidence and protocol controls

The deck preserves these confirmed boundaries:

- KTP supplies authoritative constructs and constraints.
- KIL is a proposed KTP extension profile that consumes signed, short-lived,
  composite KTP enforcement state.
- KIL may preserve or reduce KTP-authorized authority and cannot add authority
  or clear a KTP veto.
- Envoy produces the illustrated HTTP `200` or `403` transport effect; this is
  not a KTP wire decision.
- The disclosed incident is observed source material; KIL inputs and outcomes
  are visibly labeled modeled counterfactuals.
- The worker foothold precedes the currently tested Envoy boundary.
- A modeled upstream deny makes descendants conditionally unreachable; it does
  not prove multiple independent preventions.
- V3B-1 remains pending until an accepted evidence bundle exists.
- `Validated` remains reserved for accepted evidence at the relevant gate.

Every slide contains a `[Sources]` block in speaker notes. KTP claims cite the
KTP v2.0.0 repository and canonical citation metadata. Incident claims cite the
Hugging Face technical timeline. KIL model, lab, and evidence claims cite the
canonical local documents.

## 6. Deliverable and acceptance

Final output:

`docs/presentation/KIL-Ambient-Enforcement-Executive-Spine.pptx`

Acceptance requires:

- exactly 14 slides in the approved order;
- `Mike Storm` on the cover;
- complete speaker notes and `[Sources]` blocks on all slides;
- no overflow, clipping, accidental overlap, or broken image crops;
- coherent story when presented linearly without animation;
- visual inspection of every rendered slide and the full-deck montage;
- no change to the existing 30-slide deck or live lab; and
- clean repository tests relevant to documentation and presentation scope.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).

