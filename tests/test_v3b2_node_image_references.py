"""Independent crictl/ctr producer fixtures; no container runtime access."""
from dataclasses import FrozenInstanceError, replace
import json
import unittest
from unittest.mock import patch

from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_proofs import RawObservation
from kil.v3b2_node_image_references import (
    ExpectedNodeImage, NodeImageReferenceError, node_image_inspect_argv,
    validate_node_image_references,
)


IDENTITY = OwnedIdentity("kil-v3-lab", "unix:///tmp/owned/kil-v3-lab/docker.sock",
                         "kil-v3-lab", "/tmp/owned/kubeconfig", "cluster-uid", "a" * 64)
CONFIG = "/tmp/owned/docker-config"
ENV = (("DOCKER_CONFIG", CONFIG), ("DOCKER_HOST", IDENTITY.docker_host))
KIL = "kil.local/kil-v3b2:sha256-" + "b" * 64
ENVOY = "docker.io/envoyproxy/envoy@sha256:" + "d" * 64
TAG = "docker.io/envoyproxy/envoy:v1.39.1"
MANIFEST = "application/vnd.oci.image.manifest.v1+json"
INDEX = "application/vnd.oci.image.index.v1+json"


def fixture(*, tagged=False):
    expected = (
        ExpectedNodeImage("kil", KIL, "sha256:" + "c" * 64,
                          "sha256:" + "b" * 64, MANIFEST, (KIL,), (), "sha256:" + "c" * 64),
        ExpectedNodeImage("envoy", ENVOY, "sha256:" + "e" * 64,
                          "sha256:" + "d" * 64, INDEX, (TAG,) if tagged else (),
                          (ENVOY,), "sha256:" + "e" * 64),
    )
    inspections = []
    rows = ["REF TYPE DIGEST STATUS SIZE UNPACKED"]
    for index, image in enumerate(expected):
        status = {"id": image.config_digest, "repoTags": list(image.allowed_repo_tags),
                  "repoDigests": list(image.allowed_repo_digests), "size": "1048576",
                  "username": "", "pinned": False}
        if index == 0:
            status["uid"] = {"value": "65532"}
        # Independently spell command rather than using production argv builder.
        argv = ("docker", "exec", IDENTITY.node_container_id, "/usr/local/bin/crictl",
                "--runtime-endpoint", "unix:///run/containerd/containerd.sock",
                "--image-endpoint", "unix:///run/containerd/containerd.sock", "--timeout", "10s",
                "inspecti", "--quiet", "--output", "json", image.query_reference)
        inspections.append(RawObservation("cri_image_" + str(index), argv, ENV, 0,
                                          json.dumps({"status": status}).encode(), b""))
        for alias in (*image.allowed_repo_tags, *image.allowed_repo_digests):
            rows.append(f"{alias} {image.target_media_type} {image.target_digest} complete (4/4) 1.0 MiB true")
    node = RawObservation("node_images", ("docker", "exec", IDENTITY.node_container_id,
        "/usr/local/bin/ctr", "--address", "/run/containerd/containerd.sock", "--namespace", "k8s.io",
        "images", "check", "--snapshotter", "overlayfs"), ENV, 0, ("\n".join(rows) + "\n").encode(), b"")
    return dict(identity=IDENTITY, docker_config=CONFIG, expected_images=expected,
                inspections=tuple(inspections), node_images=node)


def changed_status(args, index, mutate):
    rows = list(args["inspections"])
    document = json.loads(rows[index].stdout)
    mutate(document["status"])
    rows[index] = replace(rows[index], stdout=json.dumps(document).encode())
    return {**args, "inspections": tuple(rows)}


