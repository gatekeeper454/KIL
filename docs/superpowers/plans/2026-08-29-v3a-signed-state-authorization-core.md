# V3A Signed State and Authorization Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and demonstrate the KIL experimental Ed25519 composite-state envelope and the three fixed authorization tracks before introducing Envoy or Kubernetes runtime variables.

**Architecture:** V3A adds a strict `kil.q-state.v0` claims record, compact EdDSA JWS issuance and verification, and a pure authorization adapter that fixes its mode at construction. A reference gateway invokes a harmless target marker only after a permit, then writes a modeled process-contract bundle and a human-readable HTML view; this stage proves software contracts but does not produce a validated cluster result.

**Tech Stack:** Python 3.12.13, `cryptography==50.0.0`, compact JWS with Ed25519, existing deterministic KIL V1 kernel, JSON/JSONL, SHA-256, `unittest`.

---

## File map

- `requirements-lab.txt` — pins the optional laboratory cryptography dependency.
- `schemas/q-state-v0.schema.json` — publishes the experimental composite-state payload shape.
- `src/kil/q_state.py` — owns strict claims validation, Ed25519 JWS issuance, verification, binding, and conversion to the V1 `CompositeState`.
- `tests/test_q_state.py` — proves the claims and cryptographic failure behavior.
- `src/kil/live_authz.py` — owns fixed-track authorization evaluation and server-side fixture inputs.
- `tests/test_live_authz.py` — proves baseline, signed-only, local-reduction, and downgrade resistance.
- `src/kil/reference_gateway.py` — owns the process-level forward-or-withhold contract and proof join.
- `tests/test_reference_gateway.py` — proves a denied request never invokes the harmless target marker.
- `tools/v3a_demo.py` — executes the three-track case and emits visible JSONL/HTML evidence.
- `tests/test_v3a_demo.py` — proves the demo bundle and evidence-language boundary.
- `docs/lab/V3-PROGRESS.md` — records exactly what V3A implements and what remains unvalidated.
- `adapters/envoy/README.md` — freezes the HTTP adapter boundary to be implemented in V3B.

### Task 1: Strict experimental composite-state claims

**Files:**
- Create: `requirements-lab.txt`
- Create: `schemas/q-state-v0.schema.json`
- Create: `src/kil/q_state.py`
- Create: `tests/test_q_state.py`

- [ ] **Step 1: Write the failing claims tests**

```python
from dataclasses import replace
from decimal import Decimal
import unittest

from kil.q_state import QStateClaims


def claims(**changes):
    value = QStateClaims(
        schema_version="kil.q-state.v0",
        state_id="q-v3a-1",
        issuer="https://lab-issuer.kil.invalid",
        subject="spiffe://kil.local/workload/demo",
        audience="kil-v3-signed",
        authority_class="admin_action",
        action_class="consequential_admin",
        issued_at_s=100,
        not_before_s=100,
        expires_at_s=110,
        evidence_horizon_s=99,
        trust_proof_id="tp-v3a-1",
        trust_proof_digest="sha256:" + "a" * 64,
        envelope_result_id="ke-v3a-1",
        envelope_result_digest="sha256:" + "b" * 64,
        deployment_profile="kil-lab-v3@0",
        charge=Decimal("80"),
        threshold=Decimal("40"),
        history_count=5,
        minimum_history=2,
        veto_clear=True,
        envelope_allows=True,
        decay_rate=Decimal("0"),
        maximum_charge=Decimal("100"),
        model_version="kil-decay-v1",
        parameter_version="kil-v3a-fixture-v1",
    )
    return replace(value, **changes)


class QStateClaimsTest(unittest.TestCase):
    def test_round_trips_the_exact_payload(self):
        original = claims()
        self.assertEqual(QStateClaims.from_payload(original.to_payload()), original)

    def test_rejects_more_than_ten_seconds_of_validity(self):
        with self.assertRaisesRegex(ValueError, "ten seconds"):
            claims(expires_at_s=111)

    def test_rejects_unknown_payload_fields(self):
        payload = claims().to_payload()
        payload["mode"] = "signed_state_only"
        with self.assertRaisesRegex(ValueError, "unknown"):
            QStateClaims.from_payload(payload)

    def test_converts_only_claimed_authority_to_v1_state(self):
        state = claims().to_composite_state()
        self.assertEqual(state.identity, "spiffe://kil.local/workload/demo")
        self.assertEqual(state.authority_class, "admin_action")
        self.assertTrue(state.authentic)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONPATH=src /Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests.test_q_state.QStateClaimsTest -v
```

