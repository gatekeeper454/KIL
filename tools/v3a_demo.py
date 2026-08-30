#!/usr/bin/env python3
"""Run the visible V3A process-contract demonstration."""

from argparse import ArgumentParser
from decimal import Decimal
from hashlib import sha256
from html import escape
from pathlib import Path
import shutil
from tempfile import mkdtemp

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kil.canonical import canonical_digest, canonical_json
from kil.domain import ActionRequest, LocalEvidence, ReductionProfile
from kil.live_authz import AuthorizationAdapter, LiveFixture, LiveTrack
from kil.q_state import QStateClaims, issue_q_state, key_id
from kil.reference_gateway import GatewayResult, ReferenceGateway, TargetMarker


KTP_CITATION_URL = "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff"
SCENARIO_ID = "kil-v3a-two-timescale-cutoff"
PROFILE_ID = "kil-v3a-fixture-v1"
SUBJECT = "spiffe://kil.local/workload/demo"


def _claims(audience: str) -> QStateClaims:
    return QStateClaims(
        schema_version="kil.q-state.v0",
        state_id=f"q-{audience}",
        issuer="https://lab-issuer.kil.invalid",
        subject=SUBJECT,
        audience=audience,
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
        parameter_version=PROFILE_ID,
    )


def _execute() -> tuple[tuple[GatewayResult, ...], str]:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    public_key = private_key.public_key()
    keys = {key_id(public_key): public_key}
    request = ActionRequest("v3a-request-1", SUBJECT, "admin_action", 105)
    local_evidence = LocalEvidence(Decimal("0.9"), Decimal("0"), True)
    reduction_profile = ReductionProfile(Decimal("0.25"), Decimal("25"), 3)

    track_inputs = (
        (
            LiveTrack.CREDENTIAL_POLICY_BASELINE,
            AuthorizationAdapter(LiveTrack.CREDENTIAL_POLICY_BASELINE),
            None,
        ),
        (
            LiveTrack.SIGNED_STATE_ONLY,
            AuthorizationAdapter(LiveTrack.SIGNED_STATE_ONLY, keys=keys),
            issue_q_state(_claims("kil-v3-signed"), private_key),
        ),
        (
            LiveTrack.SIGNED_PLUS_LOCAL_REDUCE,
            AuthorizationAdapter(LiveTrack.SIGNED_PLUS_LOCAL_REDUCE, keys=keys),
            issue_q_state(_claims("kil-v3-local"), private_key),
        ),
    )
    results = []
    for track, adapter, token in track_inputs:
        fixture = LiveFixture(
            request=request,
            action_class="consequential_admin",
            credential_valid=True,
            policy_allows_action=True,
            q_state_jws=token,
            local_evidence=local_evidence,
            reduction_profile=reduction_profile,
        )
        result = ReferenceGateway(adapter, TargetMarker()).handle(fixture)
        results.append(result)
        proof = "valid" if result.proof_valid else "invalid"
        print(
            f"{track.value} {result.decision.outcome.value} "
            f"markers={result.marker_count} proof={proof}"
        )
    return tuple(results), key_id(public_key)