class NodeImageReferencesTest(unittest.TestCase):
    def test_kil_fallback_and_envoy_no_tag_use_distinct_content_identities(self):
        args = fixture()
        proof = validate_node_image_references(**args)
        kil, envoy = proof.bindings
        self.assertEqual(kil.image_ref, "sha256:" + "c" * 64)
        self.assertEqual(kil.runtime_image, KIL)
        self.assertEqual(envoy.image_ref, ENVOY)
        self.assertEqual(envoy.runtime_image, "sha256:" + "e" * 64)
        self.assertNotEqual(envoy.runtime_image, ENVOY)
        self.assertEqual(kil.uid, "65532")
        self.assertFalse(proof.runtime_contract_complete)
        self.assertEqual(len(proof.observation_sha256), 3)
        self.assertEqual(node_image_inspect_argv(IDENTITY.node_container_id, KIL), args["inspections"][0].argv)
        with self.assertRaises(FrozenInstanceError): proof.runtime_contract_complete = True

    def test_reviewed_envoy_tag_preserves_runtime_image_separately(self):
        proof = validate_node_image_references(**fixture(tagged=True))
        self.assertEqual(proof.bindings[1].runtime_image, TAG)
        self.assertEqual(proof.bindings[1].image_ref, ENVOY)

    def test_public_inspection_command_accepts_only_exact_pipeline_queries(self):
        for reference in (TAG, "kil.local/kil-v3b2:latest", KIL + "x", ENVOY[:-1],
                          "docker.io/envoyproxy/envoy@sha256:" + "D" * 64,
                          ENVOY + " --quiet", "kil.local/kil-v3b2@sha256:" + "b" * 64):
            with self.subTest(reference=reference), self.assertRaises(NodeImageReferenceError):
                node_image_inspect_argv(IDENTITY.node_container_id, reference)

    def test_reference_order_is_retained_and_selects_first_runtime_tag(self):
        args = fixture(tagged=True)
        other = "docker.io/envoyproxy/envoy:reviewed"
        expected = replace(args["expected_images"][1], allowed_repo_tags=tuple(sorted((TAG, other))))
        args["expected_images"] = (args["expected_images"][0], expected)
        args["node_images"] = replace(args["node_images"], stdout=args["node_images"].stdout +
            f"{other} {INDEX} {expected.target_digest} complete (4/4) 1.0 MiB true\n".encode())
        args = changed_status(args, 1, lambda row: row.update(repoTags=[TAG, other]))
        proof = validate_node_image_references(**args)
        self.assertEqual(proof.bindings[1].repo_tags, (TAG, other))
        self.assertEqual(proof.bindings[1].runtime_image, TAG)
        reversed_args = changed_status(args, 1, lambda row: row.update(repoTags=[other, TAG]))
        reversed_proof = validate_node_image_references(**reversed_args)
        self.assertEqual(reversed_proof.bindings[1].runtime_image, other)
        self.assertNotEqual(proof.observation_sha256, reversed_proof.observation_sha256)

    def test_uid_signed_bounds_and_optional_username_follow_producer_schema(self):
        for uid in (str(-2**63), "0", str(2**63 - 1)):
            args = changed_status(fixture(), 0, lambda row: row.update(uid={"value": uid}))
            self.assertEqual(validate_node_image_references(**args).bindings[0].uid, uid)
        args = changed_status(fixture(), 1, lambda row: row.update(username="envoy", size=str(2**64 - 1)))
        self.assertEqual(validate_node_image_references(**args).bindings[1].username, "envoy")

    def test_missing_alias_and_duplicated_ctr_row_are_not_hidden_by_other_images(self):
        args = fixture(tagged=True)
        raw = args["node_images"].stdout
        without_tag = b"\n".join(line for line in raw.split(b"\n") if not line.startswith(TAG.encode()))
        for payload in (without_tag, raw + raw.splitlines(keepends=True)[1]):
            with self.subTest(payload=payload), self.assertRaises(NodeImageReferenceError):
                validate_node_image_references(**{**args, "node_images": replace(args["node_images"], stdout=payload)})

    def test_ctr_accepts_only_bounded_lf_rows_and_printable_tab_spacing(self):
        args = fixture()
        raw = args["node_images"].stdout
        for separator in (b"\r", b"\v", b"\f", b"\x1c", b"\x1d", b"\x1e", b"\r\n"):
            payload = raw.rstrip(b"\n").replace(b"\n", separator) + b"\n"
            with self.subTest(separator=separator), self.assertRaises(NodeImageReferenceError):
                validate_node_image_references(**{**args, "node_images": replace(args["node_images"], stdout=payload)})
        extra = [f"other.invalid/image:{index} {MANIFEST} sha256:{'9' * 64} complete (2/2) 1.0 KiB true\n".encode()
                 for index in range(255)]
        # Two required image rows plus 255 others exceed 256 data rows.
        with self.assertRaises(NodeImageReferenceError):
            validate_node_image_references(**{**args, "node_images": replace(args["node_images"], stdout=raw + b"".join(extra))})
        disguised = (raw + b"".join(extra)).rstrip(b"\n").replace(b"\n", b"\v") + b"\n"
        with self.assertRaises(NodeImageReferenceError):
            validate_node_image_references(**{**args, "node_images": replace(args["node_images"], stdout=disguised)})
        valid = raw.replace(b" ", b"\t")
        self.assertFalse(validate_node_image_references(**{**args, "node_images":
            replace(args["node_images"], stdout=valid)}).runtime_contract_complete)

    def test_config_alias_query_and_target_chain_fail_independently(self):
        args = fixture(tagged=True)
        for index, key, value in ((0, "id", "sha256:" + "b" * 64),
                                  (0, "repoTags", []),
                                  (0, "repoDigests", ["kil.local/kil-v3b2@sha256:" + "b" * 64]),
                                  (1, "repoDigests", ["wrong.invalid/envoy@sha256:" + "d" * 64]),
                                  (1, "repoTags", ["docker.io/envoyproxy/envoy:unreviewed"])):
            with self.subTest(key=key, value=value), self.assertRaises(NodeImageReferenceError):
                validate_node_image_references(**changed_status(args, index, lambda row: row.update({key: value})))
        for old, new in (("sha256:" + "d" * 64 + " complete", "sha256:" + "f" * 64 + " complete"),
                         ("complete (4/4)", "incomplete (3/4)"),
                         ("MiB true", "MiB false"), (INDEX, MANIFEST)):
            with self.subTest(old=old), self.assertRaises(NodeImageReferenceError):
                validate_node_image_references(**{**args, "node_images": replace(args["node_images"],
                    stdout=args["node_images"].stdout.replace(old.encode(), new.encode()))})

    def test_quiet_schema_types_and_integer_ranges_are_exact(self):
        args = fixture()
        for key, value in (("size", 1), ("size", "01"), ("size", "0"),
                           ("size", str(2**64)), ("pinned", 0), ("username", None),
                           ("uid", {"value": 65532}), ("uid", {"value": "-0"}),
                           ("uid", {"value": str(2**63)}), ("uid", {"value": "0", "extra": 1}),
                           ("spec", {}), ("repoTags", KIL)):
            with self.subTest(key=key, value=value), self.assertRaises(NodeImageReferenceError):
                validate_node_image_references(**changed_status(args, 0, lambda row: row.update({key: value})))
        for raw in (b'{"status":{},"status":{}}', b'{"status":{},"info":{}}',
                    b'{"status":{"size":NaN}}', b'[]', b'{}', b'{"status":'):
            with self.subTest(raw=raw), self.assertRaises(NodeImageReferenceError):
                validate_node_image_references(**{**args, "inspections":
                    (replace(args["inspections"][0], stdout=raw), args["inspections"][1])})

    def test_node_command_environment_and_transport_are_bound(self):
        args = fixture()
        row = args["inspections"][0]
        for altered in (replace(row, argv=(*row.argv[:2], "f" * 64, *row.argv[3:])),
                        replace(row, argv=(*row.argv[:-1], ENVOY)),
                        replace(row, env=(("DOCKER_HOST", "unix:///foreign/kil-v3-lab/docker.sock"),)),
                        replace(row, env=(*ENV, ("DOCKER_CONTEXT", "foreign"))),
                        replace(row, returncode=1), replace(row, stderr=b"warning"),
                        replace(row, label="cri_image_1")):
            with self.subTest(row=altered), self.assertRaises(NodeImageReferenceError):
                validate_node_image_references(**{**args, "inspections": (altered, args["inspections"][1])})
        with self.assertRaises(NodeImageReferenceError):
            validate_node_image_references(**{**args, "identity": replace(IDENTITY, node_container_id=None)})

    def test_cardinality_and_byte_bounds_precede_parsing_or_hashing(self):
        args = fixture()
        with patch("kil.v3b2_node_image_references.json.loads", side_effect=AssertionError("parsed")), \
             patch("kil.v3b2_node_image_references.sha256", side_effect=AssertionError("hashed")):
            for key, value in (("inspections", (*args["inspections"], args["inspections"][0])),
                               ("expected_images", args["expected_images"][:1]),
                               ("inspections", (replace(args["inspections"][0], stdout=b"x" * 16385), args["inspections"][1]))):
                with self.subTest(key=key), self.assertRaises(NodeImageReferenceError):
                    validate_node_image_references(**{**args, key: value})

    def test_constructor_reconstruction_rejects_tampering(self):
        proof = validate_node_image_references(**fixture())
        for changes in ({"runtime_contract_complete": True},
                        {"observation_sha256": ("0" * 64,) * 3},
                        {"identity": replace(IDENTITY, node_container_id="f" * 64)},
                        {"docker_config": "/tmp/other"}):
            with self.subTest(changes=changes), self.assertRaises(NodeImageReferenceError): replace(proof, **changes)
        with self.assertRaises(NodeImageReferenceError): replace(proof.bindings[1], runtime_image=ENVOY)
        poisoned = fixture()
        object.__setattr__(poisoned["expected_images"][0], "config_digest", "bad")
        with self.assertRaises(NodeImageReferenceError): validate_node_image_references(**poisoned)

    def test_forged_binding_bounds_precede_proof_replay_hashing(self):
        proof = validate_node_image_references(**fixture())
        poisoned = replace(proof.bindings[0])
        object.__setattr__(poisoned, "repo_tags", (KIL,) * 9)
        with patch("kil.v3b2_node_image_references.sha256", side_effect=AssertionError("hashed")):
            with self.assertRaises(NodeImageReferenceError):
                replace(proof, bindings=(poisoned, proof.bindings[1]))

    def test_expected_descriptor_rejects_manifest_config_and_saved_input_confusion(self):
        image = fixture()["expected_images"][0]
        for changes in ({"query_reference": "kil.local/kil-v3b2:sha256-" + "9" * 64},
                        {"saved_container_image": image.query_reference},
                        {"allowed_repo_tags": ("evil.invalid/kil:tag",)},
                        {"target_media_type": "text/plain"}):
            with self.subTest(changes=changes), self.assertRaises(NodeImageReferenceError): replace(image, **changes)

    def test_four_content_identities_are_distinct_before_candidate_parsing(self):
        for collision in ("kil_config_envoy_target", "envoy_config_kil_target", "shared_target"):
            args = fixture()
            kil, envoy = args["expected_images"]
            if collision == "kil_config_envoy_target":
                kil = replace(kil, config_digest=envoy.target_digest,
                              saved_container_image=envoy.target_digest)
            elif collision == "envoy_config_kil_target":
                envoy = replace(envoy, config_digest=kil.target_digest,
                                saved_container_image=kil.target_digest)
            else:
                query = "docker.io/envoyproxy/envoy@" + kil.target_digest
                envoy = replace(envoy, target_digest=kil.target_digest,
                                query_reference=query, allowed_repo_digests=(query,))
                args["inspections"] = (args["inspections"][0], replace(args["inspections"][1],
                    argv=(*args["inspections"][1].argv[:-1], query)))
            args["expected_images"] = (kil, envoy)
            with self.subTest(collision=collision), \
                 patch("kil.v3b2_node_image_references.json.loads", side_effect=AssertionError("parsed")), \
                 patch("kil.v3b2_node_image_references.sha256", side_effect=AssertionError("hashed")), \
                 self.assertRaisesRegex(NodeImageReferenceError, "four.*distinct"):
                validate_node_image_references(**args)


if __name__ == "__main__": unittest.main()