Expected: `ModuleNotFoundError: No module named 'kil.q_state'`.

- [ ] **Step 3: Pin the laboratory dependency**

Create `requirements-lab.txt` with exactly:

```text
cryptography==50.0.0
```

- [ ] **Step 4: Add the strict claims implementation**

Create `src/kil/q_state.py` with `QStateClaims`, an exact `_FIELDS` set, strict
primitive-type checks, finite `Decimal` checks, the ten-second validity ceiling,
`sha256:<64 lowercase hex>` digest validation, `to_payload()`, `from_payload()`,
and `to_composite_state()`. Decimal payload members are canonical decimal
strings, not JSON floating-point values. The conversion is:

```python
def to_composite_state(self) -> CompositeState:
    return CompositeState(
        state_id=self.state_id,
        identity=self.subject,
        authority_class=self.authority_class,
        issued_at_s=self.issued_at_s,
        not_before_s=self.not_before_s,
        expires_at_s=self.expires_at_s,
        charge=self.charge,
        threshold=self.threshold,
        history_count=self.history_count,
        minimum_history=self.minimum_history,
        authentic=True,
        veto_clear=self.veto_clear,
        envelope_allows=self.envelope_allows,
        decay_rate=self.decay_rate,
        maximum_charge=self.maximum_charge,
    )
```

`to_payload()` must emit all fields and render `charge`, `threshold`,
`decay_rate`, and `maximum_charge` with `str(value)`. `from_payload()` must
reject missing or unknown fields before constructing the record.

- [ ] **Step 5: Add the machine-readable schema**

Create `schemas/q-state-v0.schema.json` as a Draft 2020-12 closed object with
all `QStateClaims` fields required. Fix `schema_version` to `kil.q-state.v0`;
set `expires_at_s`, `issued_at_s`, `not_before_s`, and `evidence_horizon_s` to
integers; set `history_count` and `minimum_history` to nonnegative integers;
set booleans to JSON booleans; define the four decimal values as strings with
pattern `^[0-9]+(\\.[0-9]+)?$`; and define both digests with pattern
`^sha256:[a-f0-9]{64}$`. The schema description must call the format an
experimental KIL extension to KTP v2.0.0, not a KTP v2 wire artifact.

- [ ] **Step 6: Run the focused and full tests**

Run:

```bash
PYTHONPATH=src /Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests.test_q_state.QStateClaimsTest -v
make validate PYTHON=/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
```

Expected: the focused tests pass and the full count increases from 104 to 108.

- [ ] **Step 7: Commit**

```bash
git add requirements-lab.txt schemas/q-state-v0.schema.json src/kil/q_state.py tests/test_q_state.py
git commit -m "Add experimental KIL composite state claims"
```

### Task 2: Ed25519 compact-JWS issuance and verification

**Files:**
- Modify: `src/kil/q_state.py`
- Modify: `tests/test_q_state.py`

- [ ] **Step 1: Write the failing cryptographic tests**

Add tests using a deterministic fixture key created with
`Ed25519PrivateKey.from_private_bytes(bytes(range(32)))`. The tests must prove:

