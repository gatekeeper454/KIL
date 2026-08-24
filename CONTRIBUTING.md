# Contributing

The design is still being specified. Until the first design and implementation
plans are approved, contributions should focus on source provenance, factual
corrections, threat-model gaps, and testable requirements.

All claims must preserve the `observed`, `modeled`, and `validated` distinction
defined in the root README. Changes that use named KTP constructs must cite the
KTP RFC series and record any deviation from v2.0.0.

Run the repository checks before submitting a change:

```bash
make validate
```

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