def _live_html(results: tuple[GatewayResult, ...], run_id: str) -> str:
    cards = []
    rows = []
    for result in results:
        track = result.decision.track.value
        outcome = result.decision.outcome.value.upper()
        outcome_class = "permit" if outcome == "PERMIT" else "deny"
        cards.append(
            "<article class='card'>"
            f"<div class='track'>{escape(track)}</div>"
            f"<div class='outcome {outcome_class}'>{escape(outcome)}</div>"
            f"<div class='markers'>target markers: {result.marker_count}</div>"
            "</article>"
        )
        engine_reasons = "—"
        if result.decision.engine_record is not None:
            engine_reasons = ", ".join(
                reason.value for reason in result.decision.engine_record.reasons
            )
        rows.append(
            "<tr>"
            f"<td>{escape(track)}</td>"
            f"<td>{escape(result.decision.request_id)}</td>"
            f"<td><code>{escape(result.decision.decision_digest)}</code></td>"
            f"<td>{escape(engine_reasons)}</td>"
            f"<td>{str(result.forwarded).lower()}</td>"
            f"<td>{result.marker_count}</td>"
            f"<td>{str(result.proof_valid).lower()}</td>"
            "</tr>"
        )
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KIL V3A Process Contract</title>
<style>
:root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
body { margin: 0; background: #07131f; color: #e2e8f0; }
main { max-width: 1180px; margin: 0 auto; padding: 48px 28px 72px; }
h1 { margin: 0 0 8px; font-size: 34px; }
.scope { margin: 24px 0; padding: 16px 20px; border: 1px solid #f59e0b;
  border-radius: 12px; background: #2a1d09; color: #fde68a; font-weight: 700; }
.summary { color: #bae6fd; font-size: 22px; font-weight: 800; letter-spacing: .04em; }
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 26px 0; }
.card { background: #102842; border: 1px solid #3b82f6; border-radius: 16px; padding: 22px; }
.track { min-height: 42px; color: #bfdbfe; font-weight: 700; overflow-wrap: anywhere; }
.outcome { margin: 18px 0 8px; font-size: 30px; font-weight: 900; }
.permit { color: #5eead4; } .deny { color: #fca5a5; }
.markers { color: #cbd5e1; }
table { width: 100%; border-collapse: collapse; background: #0b1f33; font-size: 13px; }
th, td { padding: 12px 10px; border: 1px solid #27445f; text-align: left; vertical-align: top; }
th { color: #bae6fd; } code { overflow-wrap: anywhere; }
.foot { margin-top: 24px; color: #94a3b8; }
@media (max-width: 850px) { .cards { grid-template-columns: 1fr; } }
</style>
</head>
<body><main>
""" + (
        f"<h1>KIL V3A Process Contract · {escape(run_id)}</h1>"
        "<div class='scope'>PROCESS CONTRACT ONLY · MODELED · NOT A LIVE-CLUSTER VALIDATION</div>"
        "<div class='summary'>PERMIT / PERMIT / DENY</div>"
        "<p>The same action facts traverse three infrastructure-fixed authorization tracks.</p>"
        f"<section class='cards'>{''.join(cards)}</section>"
        "<table><thead><tr><th>track</th><th>request</th><th>decision digest</th>"
        "<th>engine reasons</th><th>forwarded</th><th>markers</th><th>proof valid</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        "<p class='foot'>A denial is accepted only when the decision denies, forwarding is false, "
        "and the harmless target has no matching marker. The repository architecture diagram is "
        "docs/architecture/v3-envoy-live-validation.svg.</p>"
        "</main></body></html>\n"
    )


def _artifact_contents(
    results: tuple[GatewayResult, ...],
    run_id: str,
    implementation_version: str,
    verification_key_id: str,
) -> dict[str, str]:
    manifest = {
        "run_id": run_id,
        "scenario_id": SCENARIO_ID,
        "profile_id": PROFILE_ID,
        "implementation_version": implementation_version,
        "evidence_class": "modeled",
        "validation_scope": "process_contract_only",
        "signature_profile": "kil-q-jws-eddsa-lab-v0",
        "verification_key_id": verification_key_id,
        "ktp_citation": KTP_CITATION_URL,
    }
    joins = tuple(
        {
            "request_id": result.decision.request_id,
            "track": result.decision.track,
            "outcome": result.decision.outcome,
            "decision_digest": result.decision.decision_digest,
            "forwarded": result.forwarded,
            "marker_count": result.marker_count,
            "proof_valid": result.proof_valid,
        }
        for result in results
    )
    targets = tuple(
        target
        for result in results
        for target in result.target_records
    )
    summary = (
        f"# KIL V3A process contract {run_id}\n\n"
        "Result: `permit / permit / deny`.\n\n"
        "This V3A process-contract demonstration is modeled, not a validated "
        "cluster run. It verifies the software contract only; Envoy and Kind "
        "remain Gate V3B.\n\n"
        f"KTP citation: [canonical `CITATION.cff`]({KTP_CITATION_URL}).\n"
    )
    return {
        "manifest.json": canonical_json(manifest) + "\n",
        "decisions.jsonl": "".join(
            canonical_json(result.decision) + "\n" for result in results
        ),
        "joins.jsonl": "".join(canonical_json(item) + "\n" for item in joins),
        "targets.jsonl": "".join(
            canonical_json(item) + "\n" for item in targets
        ),
        "summary.md": summary,
        "live.html": _live_html(results, run_id),
    }


def _write_bundle(
    output_root: Path,
    results: tuple[GatewayResult, ...],
    implementation_version: str,
    verification_key_id: str,
) -> Path:
    identity = {
        "scenario_id": SCENARIO_ID,
        "profile_id": PROFILE_ID,
        "implementation_version": implementation_version,
        "decisions": tuple(result.decision for result in results),
        "joins": tuple(
            (result.forwarded, result.marker_count, result.proof_valid)
            for result in results
        ),
    }
    run_id = canonical_digest(identity)[:16]
    output_root.mkdir(parents=True, exist_ok=True)
    bundle = output_root / run_id
    if bundle.exists():
        raise FileExistsError(f"run bundle already exists: {bundle}")
    artifacts = _artifact_contents(
        results,
        run_id,
        implementation_version,
        verification_key_id,
    )
    temporary = Path(mkdtemp(prefix=f".{run_id}-", dir=output_root))
    try:
        for name, content in artifacts.items():
            (temporary / name).write_text(content, encoding="utf-8")
        checksums = []
        for name in sorted(artifacts):
            digest = sha256((temporary / name).read_bytes()).hexdigest()
            checksums.append(f"{digest}  {name}")
        (temporary / "SHA256SUMS").write_text(
            "\n".join(checksums) + "\n",
            encoding="utf-8",
        )
        temporary.rename(bundle)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return bundle


def main() -> None:
    parser = ArgumentParser(
        description=(
            "Execute the modeled V3A process contract. This is not a validated "
            "Envoy or Kubernetes run."
        )
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--implementation-version", required=True)
    arguments = parser.parse_args()
    if not arguments.implementation_version.strip():
        parser.error("--implementation-version must be nonblank")
    results, verification_key_id = _execute()
    bundle = _write_bundle(
        arguments.output,
        results,
        arguments.implementation_version,
        verification_key_id,
    )
    print(f"bundle {bundle}")


if __name__ == "__main__":
    main()
