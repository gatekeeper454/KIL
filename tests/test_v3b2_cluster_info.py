"""Independent fixtures for kubeadm's public cluster-info bootstrap proof."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from hashlib import sha256
import base64
import builtins
import hmac
import json
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID

from kil import v3b2_cluster_info as cluster_info_module
from kil.v3b2_cluster_info import (
    ClusterInfoError, ClusterInfoProof, validate_cluster_info,
)


TOKEN_ID = "abc123"
TOKEN_SECRET = b"0123456789abcdef"
SERVER = "https://10.96.0.1:443"
EXPIRATION = "2026-09-08T00:00:00.123456789Z"
CAPTURED = "2026-09-07T00:00:00.000000001Z"


def certificate(*, ca=True):
    key = Ed25519PrivateKey.generate()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "cluster-ca")])
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(7001)
        .not_valid_before(datetime(2025, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime(2035, 1, 1, tzinfo=timezone.utc))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .sign(key, algorithm=None)
    )
    return (cert.public_bytes(serialization.Encoding.PEM),
            cert.public_bytes(serialization.Encoding.DER))


CA_PEM, CA_DER = certificate()
LEAF_PEM, _ = certificate(ca=False)
CA_DIGEST = sha256(CA_DER).hexdigest()


def kubeconfig(*, server=SERVER, pem=CA_PEM, order="normal", empties="null"):
    ca_data = base64.b64encode(pem).decode("ascii")
    cluster = [
        "- cluster:",
        f"    certificate-authority-data: {ca_data}",
        f"    server: {server}",
        '  name: ""',
    ]
    if order == "alternate":
        cluster = [
            '- name: ""',
            "  cluster:",
            f"    server: {server}",
            f"    certificate-authority-data: {ca_data}",
        ]
        top = ["kind: Config", "preferences: {}", "clusters:", *cluster,
               "apiVersion: v1", "users: []", 'current-context: ""', "contexts: []"]
    else:
        empty = "null" if empties == "null" else "[]"
        top = ["apiVersion: v1", "clusters:", *cluster, f"contexts: {empty}",
               'current-context: ""', "kind: Config", "preferences: {}", f"users: {empty}"]
    return "\n".join(top) + "\n"


def b64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def detached(content, *, secret=TOKEN_SECRET, header=None, protected=None, payload=""):
    if protected is None:
        if header is None:
            header = {"alg": "HS256", "kid": TOKEN_ID}
        protected = b64url(json.dumps(header, separators=(",", ":")).encode())
    encoded_content = b64url(content.encode("utf-8"))
    signature = hmac.new(secret, f"{protected}.{encoded_content}".encode("ascii"), sha256).digest()
    return f"{protected}.{payload}.{b64url(signature)}"


def metadata(*, uid="uid-cluster-info", rv="41"):
    return {
        "name": "cluster-info", "namespace": "kube-public", "uid": uid,
        "resourceVersion": rv, "creationTimestamp": "2026-09-06T00:00:00Z",
        "managedFields": [{"manager": "kubeadm", "operation": "Update",
                            "apiVersion": "v1", "fieldsType": "FieldsV1",
                            "fieldsV1": {"f:data": {}}}],
    }


def document(*, config=None, rv="41", uid="uid-cluster-info", signature=True,
             jws=None):
    config = kubeconfig() if config is None else config
    data = {"kubeconfig": config}
    if signature:
        data[f"jws-kubeconfig-{TOKEN_ID}"] = detached(config) if jws is None else jws
    return {"apiVersion": "v1", "kind": "ConfigMap",
            "metadata": metadata(uid=uid, rv=rv), "data": data}


def validate(value=None, **changes):
    arguments = dict(internal_server=SERVER,
                     cluster_ca_certificate_der_sha256=CA_DIGEST,
                     token_id=TOKEN_ID, token_secret=TOKEN_SECRET,
                     token_expiration=EXPIRATION, captured_at=CAPTURED)
    arguments.update(changes)
    return validate_cluster_info(document() if value is None else value, **arguments)


class StringSubclass(str):
    pass


class BytesSubclass(bytes):
    pass


class DictSubclass(dict):
    pass


class ClusterInfoTest(unittest.TestCase):
    def assertInvalid(self, value=None, **changes):
        with self.assertRaises(ClusterInfoError):
            validate(value, **changes)

    def test_active_success_is_frozen_minimal_and_deterministic(self):
        observed = document()
        original = deepcopy(observed)
        proof = validate(observed)
        self.assertEqual(proof, validate(observed))
        self.assertEqual(observed, original)
        self.assertEqual(proof.api_version, "v1")
        self.assertEqual(proof.kind, "ConfigMap")
        self.assertEqual(proof.namespace, "kube-public")
        self.assertEqual(proof.name, "cluster-info")
        self.assertEqual(proof.kubeconfig_sha256,
                         sha256(kubeconfig().encode()).hexdigest())
        self.assertTrue(proof.signature_present)
        self.assertEqual(proof.jws_sha256_or_none,
                         sha256(observed["data"][f"jws-kubeconfig-{TOKEN_ID}"].encode()).hexdigest())
        self.assertFalse(proof.runtime_contract_complete)
        self.assertNotIn(TOKEN_SECRET.decode(), repr(proof))
        self.assertNotIn("certificate-authority-data", repr(proof))
        self.assertNotIn("eyJ", repr(proof))
        with self.assertRaises(FrozenInstanceError):
            proof.uid = "changed"

    def test_header_original_encoding_is_signed_not_reserialized(self):
        config = kubeconfig()
        raw = b'{ "kid" : "abc123", "alg" : "HS256" }'
        jws = detached(config, protected=b64url(raw))
        self.assertTrue(validate(document(config=config, jws=jws)).signature_present)
        changed = config.replace("kind: Config", "kind:  Config")
        self.assertInvalid(document(config=changed, jws=jws))

    def test_secret_only_is_hmac_key(self):
        config = kubeconfig()
        full = TOKEN_ID.encode() + b"." + TOKEN_SECRET
        self.assertInvalid(document(config=config, jws=detached(config, secret=full)))

    def test_signature_and_header_fail_closed(self):
        config = kubeconfig()
        cases = {
            "bad signature": detached(config)[:-1] + ("A" if detached(config)[-1] != "A" else "B"),
            "wrong alg": detached(config, header={"alg": "HS384", "kid": TOKEN_ID}),
            "wrong kid": detached(config, header={"alg": "HS256", "kid": "def456"}),
            "extra header": detached(config, header={"alg": "HS256", "kid": TOKEN_ID, "typ": "JWT"}),
            "duplicate header": detached(config, protected=b64url(b'{"alg":"HS256","alg":"HS256","kid":"abc123"}')),
            "payload": detached(config, payload="eA"),
            "protected padding": detached(config).replace(".", "=.", 1),
            "signature padding": detached(config) + "=",
            "empty protected": "." + detached(config).split(".", 1)[1],
            "invalid alphabet": "*." + detached(config).split(".", 1)[1],
            "extra segment": detached(config) + ".x",
            "nonascii": detached(config) + "é",
        }
        for label, jws in cases.items():
            with self.subTest(label=label):
                self.assertInvalid(document(config=config, jws=jws))

    def test_data_key_lifecycle_is_exact(self):
        for mutate in (
            lambda d: d["data"].pop(f"jws-kubeconfig-{TOKEN_ID}"),
            lambda d: d["data"].update(extra="x"),
            lambda d: d["data"].update({"jws-kubeconfig-def456": "x"}),
            lambda d: d["data"].pop("kubeconfig"),
        ):
            value = document()
            mutate(value)
            self.assertInvalid(value)

    def test_token_and_evidence_exact_types_and_grammar(self):
        cases = [
            {"token_id": "ABC123"}, {"token_id": "abc12"},
            {"token_id": StringSubclass(TOKEN_ID)}, {"token_secret": b"short"},
            {"token_secret": b"0123456789abcde!"},
            {"token_secret": BytesSubclass(TOKEN_SECRET)},
            {"internal_server": StringSubclass(SERVER)},
            {"internal_server": "http://10.96.0.1"},
            {"internal_server": "https://user@host"},
            {"internal_server": "https://host/path?q=1"},
            {"internal_server": "https://host?"},
            {"cluster_ca_certificate_der_sha256": CA_DIGEST.upper()},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertInvalid(**changes)

    def test_timestamps_are_real_exact_utc_and_equality_is_expired(self):
        for changes in (
            {"captured_at": "2026-02-30T00:00:00Z"},
            {"captured_at": "2026-09-07T00:00:00+00:00"},
            {"captured_at": "2026-09-07T00:00:00.1234567890Z"},
            {"token_expiration": StringSubclass(EXPIRATION)},
        ):
            self.assertInvalid(**changes)
        self.assertInvalid(captured_at=EXPIRATION)

    def test_expired_removal_requires_qualifying_prior_and_advance(self):
        prior_source = document()
        prior = validate(prior_source)
        expired = "2026-09-08T00:00:00.123456789Z"
        current = document(rv="42", signature=False)
        proof = validate(current, captured_at=expired, prior=prior,
                         prior_document=prior_source)
        self.assertFalse(proof.signature_present)
        self.assertIsNone(proof.jws_sha256_or_none)
        for label, value, changes in (
            ("first", current, {"captured_at": expired}),
            ("same rv", document(rv="41", signature=False), {"prior": prior, "prior_document": prior_source, "captured_at": expired}),
            ("stale signature", document(rv="42"), {"prior": prior, "prior_document": prior_source, "captured_at": expired}),
            ("replacement", document(rv="42", uid="uid-new", signature=False), {"prior": prior, "prior_document": prior_source, "captured_at": expired}),
            ("time regression", current, {"prior": prior, "captured_at": "2026-09-06T23:00:00Z"}),
        ):
            with self.subTest(label=label):
                self.assertInvalid(value, **changes)

    def test_expired_prior_binding_drift_fails(self):
        current = document(rv="42", signature=False)
        expired = EXPIRATION
        prior_source = document()
        for changes in (
            {"internal_server": "https://10.96.0.2:443"},
            {"cluster_ca_certificate_der_sha256": "0" * 64},
            {"token_id": "def456"},
            {"token_expiration": "2026-09-08T01:00:00Z"},
        ):
            with self.subTest(changes=changes):
                self.assertInvalid(current, captured_at=expired, prior=validate(),
                                   prior_document=prior_source, **changes)

    def test_active_prior_allows_equal_rv_time_but_rejects_regression_or_drift(self):
        prior = validate()
        self.assertEqual(validate(prior=prior), prior)
        self.assertInvalid(document(rv="40"), prior=prior)
        self.assertInvalid(prior=prior, captured_at="2026-09-06T23:59:59Z")
        changed = kubeconfig(order="alternate")
        self.assertInvalid(document(config=changed, rv="42"), prior=prior)

    def test_equal_resource_version_rejects_alternate_valid_jws_encoding(self):
        prior = validate()
        config = kubeconfig()
        alternate = detached(config, protected=b64url(
            b'{ "kid" : "abc123", "alg" : "HS256" }'))
        self.assertInvalid(document(config=config, rv="41", jws=alternate),
                           prior=prior)

    def test_yaml_allows_order_and_empty_variants(self):
        minimal = "\n".join(kubeconfig().splitlines()[:6] + ["kind: Config"]) + "\n"
        for config in (kubeconfig(order="alternate"), kubeconfig(empties="sequence"),
                       minimal):
            with self.subTest(config=config[:30]):
                proof = validate(document(config=config, jws=detached(config)))
                self.assertTrue(proof.signature_present)

    def test_yaml_server_scalar_allows_legal_url_path_characters(self):
        server = "https://cluster.example/a*b!c&d%7Ce%3Ef"
        config = kubeconfig(server=server)
        proof = validate(document(config=config, jws=detached(config)),
                         internal_server=server)
        self.assertEqual(proof.internal_server, server)

    def test_server_rejects_malformed_authority_controls_and_percent_escapes(self):
        for server in ("https://example.com:", "https://exa\x00mple.com",
                       "https://example.com\\evil/path", "https://example.com/%ZZ",
                       "https://exa%ZZmple.com", "https://exa%mple.com"):
            config = kubeconfig(server=server)
            with self.subTest(server=repr(server)):
                self.assertInvalid(document(config=config, jws=detached(config)),
                                   internal_server=server)

    def test_yaml_structure_is_tightly_closed(self):
        transformations = [
            lambda c: c.replace('name: ""', "name: other"),
            lambda c: c.replace("- cluster:", "- name: \"\"\n  cluster:\n    server: " + SERVER + "\n    certificate-authority-data: " + base64.b64encode(CA_PEM).decode() + "\n- cluster:", 1),
            lambda c: c.replace("server: " + SERVER, "server: https://other:443"),
            lambda c: c.replace("server: " + SERVER, "server: " + SERVER + "\n    insecure-skip-tls-verify: true"),
            lambda c: c.replace("users: null", "users:\n- name: admin"),
            lambda c: c.replace("contexts: null", "contexts:\n- name: ctx"),
            lambda c: c.replace('current-context: ""', "current-context: ctx"),
            lambda c: c.replace('current-context: ""', "current-context:"),
            lambda c: c.replace("preferences: {}", "preferences:\n  colors: true"),
            lambda c: c + "extensions: []\n",
            lambda c: c.replace("kind: Config", "kind: Config # comment"),
            lambda c: c.replace("kind: Config", "kind:\tConfig"),
            lambda c: c.replace("kind: Config", "kind: &x Config"),
            lambda c: c.replace("kind: Config", "kind: |\n  Config"),
            lambda c: c[:-1],
        ]
        for mutate in transformations:
            config = mutate(kubeconfig())
            with self.subTest(config=config[-50:]):
                self.assertInvalid(document(config=config, jws=detached(config)))

    def test_ca_base64_pem_and_constraints_fail_closed(self):
        variants = []
        good_b64 = base64.b64encode(CA_PEM).decode()
        variants.append(kubeconfig().replace(good_b64, good_b64.rstrip("=")))
        variants.append(kubeconfig().replace(good_b64, "%%%"))
        variants.append(kubeconfig().replace(good_b64,
                        base64.b64encode(LEAF_PEM).decode()))
        variants.append(kubeconfig().replace(good_b64,
                        base64.b64encode(CA_PEM + CA_PEM).decode()))
        variants.append(kubeconfig().replace(good_b64,
                        base64.b64encode(CA_PEM + b"garbage").decode()))
        for config in variants:
            self.assertInvalid(document(config=config, jws=detached(config)))
        self.assertInvalid(cluster_ca_certificate_der_sha256="0" * 64)

    def test_root_metadata_and_tree_are_closed_bounded_and_cycle_safe(self):
        mutations = [
            lambda d: d.update(extra=None),
            lambda d: d.update(apiVersion=StringSubclass("v1")),
            lambda d: d.update(kind="Secret"),
            lambda d: d.update(metadata=DictSubclass(d["metadata"])),
            lambda d: d["metadata"].update(labels={}),
            lambda d: d["metadata"].update(uid=""),
            lambda d: d["metadata"].update(resourceVersion="01"),
            lambda d: d["metadata"].update(creationTimestamp="not-time"),
            lambda d: d.update(data=DictSubclass(d["data"])),
        ]
        for mutate in mutations:
            value = document()
            mutate(value)
            self.assertInvalid(value)
        huge = document()
        huge["data"]["extra"] = "x" * (1024 * 1024)
        self.assertInvalid(huge)
        oversized_surrogates = document()
        oversized_surrogates["data"]["extra"] = "\ud800" * (1024 * 1024 + 1)
        with self.assertRaisesRegex(ClusterInfoError, "unbounded"):
            validate(oversized_surrogates)
        cycle = document()
        cycle["loop"] = cycle
        self.assertInvalid(cycle)
        surrogate = document()
        surrogate["data"]["kubeconfig"] = "\ud800"
        self.assertInvalid(surrogate)
        deep = document()
        node = {}
        deep["extra"] = node
        for _ in range(65):
            child = {}
            node["x"] = child
            node = child
        self.assertInvalid(deep)

    def test_wide_containers_fail_before_children_are_scheduled(self):
        for wide in ([None] * 32768, {str(index): None for index in range(32768)}):
            value = document()
            value["wide"] = wide
            original_reversed = builtins.reversed
            def guarded(candidate):
                if candidate is wide:
                    raise AssertionError("oversized container was scheduled")
                return original_reversed(candidate)
            with self.subTest(kind=type(wide).__name__), patch(
                    "builtins.reversed", side_effect=guarded):
                self.assertInvalid(value)

    def test_kubeconfig_bound_and_exact_type(self):
        self.assertInvalid(document(config=StringSubclass(kubeconfig())))
        config = "x" * (256 * 1024 + 1)
        self.assertInvalid(document(config=config, jws=detached(config)))

    def test_private_string_bounds_precede_utf8_encoding(self):
        for changes in ({"internal_server": "\ud800" * 2049},
                        {"captured_at": "\ud800" * 31},
                        {"cluster_ca_certificate_der_sha256": "a" * 65}):
            with self.subTest(field=next(iter(changes))), self.assertRaisesRegex(
                    ClusterInfoError, "unbounded|lowercase SHA-256"):
                validate(**changes)

    def test_expiry_requires_revalidated_raw_prior_evidence(self):
        real = validate()
        fabricated = object.__new__(ClusterInfoProof)
        for name in real.__slots__:
            object.__setattr__(fabricated, name, getattr(real, name))
        with self.assertRaises(ClusterInfoError):
            validate(document(rv="42", signature=False), captured_at=EXPIRATION,
                     prior=fabricated)
        mismatched = object.__new__(ClusterInfoProof)
        for name in real.__slots__:
            object.__setattr__(mismatched, name, getattr(real, name))
        object.__setattr__(mismatched, "jws_sha256_or_none", "0" * 64)
        with self.assertRaises(ClusterInfoError):
            validate(document(rv="42", signature=False), captured_at=EXPIRATION,
                     prior=mismatched, prior_document=document())
        invalid_source = document()
        invalid_source["data"][f"jws-kubeconfig-{TOKEN_ID}"] += "A"
        with self.assertRaises(ClusterInfoError):
            validate(document(rv="42", signature=False), captured_at=EXPIRATION,
                     prior=real, prior_document=invalid_source)
        proof = validate(document(rv="42", signature=False),
                         captured_at=EXPIRATION, prior=real,
                         prior_document=document())
        self.assertFalse(proof.signature_present)

    def test_proof_direct_partial_and_bypass_invariants(self):
        proof = validate()
        values = {name: getattr(proof, name) for name in proof.__slots__}
        for field, replacement in (
            ("api_version", StringSubclass("v1")), ("kind", "Secret"),
            ("namespace", "default"), ("uid", ""), ("resource_version", "0"),
            ("internal_server", "http://bad"),
            ("cluster_ca_certificate_der_sha256", "A" * 64),
            ("token_id", "ABC123"), ("token_expiration", "bad"),
            ("captured_at", EXPIRATION), ("kubeconfig_sha256", "0"),
            ("signature_present", 1), ("jws_sha256_or_none", None),
            ("runtime_contract_complete", True),
        ):
            changed = dict(values)
            changed[field] = replacement
            with self.subTest(field=field), self.assertRaises(ClusterInfoError):
                ClusterInfoProof(**changed)
        partial = object.__new__(ClusterInfoProof)
        with self.assertRaises(ClusterInfoError):
            validate(prior=partial)
        forged = object.__new__(ClusterInfoProof)
        for name, value in values.items():
            object.__setattr__(forged, name, value)
        object.__setattr__(forged, "runtime_contract_complete", True)
        with self.assertRaises(ClusterInfoError):
            validate(prior=forged)

    def test_export_surface_is_tuple(self):
        self.assertIs(type(cluster_info_module.__all__), tuple)


if __name__ == "__main__":
    unittest.main()
