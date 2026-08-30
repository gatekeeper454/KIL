# Project tools

Repository tools normalize public source material, validate evidence labels,
run deterministic replays, compare counterfactuals, and generate paper tables
and figures from canonical decision records.

`v3a_demo.py` runs the three infrastructure-fixed authorization tracks against
one normalized request, joins each decision to its forwarding outcome and
harmless target marker, and emits an atomic, content-addressed evidence bundle.
The bundle is labeled `modeled` with scope `process_contract_only`; it is not an
Envoy or Kubernetes validation.

```bash
PYTHONPATH=src python3 tools/v3a_demo.py \
  --output /absolute/path/to/v3a-runs \
  --implementation-version <full-git-commit>
```

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
