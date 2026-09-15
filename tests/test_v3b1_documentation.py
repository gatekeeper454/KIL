from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CITATION_URL = "https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff"

README = ROOT / "README.md"
TOOLS_README = ROOT / "tools/README.md"
ENVOY_README = ROOT / "adapters/envoy/README.md"
V3_PROGRESS = ROOT / "docs/lab/V3-PROGRESS.md"
TASK10_GATE = ROOT / "docs/lab/V3B1-TASK10-REQUEST-FREE-GATE.md"
PAPER = ROOT / "docs/paper/kinetic-infrastructure.md"
SVG = ROOT / "docs/architecture/v3-envoy-live-validation.svg"
HYBRID_INLINE = ROOT / "docs/design-drafts/hybrid-two-timescale-architecture.html"
HYBRID_STANDALONE = ROOT / "docs/architecture/hybrid-two-timescale-architecture.html"
LEGACY_SPEC = (
    ROOT / "docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md"
)
LEGACY_PLAN = (
    ROOT / "docs/superpowers/plans/2026-08-30-v3b1-integration-contract.md"
)
LINEAGE = ROOT / "docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md"
LIVE_BOARD = ROOT / "artifacts/generated/v3b1-task6-live-status.md"
CENTRAL_RUN_ID = (
    "v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94"
)
CENTRAL_BUNDLE = ROOT / "artifacts/generated/v3b1-local-envoy" / CENTRAL_RUN_ID

REQUEST_DRIVER_DESIGN = "2026-08-31-v3b1-in-network-request-driver-design.md"
REQUEST_DRIVER_PLAN = "2026-08-31-v3b1-in-network-request-driver.md"
CURRENT_DRIVER_PLAN = ROOT / "docs/superpowers/plans" / REQUEST_DRIVER_PLAN
FOREIGN_SNAPSHOT_DESIGN = (
    ROOT
    / "docs/superpowers/specs/2026-08-31-v3b1-foreign-resource-snapshot-design.md"
)

LEGACY_PREFIXES = {
    LEGACY_SPEC: (
        20229,
        "cf44f8c4b86b0754056595defd39c96fd90142c60c4e106c9b87dc568c0fb09b",
    ),
    LEGACY_PLAN: (
        13368,
        "36e123a819cdba9d1dfac400372b109757e53de77cf3593ec4f791aad7af5efb",
    ),
}

TRACKED_TASK9_PUBLICATIONS = (
    README,
    TOOLS_README,
    ENVOY_README,
    V3_PROGRESS,
    TASK10_GATE,
    PAPER,
    SVG,
    HYBRID_INLINE,
    HYBRID_STANDALONE,
    LEGACY_SPEC,
    LEGACY_PLAN,
    LINEAGE,
)


def normalized(value: str) -> str:
    return " ".join(value.split())


