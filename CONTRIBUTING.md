# Contributing

KIL uses versioned design specifications, test-first implementation plans, and
explicit evidence gates. Contributions must preserve the approved scope,
include tests for behavior changes, update affected progress and publication
records, and append specialist lineage for substantive design, protocol,
experiment, or evidence changes. Source provenance, factual corrections,
threat-model gaps, and testable requirements remain welcome.

All claims must preserve the `observed`, `modeled`, and `validated` distinction
defined in the root README. Changes that use named KTP constructs must cite the
KTP RFC series and record any deviation from v2.0.0.

Run the repository checks before submitting a change:

```bash
make validate
```

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
