# Test strategy

The implemented project will separate five suites:

1. unit tests for deterministic arithmetic and evidence classification;
2. property tests for monotonicity, fail-closed behavior, and bounded values;
3. KTP v2.0.0 conformance vectors;
4. golden replay tests over versioned incident fixtures; and
5. live Kind integration tests proving transport allow/deny behavior.

Only the package smoke test exists during bootstrap. Behavioral tests will be
written before their implementation.