```python
def test_issues_and_verifies_a_bound_compact_jws(self):
    token = issue_q_state(claims(), self.private_key)
    verified = verify_q_state(
        token,
        {key_id(self.private_key.public_key()): self.private_key.public_key()},
        now_s=105,
        expected_subject="spiffe://kil.local/workload/demo",
        expected_audience="kil-v3-signed",
        expected_authority_class="admin_action",
        expected_action_class="consequential_admin",
        revoked_state_ids=frozenset(),
    )
    self.assertEqual(verified.claims, claims())
    self.assertTrue(verified.composite_state.authentic)

def test_tampering_wrong_key_expiry_and_binding_fail_closed(self):
    token = issue_q_state(claims(), self.private_key)
    parts = token.split(".")
    parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    tampered = ".".join(parts)
    cases = (
        (tampered, self.keys, 105,
         "spiffe://kil.local/workload/demo", "kil-v3-signed", "admin_action",
         "consequential_admin", frozenset(), "signature"),
        (token, self.other_keys, 105, "spiffe://kil.local/workload/demo",
         "kil-v3-signed", "admin_action", "consequential_admin", frozenset(),
         "key"),
        (token, self.keys, 110, "spiffe://kil.local/workload/demo",
         "kil-v3-signed", "admin_action", "consequential_admin", frozenset(),
         "expired"),
        (token, self.keys, 105, "spiffe://kil.local/workload/other",
         "kil-v3-signed", "admin_action", "consequential_admin", frozenset(),
         "subject"),
        (token, self.keys, 105, "spiffe://kil.local/workload/demo",
         "kil-v3-local", "admin_action", "consequential_admin", frozenset(),
         "audience"),
        (token, self.keys, 105, "spiffe://kil.local/workload/demo",
         "kil-v3-signed", "read", "consequential_admin", frozenset(), "class"),
        (token, self.keys, 105, "spiffe://kil.local/workload/demo",
         "kil-v3-signed", "admin_action", "benign_read", frozenset(), "action"),
        (token, self.keys, 105, "spiffe://kil.local/workload/demo",
         "kil-v3-signed", "admin_action", "consequential_admin",
         frozenset({"q-v3a-1"}), "revoked"),
    )
    for arguments in cases:
        *values, reason = arguments
        with self.subTest(reason=reason):
            with self.assertRaisesRegex(QStateVerificationError, reason):
                verify_q_state(*values)
```

- [ ] **Step 2: Run the cryptographic tests and verify RED**

Run the two new tests by full dotted name. Expected: import failure for
`issue_q_state`, `verify_q_state`, `key_id`, or `QStateVerificationError`.

- [ ] **Step 3: Implement the compact JWS profile**

Add:

```python
@dataclass(frozen=True, slots=True)
class VerifiedQState:
    claims: QStateClaims
    composite_state: CompositeState
    key_id: str


class QStateVerificationError(ValueError):
    pass


def _b64encode(value: bytes) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    try:
        padding = "=" * (-len(value) % 4)
        return b64decode(value + padding, altchars=b"-_", validate=True)
    except (ValueError, UnicodeEncodeError) as error:
        raise QStateVerificationError("malformed base64url") from error


def key_id(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return sha256(raw).hexdigest()[:16]


def issue_q_state(claims: QStateClaims, private_key: Ed25519PrivateKey) -> str:
    kid = key_id(private_key.public_key())
    header = {"alg": "EdDSA", "kid": kid, "typ": "KIL-Q+JWT"}
    header_part = _b64encode(_json_bytes(header))
    payload_part = _b64encode(_json_bytes(claims.to_payload()))
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    return f"{header_part}.{payload_part}.{_b64encode(private_key.sign(signing_input))}"
```

