# Source register

| Source | Role | Evidence use |
|---|---|---|
| [KTP v2.0.0](https://github.com/nmcitra/ktp-rfc/tree/v2.0.0) | Primary protocol source | Existing constructs, wire semantics, conformance requirements |
| [Hugging Face technical timeline](https://cdn-avatars.qwak.ai/blog/agent-intrusion-technical-timeline) | Primary incident source | Historical actions, ordering, timestamps, disclosed outcomes |
| [Hugging Face incident disclosure](https://huggingface.co/blog/security-incident-july-2026) | Primary incident source | Scope, response, and public impact statements |
| Claude data export, conversation `9a53e1b5-61c4-4f86-ae36-049675efe6ba` | Primary ideation provenance | Original brief, KTP connection, KIL genesis, and artifact requests; not evidence for technical claims |

Retrieval date for initial review: 2026-08-24.

The technical timeline states that live credentials, internal hostnames, and
specific indicators were redacted or genericized. The project must not infer
missing values and label them `observed`.

Claims originating in brainstorming remain hypotheses until independently
supported. In particular, the early Claude description of a “7-dimensional
Context Tensor with 1,700+ signals” is preserved as historical wording and is
not adopted as a KTP v2.0.0 fact by this project.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