class _PassiveHTMLParser(HTMLParser):
    FORBIDDEN_TAGS = {
        "script",
        "iframe",
        "object",
        "embed",
        "foreignobject",
        "link",
        "form",
    }
    EXTERNAL_OR_ACTIVE_ATTRIBUTES = {
        "href",
        "src",
        "srcset",
        "data",
        "action",
        "formaction",
        "poster",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.violations: list[str] = []

    def handle_starttag(self, tag, attrs):
        lowered_tag = tag.lower()
        if lowered_tag in self.FORBIDDEN_TAGS:
            self.violations.append(f"forbidden tag <{tag}>")
        for name, _value in attrs:
            lowered_name = name.lower()
            if lowered_name.startswith("on"):
                self.violations.append(f"event attribute {name}")
            if lowered_name in self.EXTERNAL_OR_ACTIVE_ATTRIBUTES:
                self.violations.append(f"external/active attribute {name}")

    handle_startendtag = handle_starttag


class V3B1DocumentationTest(unittest.TestCase):
    def test_accepted_central_proof_is_bound_and_claim_limited(self):
        source_commit = "514e910ea9427e0497c4fe8a1ec279b554e75176"
        for path in (README, ENVOY_README, V3_PROGRESS, PAPER):
            with self.subTest(path=path.relative_to(ROOT)):
                value = normalized(path.read_text(encoding="utf-8")).lower()
                self.assertIn(CENTRAL_RUN_ID, value)
                self.assertIn(source_commit, value)
                self.assertIn("permit / permit / deny", value)
                self.assertIn("200 / 200 / 403", value)
                self.assertIn("1 / 1 / 0", value)
                self.assertRegex(value, r"local[-_ ]envoy boundary")
                self.assertIn("kil-v3-lab", value)
                self.assertRegex(value, r"does not mutate|remain[s]? untouched")
                self.assertRegex(value, r"kind(?:/|\s*\+\s*)calico[^.]{0,160}(?:future|pending|not)")
                self.assertRegex(value, r"historical prevention[^.]{0,120}(?:not|no|exclude)")
                self.assertRegex(value, r"performance[^.]{0,120}(?:not|no|exclude|future)")

        manifest = CENTRAL_BUNDLE / "manifest.json"
        self.assertTrue(manifest.is_file())
        manifest_value = manifest.read_text(encoding="utf-8")
        self.assertIn('"run_complete":true', manifest_value)
        self.assertIn('"bundle_class":"intermediate_provisional_local_boundary"', manifest_value)
        self.assertIn('"unchanged":true', manifest_value)

    def test_v3_foreign_snapshot_prerequisite_and_next_gate_are_current(self):
        for path in (README, ENVOY_README, V3_PROGRESS):
            with self.subTest(path=path.relative_to(ROOT)):
                value = normalized(path.read_text(encoding="utf-8")).lower()
                self.assertIn("kil.v3b1-manifest.v3", value)
                self.assertIn("pseudonym", value)
                self.assertRegex(
                    value,
                    r"before/after[^.]{0,180}foreign[^.]{0,180}(?:exact|equality)",
                )
                self.assertIn(CENTRAL_RUN_ID, value)
                self.assertIn("accepted", value)
                self.assertRegex(
                    value,
                    r"fresh request-free[^.]{0,180}v3",
                )

        gate = normalized(TASK10_GATE.read_text(encoding="utf-8")).lower()
        self.assertRegex(gate, r"historical[^.]{0,100}v2")
        self.assertRegex(gate, r"does not satisfy[^.]{0,160}v3")
        self.assertRegex(gate, r"fresh request-free[^.]{0,180}v3")

        task11 = normalized(
            CURRENT_DRIVER_PLAN.read_text(encoding="utf-8").split(
                "### Task 11", 1
            )[1]
        ).lower()
        self.assertIn("kil.v3b1-manifest.v3", task11)
        self.assertRegex(task11, r"fresh request-free[^.]{0,180}v3")

    def test_fresh_v3_request_free_gate_is_public_bound_and_claim_limited(self):
        run_id = (
            "v3b1-4ac0b6eef70b0483f7883c8a26753d15a007f612953b25e23b8ecb6afd021a8f"
        )
        source_commit = "5ebf21a88794a9f83a0e6c8ee53e76f6d8e5142d"
        public_commitment = (
            "10101f8ddb3d11682955444d5b3330ab5b290f2663302afdd5fade23530cf112"
        )
        manifest_sha256 = (
            "3572ad5b9f7a2da66ce8b5cf13c020179283c5b1635aef8302977e8c562bb475"
        )
        for path in (README, ENVOY_README, V3_PROGRESS, TASK10_GATE):
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                value = normalized(text).lower()
                self.assertIn(run_id, text)
                self.assertIn(source_commit, text)
                self.assertIn("kil.v3b1-public-manifest.v3", text)
                self.assertRegex(
                    value,
                    r"foreign[^.]{0,180}(?:exact equality|exactly equal|unchanged)",
                )
                self.assertRegex(value, r"zero[^.]{0,120}(?:http|requests?)")

        for path in (README, ENVOY_README, V3_PROGRESS):
            with self.subTest(accepted_path=path.relative_to(ROOT)):
                self.assertIn(CENTRAL_RUN_ID, path.read_text(encoding="utf-8"))

        gate_text = TASK10_GATE.read_text(encoding="utf-8")
        self.assertIn(public_commitment, gate_text)
        self.assertIn(manifest_sha256, gate_text)
        self.assertIn("intermediate_provisional_failure_local_boundary", gate_text)
        self.assertIn("not_promoted", gate_text)

        task11 = CURRENT_DRIVER_PLAN.read_text(encoding="utf-8").split(
            "### Task 11", 1
        )[1]
        self.assertIn("- [x] **Step 1:", task11)
        self.assertIn(run_id, task11)
        self.assertRegex(
            normalized(task11).lower(),
            r"review[^.]{0,120}merge[^.]{0,120}synchron",
        )

        publication_gate = FOREIGN_SNAPSHOT_DESIGN.read_text(
            encoding="utf-8"
        ).split("## 10. Publication and live gates", 1)[1].split(
            "## 11.", 1
        )[0]
        publication_value = normalized(publication_gate).lower()
        self.assertIn("failure-bundle verifier", publication_value)
        self.assertRegex(
            publication_value,
            r"view --bundle[^.]{0,180}(?:completed|central)",
        )
        mismatch_section = FOREIGN_SNAPSHOT_DESIGN.read_text(
            encoding="utf-8"
        ).split("## 6. Mismatch and failure behavior", 1)[1].split(
            "## 7.", 1
        )[0]
        self.assertRegex(
            normalized(mismatch_section).lower(),
            r"failure bundle[^.]{0,160}unequal[^.]{0,160}"
            r"cannot satisfy the fresh request-free gate",
        )

    def test_task10_request_free_gate_is_public_bound_and_claim_limited(self):
        run_id = (
            "v3b1-d2b26f6c8136dcd26a6e6727b9bb1381076a1e03b71a5a44df9b2b2ef9db6cf9"
        )
        source_commit = "a46e8dc98a1af64ceadb5700e91c2f87840564fe"
        self.assertTrue(TASK10_GATE.is_file(), "Task 10 gate record is missing")
        for path in (README, V3_PROGRESS, TASK10_GATE):
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                value = normalized(text).lower()
                self.assertIn(run_id, text)
                self.assertIn(source_commit, text)
                self.assertIn("request-free", value)
                self.assertRegex(value, r"three[^.]{0,120}readiness")
                self.assertRegex(value, r"three[^.]{0,120}(?:clean )?cancellations")
                self.assertRegex(value, r"15[^.]{0,80}containers")
                self.assertRegex(value, r"six[^.]{0,80}networks")
                self.assertRegex(value, r"zero[^.]{0,120}(?:http|requests?)")
                if path == TASK10_GATE:
                    self.assertRegex(
                        value,
                        r"central `?run`?[^.]{0,120}(?:not executed|prohibited)",
                    )
                else:
                    self.assertIn(CENTRAL_RUN_ID, value)

        gate_text = TASK10_GATE.read_text(encoding="utf-8")
        gate_value = normalized(gate_text).lower()
        for exact in (
            "18bfe97801cfb5f43774c68581da58576147e698f05d56dfac53cc7fa1097da7",
            "e7dfc3e371a3057152850b196005753b40bafd384fd470b3d501bffa34d0acae",
            "intermediate_provisional_failure_local_boundary",
            "local_envoy_boundary",
            "not_promoted",
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ):
            self.assertIn(exact, gate_text)
        self.assertIn("not durably", gate_value)
        self.assertIn(CITATION_URL, gate_text)

        lineage_text = LINEAGE.read_text(encoding="utf-8").split(
            "### T-124 —", 1
        )[1]
        for exact in (
            run_id,
            source_commit,
            "18bfe97801cfb5f43774c68581da58576147e698f05d56dfac53cc7fa1097da7",
            "e7dfc3e371a3057152850b196005753b40bafd384fd470b3d501bffa34d0acae",
        ):
            self.assertIn(exact, lineage_text)
        self.assertRegex(
            normalized(lineage_text).lower(),
            r"central `?run`?[^.]{0,120}(?:not executed|prohibited)",
        )
        self.assertIn("not durably", normalized(lineage_text).lower())

        self.assertNotIn(
            "latest merged complete static gate passes 480",
            normalized(README.read_text(encoding="utf-8")).lower(),
        )
        self.assertNotIn(
            "either pending driver-era live gate",
            normalized(V3_PROGRESS.read_text(encoding="utf-8")).lower(),
        )

        task10_plan = CURRENT_DRIVER_PLAN.read_text(encoding="utf-8").split(
            "## Task 10", 1
        )[1].split("## Task 11", 1)[0]
        self.assertIn("- [x] **Step 3:", task10_plan)
        self.assertIn("- [x] **Step 4:", task10_plan)
        self.assertIn("- [x] **Step 5:", task10_plan)
        task10_value = normalized(task10_plan).lower()
        self.assertNotIn("exact foreign-state restoration", task10_value)
        self.assertRegex(
            task10_value,
            r"context name[^.]{0,160}post-run[^.]{0,160}(?:tuple|resource)",
        )
        self.assertNotIn(
            "until the pending live gates pass",
            normalized(README.read_text(encoding="utf-8")).lower(),
        )

        task11_plan = CURRENT_DRIVER_PLAN.read_text(encoding="utf-8").split(
            "## Task 11", 1
        )[1]
        task11_value = normalized(task11_plan).lower()
        self.assertRegex(
            task11_value,
            r"before- and after-resource snapshots[^.]{0,160}"
            r"(?:implemented|tested|merged)",
        )
        self.assertRegex(
            task11_value,
            r"verif(?:y|ier)[^.]{0,160}(?:exact equality|exactly equal)",
        )
        self.assertIn(CENTRAL_RUN_ID, task11_value)
        self.assertIn("- [x] **step 5:", task11_value)

    def test_founder_byline_and_approved_opening_are_preserved(self):
        text = PAPER.read_text(encoding="utf-8")
        self.assertIn(
            "**Author and Creator** Mike Storm, Distinguished Engineer",
            text,
        )
        introduction = text.split("## 1. Introduction", 1)[1].split(
            "### 1.1 The checkpoint problem", 1
        )[0]
        expected_paragraphs = (
            """
            Cybersecurity is currently at an inflection point where reliance on
            static or AI-assisted SOCs (Security Operations Centers) and traditional
            AI-augmented controls is no longer sufficient to counter modern,
            adversarial AI.
            """,
            """
            To remain effective, the practice must transcend the legacy
            detect-and-prevent paradigm and evolve into a state of ambient
            enforcement. We are transitioning from a landscape of “ambient risk” and
            “ambient threat” into an era of pervasive, continuous “ambient breach,”
            necessitating a shift toward autonomous, real-time mitigation that
            functions at speed and scale independent of human intervention.
            """,
            """
            Ambient enforcement represents this critical evolution by decoupling
            defense from static, procedural constraints and utilizing kinetic
            infrastructure to match the velocity of AI adversaries in real time. By
            leveraging the same transport mechanisms as the threat itself and
            instantiating immutable controls that enforce security through physics,
            we move toward a future where cybersecurity functions not as a reactive
            overlay, but as an autonomous, omnipresent force capable of neutralizing
            AI-driven threats with the same speed and adaptability as the intelligence
            it seeks to contain.
            """,
        )
        normalized_introduction = normalized(introduction)
        for paragraph in expected_paragraphs:
            with self.subTest(paragraph=normalized(paragraph)[:48]):
                self.assertIn(normalized(paragraph), normalized_introduction)

    def test_current_publications_explain_the_driver_transport_boundary(self):
        for path in (README, TOOLS_README, ENVOY_README, V3_PROGRESS, PAPER):
            with self.subTest(path=path.relative_to(ROOT)):
                value = normalized(path.read_text(encoding="utf-8")).lower()
                self.assertRegex(value, r"(?:request[- ]driver|one-shot driver)")
                self.assertRegex(
                    value,
                    r"(?:no|without a) host (?:tcp )?publication",
                )
                self.assertIn("laboratory transport", value)

        for path in (SVG, HYBRID_INLINE, HYBRID_STANDALONE):
            with self.subTest(path=path.relative_to(ROOT)):
                value = normalized(path.read_text(encoding="utf-8"))
                lowered = value.lower()
                self.assertRegex(lowered, r"\b(?:six|6) internal networks\b")
                self.assertIn("credential_policy_baseline", value)
                self.assertIn("signed_state_only", value)
                self.assertIn("signed_plus_local_reduce", value)
                self.assertIn("frontend", lowered)
                self.assertRegex(lowered, r"request[- ]driver")
                self.assertIn("backend", lowered)
                self.assertIn("authorization", lowered)
                self.assertIn("target", lowered)
                self.assertIn("dual-homed", lowered)
                self.assertIn("docker attach", lowered)
                self.assertIn("stdin", lowered)
                self.assertIn("no host publication", lowered)
                self.assertIn("evidence", lowered)

        for path in (V3_PROGRESS, PAPER, SVG, HYBRID_INLINE, HYBRID_STANDALONE):
            with self.subTest(semantics_path=path.relative_to(ROOT)):
                value = normalized(path.read_text(encoding="utf-8")).lower()
                self.assertIn("does not change", value)
                self.assertIn("authorization semantics", value)
                self.assertRegex(value, r"signed (?:composite )?(?:ktp )?state")
                self.assertIn("transport witness", value)
                self.assertIn("not kil enforcement", value)

        paper_text = PAPER.read_text(encoding="utf-8")
        self.assertIn(
            "[hybrid-two-timescale-architecture.html]"
            "(../architecture/hybrid-two-timescale-architecture.html)",
            paper_text,
        )
        for path in (PAPER, SVG, HYBRID_INLINE, HYBRID_STANDALONE):
            with self.subTest(track_semantics_path=path.relative_to(ROOT)):
                value = normalized(path.read_text(encoding="utf-8")).lower().replace(
                    "`", ""
                )
                self.assertIn(
                    "credential_policy_baseline is a credential-policy control "
                    "and does not consume signed composite ktp state",
                    value,
                )
                self.assertIn(
                    "only signed_state_only and signed_plus_local_reduce consume "
                    "signed composite ktp state",
                    value,
                )
        self.assertIn(
            "![Gate V3 Envoy live-validation architecture]"
            "(../architecture/v3-envoy-live-validation.svg)",
            paper_text,
        )

    def test_v3b1_current_scope_and_v4_future_scope_remain_distinct(self):
        for path in (README, V3_PROGRESS, PAPER, HYBRID_STANDALONE):
            with self.subTest(path=path.relative_to(ROOT)):
                value = normalized(path.read_text(encoding="utf-8"))
                lowered = value.lower()
                self.assertIn("v3b-1", lowered)
                self.assertRegex(lowered, r"local[-_ ]envoy boundary")
                self.assertIn("v4 future", lowered)
                self.assertRegex(lowered, r"kind(?:/|\s*\+\s*)calico")
                self.assertRegex(
                    lowered,
                    r"pending|future|not[_ ]promoted|has (?:not|yet)",
                )

        corpus = normalized(
            "\n".join(
                path.read_text(encoding="utf-8")
                for path in (README, V3_PROGRESS, PAPER, HYBRID_INLINE, HYBRID_STANDALONE)
            )
        ).lower()
        for prohibited_claim in (
            "kil prevented the hugging face incident",
            "v3b-1 is validated",
            "validated v3b-1",
            "validated kind/calico",
            "validated networkpolicy",
            "production-performance validated",
        ):
            with self.subTest(prohibited_claim=prohibited_claim):
                self.assertNotIn(prohibited_claim, corpus)

    def test_current_visuals_drop_direct_host_and_current_kind_language(self):
        corpus = normalized(
            SVG.read_text(encoding="utf-8")
            + "\n"
            + HYBRID_INLINE.read_text(encoding="utf-8")
            + "\n"
            + HYBRID_STANDALONE.read_text(encoding="utf-8")
        ).lower()
        for stale in (
            "a host controller sends identical requests",
            "monotonic timing · localhost only",
            "isolated kind cluster",
            "local kubernetes actions + locally observed telemetry",
        ):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, corpus)

    def test_every_task9_publication_has_the_canonical_ktp_citation(self):
        for path in TRACKED_TASK9_PUBLICATIONS:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertTrue(path.is_file(), f"missing publication: {path}")
                self.assertIn(CITATION_URL, path.read_text(encoding="utf-8"))

        for path in (
            README,
            TOOLS_README,
            ENVOY_README,
            V3_PROGRESS,
            PAPER,
            LEGACY_SPEC,
            LEGACY_PLAN,
        ):
            with self.subTest(static_count_path=path.relative_to(ROOT)):
                value = normalized(path.read_text(encoding="utf-8")).lower()
                self.assertRegex(value, r"task 8[^.]{0,200}\b466\b")
                self.assertRegex(
                    value,
                    r"fresh task 9 complete static gate[^.]{0,200}\b474\b",
                )

    def test_svg_and_html_are_passive_and_self_contained(self):
        self.assertTrue(SVG.is_file())
        svg_text = SVG.read_text(encoding="utf-8")
        svg_root = ET.fromstring(svg_text)
        forbidden_svg_tags = {
            "script",
            "iframe",
            "object",
            "embed",
            "foreignobject",
        }
        active_reference_attributes = {
            "href",
            "src",
            "data",
            "action",
            "formaction",
        }
        for element in svg_root.iter():
            tag = element.tag.rsplit("}", 1)[-1].lower()
            self.assertNotIn(tag, forbidden_svg_tags)
            for raw_name, value in element.attrib.items():
                name = raw_name.rsplit("}", 1)[-1].lower()
                self.assertFalse(name.startswith("on"), f"event attribute {name}")
                if name in active_reference_attributes:
                    self.assertTrue(
                        value.startswith("#"),
                        f"external SVG reference {name}={value!r}",
                    )
                self.assertNotRegex(value.lower(), r"(?:javascript|data|file):")
        self.assertNotIn("@import", svg_text.lower())
        for reference in re.findall(r"url\(\s*([^\)]+?)\s*\)", svg_text):
            self.assertTrue(
                reference.strip("\"'").startswith("#"),
                f"external CSS reference {reference!r}",
            )

        self.assertTrue(HYBRID_INLINE.is_file())
        html_text = HYBRID_INLINE.read_text(encoding="utf-8")
        self.assertTrue(
            html_text.lstrip().startswith('<div id="kil-hybrid-architecture">')
        )
        self.assertNotRegex(
            html_text.lower(),
            r"<!doctype|<html\b|<head\b|<body\b|<meta\b",
        )
        parser = _PassiveHTMLParser()
        parser.feed(html_text)
        parser.close()
        self.assertEqual(parser.violations, [])
        self.assertNotIn("@import", html_text.lower())
        self.assertNotRegex(html_text.lower(), r"url\s*\(")
        self.assertNotRegex(html_text.lower(), r"(?:javascript|data|file):")

        self.assertTrue(HYBRID_STANDALONE.is_file())
        standalone_bytes = HYBRID_STANDALONE.read_bytes()
        standalone_text = standalone_bytes.decode("utf-8")
        self.assertEqual(standalone_text.encode("utf-8"), standalone_bytes)
        self.assertTrue(standalone_text.lower().lstrip().startswith("<!doctype html>"))
        self.assertRegex(
            standalone_text.lower(),
            r'<meta\s+charset=["\']utf-8["\']\s*/?>',
        )
        self.assertIn("light-dark(", standalone_text)
        for variable in (
            "--background:",
            "--foreground:",
            "--muted:",
            "--muted-foreground:",
            "--accent:",
            "--border:",
            "--viz-series-1:",
            "--viz-series-2:",
            "--viz-series-3:",
        ):
            with self.subTest(standalone_variable=variable):
                self.assertIn(variable, standalone_text)
        self.assertNotIn("--color-", standalone_text)
        standalone_parser = _PassiveHTMLParser()
        standalone_parser.feed(standalone_text)
        standalone_parser.close()
        self.assertEqual(standalone_parser.violations, [])
        self.assertNotIn("@import", standalone_text.lower())
        self.assertNotRegex(standalone_text.lower(), r"url\s*\(")
        self.assertNotRegex(standalone_text.lower(), r"(?:javascript|data|file):")
        self.assertIn(CITATION_URL, standalone_text)

    def test_legacy_execution_records_are_append_only_and_superseded(self):
        for path, (prefix_size, expected_digest) in LEGACY_PREFIXES.items():
            with self.subTest(path=path.relative_to(ROOT)):
                data = path.read_bytes()
                self.assertGreater(len(data), prefix_size)
                self.assertEqual(
                    sha256(data[:prefix_size]).hexdigest(),
                    expected_digest,
                    "the historical execution record was rewritten",
                )
                note = data[prefix_size:].decode("utf-8")
                stripped_note = note.lstrip()
                if stripped_note.startswith("---"):
                    stripped_note = stripped_note[3:].lstrip()
                self.assertTrue(stripped_note.startswith("## Supersession"))
                self.assertIn(REQUEST_DRIVER_DESIGN, note)
                self.assertIn(REQUEST_DRIVER_PLAN, note)
                self.assertIn("historical", note.lower())

    def test_live_board_is_ignored_and_not_tracked(self):
        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", str(LIVE_BOARD.relative_to(ROOT))],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(ignored.returncode, 0, "the live board is not ignored")
        tracked = subprocess.run(
            [
                "git",
                "ls-files",
                "--error-unmatch",
                "--",
                str(LIVE_BOARD.relative_to(ROOT)),
            ],
            cwd=ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.assertNotEqual(tracked.returncode, 0, "the ignored live board is tracked")
        if LIVE_BOARD.exists():
            self.assertTrue(LIVE_BOARD.is_file())
            live_board_text = LIVE_BOARD.read_text(encoding="utf-8")
            self.assertIn(CITATION_URL, live_board_text)
            live_board_value = normalized(live_board_text).lower()
            self.assertRegex(live_board_value, r"task 11")
            self.assertRegex(live_board_value, r"central request attempts:\s*1")
            self.assertRegex(live_board_value, r"retry prohibited|never retry")


if __name__ == "__main__":
    unittest.main()