`_json_bytes()` must use `json.dumps(value, sort_keys=True,
separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.

`verify_q_state()` must split exactly three segments, decode and parse the
header and payload, require the exact header keys and values, select the public
key from the caller-provided key map, verify the signature over the original
encoded header and payload segments, construct `QStateClaims`, then check in
this order: revocation, `not_before_s <= now_s < expires_at_s`, subject,
audience, authority class, and action class. Each failure raises
`QStateVerificationError` with the corresponding stable word used by the test.

- [ ] **Step 4: Run the focused and full tests**

Run `tests.test_q_state -v`, then `make validate` with bundled Python 3.12.
Expected: all tests pass; test count increases to at least 110.

- [ ] **Step 5: Commit**

```bash
git add src/kil/q_state.py tests/test_q_state.py
git commit -m "Verify signed short-lived KIL state"
```

### Task 3: Three fixed authorization tracks

**Files:**
- Create: `src/kil/live_authz.py`
- Create: `tests/test_live_authz.py`

- [ ] **Step 1: Write the failing fixed-track tests**

Define one server-side `LiveFixture` whose credential and policy are valid,
whose signed charge is 80 with threshold 40, and whose local divergence is
`0.9` under `ReductionProfile(Decimal("0.25"), Decimal("25"), 3)`.

```python
class LiveAuthorizationTest(unittest.TestCase):
    def test_same_case_differentiates_the_three_fixed_tracks(self):
        baseline = AuthorizationAdapter(LiveTrack.CREDENTIAL_POLICY_BASELINE)
        signed = AuthorizationAdapter(
            LiveTrack.SIGNED_STATE_ONLY, keys=self.keys
        )
        local = AuthorizationAdapter(
            LiveTrack.SIGNED_PLUS_LOCAL_REDUCE, keys=self.local_keys
        )
        outcomes = (
            baseline.evaluate(self.fixture_for(LiveTrack.CREDENTIAL_POLICY_BASELINE)),
            signed.evaluate(self.fixture_for(LiveTrack.SIGNED_STATE_ONLY)),
            local.evaluate(self.fixture_for(LiveTrack.SIGNED_PLUS_LOCAL_REDUCE)),
        )
        self.assertEqual(
            tuple(item.outcome for item in outcomes),
            (DecisionOutcome.PERMIT, DecisionOutcome.PERMIT, DecisionOutcome.DENY),
        )

    def test_request_metadata_cannot_change_adapter_mode(self):
        adapter = AuthorizationAdapter(
            LiveTrack.SIGNED_PLUS_LOCAL_REDUCE, keys=self.local_keys
        )
        decision = adapter.evaluate(
            self.fixture_for(
                LiveTrack.SIGNED_PLUS_LOCAL_REDUCE,
                untrusted_headers=(("x-kil-mode", "signed_state_only"),),
            )
        )
        self.assertEqual(decision.track, LiveTrack.SIGNED_PLUS_LOCAL_REDUCE)
        self.assertEqual(decision.outcome, DecisionOutcome.DENY)
        self.assertIn("untrusted_mode_header_ignored", decision.adapter_reasons)

    def test_wrong_track_audience_fails_closed(self):
        decision = AuthorizationAdapter(
            LiveTrack.SIGNED_PLUS_LOCAL_REDUCE, keys=self.signed_keys
        ).evaluate(self.fixture_for(LiveTrack.SIGNED_PLUS_LOCAL_REDUCE))
        self.assertEqual(decision.outcome, DecisionOutcome.DENY)
        self.assertIn("q_state_verification_failed", decision.adapter_reasons)
```

- [ ] **Step 2: Run the tests and verify RED**

Run `tests.test_live_authz -v`. Expected: `kil.live_authz` is missing.

- [ ] **Step 3: Implement immutable track configuration**

Create:

```python
class LiveTrack(str, Enum):
    CREDENTIAL_POLICY_BASELINE = "credential_policy_baseline"
    SIGNED_STATE_ONLY = "signed_state_only"
    SIGNED_PLUS_LOCAL_REDUCE = "signed_plus_local_reduce"


@dataclass(frozen=True, slots=True)
class LiveFixture:
    request: ActionRequest
    action_class: str
    audience: str
    credential_valid: bool
    policy_allows_action: bool
    q_state_jws: str | None
    local_evidence: LocalEvidence | None
    reduction_profile: ReductionProfile | None
    untrusted_headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class LiveDecision:
    request_id: str
    track: LiveTrack
    outcome: DecisionOutcome
    adapter_reasons: tuple[str, ...]
    engine_record: DecisionRecord | None
    decision_digest: str
```

`AuthorizationAdapter.__init__()` receives a `LiveTrack`, copies the public-key
mapping into `MappingProxyType`, and stores an immutable revoked-state set. It
derives the expected audience
from a module-level map:

```python
TRACK_AUDIENCE = {
    LiveTrack.SIGNED_STATE_ONLY: "kil-v3-signed",
    LiveTrack.SIGNED_PLUS_LOCAL_REDUCE: "kil-v3-local",
}
```

The baseline returns permit only for valid credential plus allowing policy.
KIL tracks require a token, verify its binding against the request and fixed
audience, convert it to `CompositeState`, and call the existing `decide()`.
Signed-only uses `EnforcementMode.SIGNED_STATE_ONLY` and supplies no local
inputs. Local-reduction uses `EnforcementMode.SIGNED_PLUS_LOCAL_REDUCE` and the
fixture's server-side local inputs. Verification failure returns deny with
`("q_state_verification_failed",)` and no engine record. Presence of a
case-insensitive `x-kil-mode` in `untrusted_headers` appends
`untrusted_mode_header_ignored` but never changes the track.

Build `decision_digest` with `canonical_digest()` over every other decision
field. Do not include exception text or signature details in the wire-oriented
reason tuple.

- [ ] **Step 4: Run the focused and full tests**

Run `tests.test_live_authz -v`, then the complete `make validate` command.
Expected: all tests pass and the three-track result is permit, permit, deny.

- [ ] **Step 5: Commit**

```bash
git add src/kil/live_authz.py tests/test_live_authz.py
git commit -m "Add fixed KIL authorization tracks"
```

### Task 4: Reference gateway, proof join, and visible V3A bundle

**Files:**
- Create: `src/kil/reference_gateway.py`
- Create: `tests/test_reference_gateway.py`
- Create: `tools/v3a_demo.py`
- Create: `tests/test_v3a_demo.py`
- Create: `docs/lab/V3-PROGRESS.md`
- Create: `adapters/envoy/README.md`
- Modify: `README.md`

- [ ] **Step 1: Write the failing no-forward proof test**

```python
class ReferenceGatewayTest(unittest.TestCase):
    def test_denied_request_has_no_target_marker(self):
        target = TargetMarker()
        result = ReferenceGateway(self.local_adapter, target).handle(self.local_fixture)
        self.assertEqual(result.decision.outcome, DecisionOutcome.DENY)
        self.assertFalse(result.forwarded)
        self.assertEqual(target.records, ())
        self.assertTrue(result.proof_valid)

    def test_permitted_request_has_exactly_one_target_marker(self):
        target = TargetMarker()
        result = ReferenceGateway(self.signed_adapter, target).handle(self.signed_fixture)
        self.assertEqual(result.decision.outcome, DecisionOutcome.PERMIT)
        self.assertTrue(result.forwarded)
        self.assertEqual(len(target.records), 1)
        self.assertEqual(target.records[0].request_id, self.signed_fixture.request.request_id)
        self.assertTrue(result.proof_valid)
```

- [ ] **Step 2: Run the proof test and verify RED**

Run `tests.test_reference_gateway -v`. Expected: module import failure.

- [ ] **Step 3: Implement the harmless target and proof join**

Create frozen `TargetRecord` and `GatewayResult` records. `TargetMarker` stores
records privately and exposes them as an immutable tuple. `ReferenceGateway`
evaluates the adapter, invokes `TargetMarker.invoke()` exactly once only on
`DecisionOutcome.PERMIT`, and sets:

```python
proof_valid = (
    decision.outcome is DecisionOutcome.PERMIT
    and forwarded
    and marker_count == 1
) or (
    decision.outcome is not DecisionOutcome.PERMIT
    and not forwarded
    and marker_count == 0
)
```

No target method performs filesystem, network, credential, or Kubernetes
operations.

- [ ] **Step 4: Write the failing CLI bundle test**

Run `tools/v3a_demo.py` in a temporary directory through `subprocess.run()` and
assert:

- stdout contains `credential_policy_baseline permit`,
  `signed_state_only permit`, and `signed_plus_local_reduce deny`;
- the command creates one content-addressed child directory;
- `manifest.json` contains `"evidence_class":"modeled"` and
  `"validation_scope":"process_contract_only"`;
- `joins.jsonl` contains three valid joins and the local-reduction row has zero
  target markers;
- `live.html` contains all three track names and a visible `PERMIT / PERMIT /
  DENY` summary;
- `SHA256SUMS` covers `manifest.json`, `decisions.jsonl`, `joins.jsonl`,
  `targets.jsonl`, `summary.md`, and `live.html`; and
- `summary.md` contains the canonical KTP citation and the sentence “This V3A
  process-contract demonstration is modeled, not a validated cluster run.”

- [ ] **Step 5: Run the CLI test and verify RED**

Expected: `tools/v3a_demo.py` does not exist.

- [ ] **Step 6: Implement the visible three-track demo**

The CLI accepts required `--output` and `--implementation-version` arguments.
It uses the deterministic fixture key `bytes(range(32))`, issues separate
audience-bound states for the signed and local tracks, executes the same action
facts through all three reference gateways, and prints each joined result as it
runs. It writes canonical JSON/JSONL, a static dark-theme `live.html`, a Markdown
summary, and sorted SHA-256 checksums through an atomic temporary directory
rename. The run ID is the first sixteen hex characters of a canonical digest
over scenario ID, implementation version, fixed profile ID, and the three
semantic decisions; presentation timestamps are excluded.

The HTML must render:

- three large track cards with current outcome and target-marker count;
- a “contract scope” banner that says process-only and modeled;
- the architecture SVG via relative path only when viewed from the repository,
  while the standalone bundle retains text labels if that relative asset is not
  available; and
- a table containing request ID, decision digest, engine reasons, forwarded,
  marker count, and proof validity.

- [ ] **Step 7: Document the V3A/V3B boundary**

`docs/lab/V3-PROGRESS.md` records the Ed25519 profile, fixed tracks, exact test
counts, first demo run ID, and the prohibition on calling the result a validated
cluster run. `adapters/envoy/README.md` records the V3B HTTP contract:
`failure_mode_allow: false`, external authorization before the router, no route
cache clearing, fixed server-side mode, fixed audience, allowlisted headers,
generic wire denial, decision digest header, and target-ledger proof join.
Update the root README status to say V3A is process-level only and V3B remains
the first Envoy/Kind validation gate.

Every new Markdown file must include:

```markdown
KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
```

- [ ] **Step 8: Run complete verification**

Run:

```bash
make validate PYTHON=/Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
PYTHONPATH=src /Users/mistorm/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 tools/v3a_demo.py --output /tmp/kil-v3a-runs --implementation-version $(git rev-parse HEAD)
shasum -a 256 -c /tmp/kil-v3a-runs/*/SHA256SUMS
```

Expected: complete suite passes; demo prints permit, permit, deny; all bundle
hashes report `OK`. Remove only the exact temporary run directory after reading
the verification result.

- [ ] **Step 9: Commit**

```bash
git add README.md adapters/envoy/README.md docs/lab/V3-PROGRESS.md src/kil/reference_gateway.py tests/test_reference_gateway.py tools/v3a_demo.py tests/test_v3a_demo.py
git commit -m "Demonstrate the V3A enforcement contract"
```

## V3A completion gate

V3A is complete only when the full suite passes from the feature branch, the
visible bundle reproduces permit/permit/deny, its checksums verify, no denied
request has a target marker, the mode-header downgrade test passes, and all
documentation retains the modeled/process-only caveat. V3B then implements the
same contract in Envoy 1.39.1 and Kind 0.33.0; no V3A result is relabeled as a
validated live-cluster result.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
