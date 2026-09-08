"""Independent fixtures for the exact kubeadm trust ConfigMap relationship."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import base64
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID

from kil import v3b2_trust_configmaps as trust_module
from kil.v3b2_trust_configmaps import (
    ExtensionAuthBinding,
    LegacyTrackingBinding,
    RootCABinding,
    TrustConfigMapsError,
    TrustConfigMapsProof,
    validate_trust_configmaps,
)


ROOT_NAMESPACES = (
    "default", "kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed",
    "kube-node-lease", "kube-public", "kube-system", "local-path-storage",
)
DESCRIPTION = (
    "Contains a CA bundle that can be used to verify the kube-apiserver when "
    "using internal endpoints such as the internal service IP or "
    "kubernetes.default.svc. No other usage is guaranteed across distributions."
)
EXTENSION_DATA = {
    "client-ca-file": None,
    "requestheader-client-ca-file": None,
    "requestheader-username-headers": '["X-Remote-User"]',
    "requestheader-group-headers": '["X-Remote-Group"]',
    "requestheader-extra-headers-prefix": '["X-Remote-Extra-"]',
    "requestheader-allowed-names": '["front-proxy-client"]',
}


def certificate(common_name: str, serial: int, *, ca: bool = True,
                include_constraints: bool = True) -> tuple[bytes, bytes]:
    key = Ed25519PrivateKey.generate()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(datetime(2025, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime(2035, 1, 1, tzinfo=timezone.utc))
    )
    if include_constraints:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=ca, path_length=None), critical=True,
        )
    cert = builder.sign(key, algorithm=None)
    return (
        cert.public_bytes(serialization.Encoding.PEM),
        cert.public_bytes(serialization.Encoding.DER),
    )


CLUSTER_PEM, CLUSTER_DER = certificate("kubernetes", 101)
FRONT_PEM, FRONT_DER = certificate("front-proxy", 102)
OTHER_PEM, OTHER_DER = certificate("other", 103)
LEAF_PEM, _ = certificate("not-a-ca", 104, ca=False)
NO_CONSTRAINTS_PEM, _ = certificate("missing-basic-constraints", 105,
                                    include_constraints=False)


def digest(der: bytes) -> str:
    return sha256(der).hexdigest()


def der_tlv(value: bytes, offset: int) -> tuple[int, int, int]:
    tag = value[offset]
    first = value[offset + 1]
    if first < 128:
        content = offset + 2
        length = first
    else:
        length_octets = first & 0x7F
        content = offset + 2 + length_octets
        length = int.from_bytes(value[offset + 2:content], "big")
    return tag, content, content + length


def der_length(length: int) -> bytes:
    if length < 128:
        return bytes((length,))
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes((0x80 | len(encoded),)) + encoded


def der_wrap(tag: int, content: bytes) -> bytes:
    return bytes((tag,)) + der_length(len(content)) + content


def duplicate_basic_constraints_pem(source_der: bytes) -> bytes:
    outer_tag, outer_content, outer_end = der_tlv(source_der, 0)
    tbs_tag, tbs_content, tbs_end = der_tlv(source_der, outer_content)
    if outer_tag != 0x30 or tbs_tag != 0x30 or outer_end != len(source_der):
        raise AssertionError("fixture certificate is not canonical DER")
    cursor = tbs_content
    extensions_start = -1
    extensions_end = -1
    while cursor < tbs_end:
        tag, _, end = der_tlv(source_der, cursor)
        if tag == 0xA3:
            extensions_start, extensions_end = cursor, end
            break
        cursor = end
    if extensions_start < 0:
        raise AssertionError("fixture certificate has no extensions")
    _, explicit_content, _ = der_tlv(source_der, extensions_start)
    inner_tag, inner_content, inner_end = der_tlv(source_der, explicit_content)
    _, _, first_extension_end = der_tlv(source_der, inner_content)
    first_extension = source_der[inner_content:first_extension_end]
    inner = der_wrap(0x30, source_der[inner_content:inner_end] + first_extension)
    explicit = der_wrap(0xA3, inner)
    tbs = der_wrap(0x30, source_der[tbs_content:extensions_start] + explicit
                   + source_der[extensions_end:tbs_end])
    malformed = der_wrap(0x30, tbs + source_der[tbs_end:outer_end])
    return (b"-----BEGIN CERTIFICATE-----\n" + base64.encodebytes(malformed)
            + b"-----END CERTIFICATE-----\n")


DUPLICATE_CONSTRAINTS_PEM = duplicate_basic_constraints_pem(CLUSTER_DER)


def metadata(namespace: str, name: str, serial: int, *, root: bool = False,
             timestamp: str = "2026-09-06T00:00:01.123456789Z") -> dict:
    value = {
        "name": name,
        "namespace": namespace,
        "uid": f"uid-{serial}",
        "resourceVersion": str(serial),
        "creationTimestamp": timestamp,
        "managedFields": [{
            "manager": "kube-controller-manager",
            "operation": "Update",
            "apiVersion": "v1",
            "fieldsType": "FieldsV1",
            "fieldsV1": {"f:data": {}},
            "time": "2026-09-06T00:00:01Z",
        }],
    }
    if root:
        value["annotations"] = {"kubernetes.io/description": DESCRIPTION}
    return value


def objects(*, since: str = "2026-09-06",
            legacy_timestamp: str = "2026-09-06T00:00:01Z") -> tuple[dict, ...]:
    result = []
    for serial, namespace in enumerate(reversed(ROOT_NAMESPACES), 11):
        result.append({
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": metadata(namespace, "kube-root-ca.crt", serial, root=True),
            "data": {"ca.crt": CLUSTER_PEM.decode("ascii")},
        })
    extension_data = dict(EXTENSION_DATA)
    extension_data["client-ca-file"] = CLUSTER_PEM.decode("ascii")
    extension_data["requestheader-client-ca-file"] = FRONT_PEM.decode("ascii")
    result.append({
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": metadata("kube-system", "extension-apiserver-authentication", 31),
        "data": extension_data,
    })
    result.append({
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": metadata(
            "kube-system", "kube-apiserver-legacy-service-account-token-tracking",
            32, timestamp=legacy_timestamp,
        ),
        "data": {"since": since},
    })
    return tuple(result)


def validate(documents: tuple[dict, ...] | None = None, *,
             cluster: bytes = CLUSTER_PEM, front: bytes = FRONT_PEM) -> TrustConfigMapsProof:
    return validate_trust_configmaps(
        objects() if documents is None else documents,
        cluster_ca_pem=cluster,
        front_proxy_ca_pem=front,
    )


class StringSubclass(str):
    pass


class TupleSubclass(tuple):
    pass


class DictSubclass(dict):
    pass


class TrustConfigMapsTest(unittest.TestCase):
    def test_export_surface_is_immutable(self) -> None:
        self.assertIs(type(trust_module.__all__), tuple)

    def test_success_is_frozen_sorted_deterministic_and_binds_der(self) -> None:
        proof = validate()
        self.assertEqual(proof, validate())
        self.assertEqual(proof.root_ca_bindings, tuple(sorted(proof.root_ca_bindings)))
        self.assertEqual(tuple(row.namespace for row in proof.root_ca_bindings), ROOT_NAMESPACES)
        for row in proof.root_ca_bindings:
            self.assertEqual(
                (row.api_version, row.kind, row.name,
                 row.cluster_certificate_der_sha256),
                ("v1", "ConfigMap", "kube-root-ca.crt", digest(CLUSTER_DER)),
            )
        self.assertEqual(
            (proof.extension_auth_binding.api_version,
             proof.extension_auth_binding.kind,
             proof.extension_auth_binding.namespace,
             proof.extension_auth_binding.name,
             proof.extension_auth_binding.cluster_client_certificate_der_sha256,
             proof.extension_auth_binding.front_proxy_certificate_der_sha256),
            ("v1", "ConfigMap", "kube-system",
             "extension-apiserver-authentication", digest(CLUSTER_DER), digest(FRONT_DER)),
        )
        self.assertEqual(
            (proof.legacy_tracking_binding.namespace, proof.legacy_tracking_binding.name,
             proof.legacy_tracking_binding.since_utc_date,
             proof.legacy_tracking_binding.creation_timestamp),
            ("kube-system", "kube-apiserver-legacy-service-account-token-tracking",
             "2026-09-06", "2026-09-06T00:00:01Z"),
        )
        self.assertIs(proof.runtime_contract_complete, False)
        self.assertEqual(tuple(field.name for field in fields(proof)), (
            "root_ca_bindings", "extension_auth_binding", "legacy_tracking_binding",
            "runtime_contract_complete",
        ))
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            proof.root_ca_bindings = ()  # type: ignore[misc]
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            proof.root_ca_bindings[0].uid = "changed"  # type: ignore[misc]

    def test_input_and_pem_are_not_mutated_or_aliased(self) -> None:
        documents = objects()
        before = deepcopy(documents)
        cluster = bytearray(CLUSTER_PEM)
        with self.assertRaises(TrustConfigMapsError):
            validate_trust_configmaps(documents, cluster_ca_pem=cluster, front_proxy_ca_pem=FRONT_PEM)  # type: ignore[arg-type]
        proof = validate(documents)
        self.assertEqual(documents, before)
        documents[0]["metadata"]["uid"] = "changed-after-validation"
        self.assertNotEqual(proof.root_ca_bindings[-1].uid, "changed-after-validation")
        self.assertFalse(any(
            isinstance(value, bytes)
            for binding in proof.root_ca_bindings
            for value in (getattr(binding, field.name) for field in fields(binding))
        ))

    def test_pem_formatting_variation_for_same_certificate_is_accepted(self) -> None:
        varied_cluster = b"\n  " + CLUSTER_PEM.replace(b"\n", b"\r\n") + b"\t\n"
        varied_front = b"\r\n" + FRONT_PEM.replace(b"\n", b"\r\n") + b" \n"
        changed = deepcopy(objects())
        for item in changed:
            if item["metadata"]["name"] == "kube-root-ca.crt":
                item["data"]["ca.crt"] = varied_cluster.decode("ascii")
            elif item["metadata"]["name"] == "extension-apiserver-authentication":
                item["data"]["client-ca-file"] = varied_cluster.decode("ascii")
                item["data"]["requestheader-client-ca-file"] = varied_front.decode("ascii")
        self.assertEqual(validate(tuple(changed), cluster=varied_cluster, front=varied_front), validate())

    def test_invalid_empty_multiple_duplicate_garbage_and_non_ca_pem_are_rejected(self) -> None:
        malformed = x509.load_pem_x509_certificate(DUPLICATE_CONSTRAINTS_PEM)
        with self.assertRaises(x509.DuplicateExtension):
            _ = malformed.extensions
        bad_bundles = (
            b"", b"not pem", CLUSTER_PEM + FRONT_PEM, CLUSTER_PEM + CLUSTER_PEM,
            CLUSTER_PEM + b"garbage", LEAF_PEM, NO_CONSTRAINTS_PEM,
            DUPLICATE_CONSTRAINTS_PEM,
        )
        for bad in bad_bundles:
            with self.subTest(location="evidence", bad=bad[:24]):
                with self.assertRaises(TrustConfigMapsError):
                    validate(cluster=bad)
            changed = deepcopy(objects())
            changed[0]["data"]["ca.crt"] = bad.decode("ascii")
            with self.subTest(location="observed-root", bad=bad[:24]):
                with self.assertRaises(TrustConfigMapsError):
                    validate(tuple(changed))

    def test_evidence_types_sizes_distinct_roles_and_observed_matches_are_exact(self) -> None:
        for value in ("pem", bytearray(CLUSTER_PEM), memoryview(CLUSTER_PEM), None,
                      b" " * (1024 * 1024 + 1)):
            with self.subTest(role="cluster", value_type=type(value).__name__):
                with self.assertRaises(TrustConfigMapsError):
                    validate_trust_configmaps(objects(), cluster_ca_pem=value, front_proxy_ca_pem=FRONT_PEM)  # type: ignore[arg-type]
        with self.assertRaises(TrustConfigMapsError):
            validate(front=CLUSTER_PEM)
        with self.assertRaises(TrustConfigMapsError):
            validate(cluster=OTHER_PEM)
        changed = deepcopy(objects())
        changed[0]["data"]["ca.crt"] = OTHER_PEM.decode()
        with self.assertRaises(TrustConfigMapsError):
            validate(tuple(changed))
        changed = deepcopy(objects())
        extension = next(row for row in changed if row["metadata"]["name"] == "extension-apiserver-authentication")
        extension["data"]["client-ca-file"], extension["data"]["requestheader-client-ca-file"] = (
            extension["data"]["requestheader-client-ca-file"], extension["data"]["client-ca-file"])
        with self.assertRaises(TrustConfigMapsError):
            validate(tuple(changed))

    def test_exact_tuple_length_item_types_and_identity_set_are_required(self) -> None:
        exact = objects()
        invalid_inputs: list[object] = [list(exact), TupleSubclass(exact), exact[:-1], exact + (deepcopy(exact[0]),)]
        changed = list(exact)
        changed[0] = DictSubclass(changed[0])
        invalid_inputs.append(tuple(changed))
        for index in range(10):
            changed = deepcopy(exact)
            changed[index]["metadata"]["name"] += "-foreign"
            invalid_inputs.append(changed)
            changed = deepcopy(exact)
            changed[index]["metadata"]["namespace"] += "-foreign"
            invalid_inputs.append(changed)
        duplicate = deepcopy(exact)
        duplicate[1]["metadata"]["namespace"] = duplicate[0]["metadata"]["namespace"]
        invalid_inputs.append(duplicate)
        swapped = deepcopy(exact)
        swapped[0]["metadata"]["name"], swapped[-1]["metadata"]["name"] = (
            swapped[-1]["metadata"]["name"], swapped[0]["metadata"]["name"])
        invalid_inputs.append(swapped)
        for value in invalid_inputs:
            with self.subTest(type=type(value).__name__, length=len(value)):
                with self.assertRaises(TrustConfigMapsError):
                    validate_trust_configmaps(value, cluster_ca_pem=CLUSTER_PEM, front_proxy_ca_pem=FRONT_PEM)  # type: ignore[arg-type]

    def test_every_root_metadata_and_data_field_is_closed_and_required(self) -> None:
        for index in range(10):
            base = objects()[index]
            for key in tuple(base):
                changed = deepcopy(objects())
                del changed[index][key]
                with self.subTest(index=index, scope="root", operation="missing", key=key):
                    with self.assertRaises(TrustConfigMapsError):
                        validate(changed)
            for key, value in (("binaryData", {}), ("immutable", False), ("status", {}),
                               ("spec", {}), ("foreign", None)):
                changed = deepcopy(objects())
                changed[index][key] = value
                with self.subTest(index=index, scope="root", operation="extra", key=key):
                    with self.assertRaises(TrustConfigMapsError):
                        validate(changed)
            for key in tuple(base["metadata"]):
                changed = deepcopy(objects())
                del changed[index]["metadata"][key]
                with self.subTest(index=index, scope="metadata", operation="missing", key=key):
                    with self.assertRaises(TrustConfigMapsError):
                        validate(changed)
            for key, value in (("labels", {}), ("ownerReferences", []), ("finalizers", []),
                               ("deletionTimestamp", None), ("generation", 1), ("foreign", "x")):
                changed = deepcopy(objects())
                changed[index]["metadata"][key] = value
                with self.subTest(index=index, scope="metadata", operation="extra", key=key):
                    with self.assertRaises(TrustConfigMapsError):
                        validate(changed)
            data_keys = tuple(base["data"])
            for key in data_keys:
                changed = deepcopy(objects())
                del changed[index]["data"][key]
                with self.subTest(index=index, scope="data", operation="missing", key=key):
                    with self.assertRaises(TrustConfigMapsError):
                        validate(changed)
            changed = deepcopy(objects())
            changed[index]["data"]["foreign"] = "x"
            with self.subTest(index=index, scope="data", operation="extra"):
                with self.assertRaises(TrustConfigMapsError):
                    validate(changed)

    def test_api_identity_annotation_header_keysets_and_values_are_exact_strings(self) -> None:
        for index in range(10):
            for scope, key, value in (
                ("root", "apiVersion", "v2"), ("root", "kind", "Secret"),
                ("root", "apiVersion", StringSubclass("v1")),
                ("metadata", "namespace", StringSubclass(objects()[index]["metadata"]["namespace"])),
                ("metadata", "name", StringSubclass(objects()[index]["metadata"]["name"])),
            ):
                changed = deepcopy(objects())
                target = changed[index] if scope == "root" else changed[index]["metadata"]
                target[key] = value
                with self.subTest(index=index, scope=scope, key=key):
                    with self.assertRaises(TrustConfigMapsError):
                        validate(changed)
        for annotations in ({}, {"kubernetes.io/description": DESCRIPTION + "x"},
                            {"foreign": DESCRIPTION},
                            {"kubernetes.io/description": DESCRIPTION, "foreign": "x"},
                            {"kubernetes.io/description": StringSubclass(DESCRIPTION)}):
            changed = deepcopy(objects())
            changed[0]["metadata"]["annotations"] = annotations
            with self.subTest(annotations=annotations):
                with self.assertRaises(TrustConfigMapsError):
                    validate(changed)
        extension_index = 8
        for key in tuple(EXTENSION_DATA):
            changed = deepcopy(objects())
            if key.endswith("file"):
                changed[extension_index]["data"][key] = OTHER_PEM.decode()
            else:
                changed[extension_index]["data"][key] += " "
            with self.subTest(header_or_ca=key):
                with self.assertRaises(TrustConfigMapsError):
                    validate(changed)
        changed = deepcopy(objects())
        changed[extension_index]["data"]["requestheader-uid-headers"] = '["X-Remote-Uid"]'
        with self.assertRaises(TrustConfigMapsError):
            validate(changed)
        changed = deepcopy(objects())
        changed[extension_index]["metadata"]["annotations"] = {}
        with self.assertRaises(TrustConfigMapsError):
            validate(changed)

    def test_uid_resource_version_timestamp_and_managed_fields_are_strict(self) -> None:
        mutations = (
            ("uid", ""), ("uid", "x" * 129), ("uid", "bad uid"), ("uid", 1),
            ("resourceVersion", "0"), ("resourceVersion", "01"),
            ("resourceVersion", "18446744073709551616"), ("resourceVersion", 1),
            ("creationTimestamp", "2026-02-30T00:00:00Z"),
            ("creationTimestamp", "2026-09-06T00:00:00+00:00"),
            ("creationTimestamp", None), ("managedFields", {}),
            ("managedFields", [{"manager": "x"}]),
        )
        for index in range(10):
            for key, value in mutations:
                changed = deepcopy(objects())
                changed[index]["metadata"][key] = value
                with self.subTest(index=index, key=key, value=value):
                    with self.assertRaises(TrustConfigMapsError):
                        validate(changed)

    def test_decoded_tree_bytes_depth_items_cycles_surrogates_and_json_types_are_bounded(self) -> None:
        cases = []
        huge = deepcopy(objects())
        huge[0]["data"]["ca.crt"] = "x" * (2 * 1024 * 1024 + 1)
        cases.append(huge)
        deep = deepcopy(objects())
        member: object = None
        for _ in range(66):
            member = [member]
        deep[0]["foreign"] = member
        cases.append(deep)
        many = deepcopy(objects())
        many[0]["foreign"] = [None] * 32768
        cases.append(many)
        cyclic = deepcopy(objects())
        cyclic[0]["foreign"] = cyclic[0]
        cases.append(cyclic)
        for value in (1.0, b"bytes", complex(1, 2), object()):
            changed = deepcopy(objects())
            changed[0]["foreign"] = value
            cases.append(changed)
        for value in ("\ud800",):
            changed = deepcopy(objects())
            changed[0]["metadata"]["uid"] = value
            cases.append(changed)
            changed = deepcopy(objects())
            changed[0]["\ud800"] = "x"
            cases.append(changed)
        for case in cases:
            with self.subTest(case=len(cases)):
                with self.assertRaises(TrustConfigMapsError) as raised:
                    validate(case)
                self.assertIsInstance(raised.exception, ValueError)

    def test_tree_caps_reject_before_large_encoding_or_child_scheduling(self) -> None:
        cases = (
            ("_MAX_TREE_BYTES", 8, ({"x": "\ud800" * 32},)),
            ("_MAX_TREE_BYTES", 5, ({"\ud800" * 10: None},)),
            ("_MAX_TREE_ITEMS", 10, ({"x": [object()] + [None] * 19},)),
            ("_MAX_TREE_ITEMS", 3, ({"a": 1, "b": 2, "\ud800": 3},)),
        )
        for limit, value, documents in cases:
            with self.subTest(limit=limit, value=value):
                with patch.object(trust_module, limit, value):
                    with self.assertRaisesRegex(TrustConfigMapsError, "unbounded"):
                        trust_module._validate_tree(documents)

    def test_legacy_same_day_and_previous_day_are_accepted_only(self) -> None:
        same = validate(objects(since="2026-09-06", legacy_timestamp="2026-09-06T23:59:59Z"))
        previous = validate(objects(since="2026-09-05", legacy_timestamp="2026-09-06T00:00:00Z"))
        self.assertEqual(same.legacy_tracking_binding.since_utc_date, "2026-09-06")
        self.assertEqual(previous.legacy_tracking_binding.since_utc_date, "2026-09-05")
        for since in ("2026-09-07", "2026-09-04", "2026-02-30", "2026-9-6",
                      "2026-09-06T00:00:00Z", 20260906):
            with self.subTest(since=since):
                with self.assertRaises(TrustConfigMapsError):
                    validate(objects(since=since))  # type: ignore[arg-type]

    def test_binding_and_proof_constructors_revalidate_forged_objects(self) -> None:
        proof = validate()
        root = proof.root_ca_bindings[0]
        extension = proof.extension_auth_binding
        legacy = proof.legacy_tracking_binding
        with self.assertRaises(TrustConfigMapsError):
            RootCABinding("v2", root.kind, root.namespace, root.name, root.uid,
                          root.resource_version, root.cluster_certificate_der_sha256)
        with self.assertRaises(TrustConfigMapsError):
            ExtensionAuthBinding(
                extension.api_version, extension.kind, extension.namespace, extension.name,
                extension.uid, extension.resource_version,
                extension.cluster_client_certificate_der_sha256,
                extension.cluster_client_certificate_der_sha256,
            )
        with self.assertRaises(TrustConfigMapsError):
            LegacyTrackingBinding(
                legacy.api_version, legacy.kind, legacy.namespace, legacy.name,
                legacy.uid, legacy.resource_version, "2026-09-04", legacy.creation_timestamp,
            )
        forged = object.__new__(RootCABinding)
        for field in fields(RootCABinding):
            object.__setattr__(forged, field.name, getattr(root, field.name))
        object.__setattr__(forged, "cluster_certificate_der_sha256", "0" * 64)
        forged_roots = tuple(sorted((forged,) + proof.root_ca_bindings[1:]))
        with self.assertRaises(TrustConfigMapsError):
            TrustConfigMapsProof(forged_roots, extension, legacy)
        with self.assertRaises(TrustConfigMapsError):
            TrustConfigMapsProof(proof.root_ca_bindings, extension, legacy, True)
        forged_extension = object.__new__(ExtensionAuthBinding)
        for field in fields(ExtensionAuthBinding):
            object.__setattr__(forged_extension, field.name, getattr(extension, field.name))
        object.__setattr__(forged_extension, "cluster_client_certificate_der_sha256", "0" * 64)
        with self.assertRaises(TrustConfigMapsError):
            TrustConfigMapsProof(proof.root_ca_bindings, forged_extension, legacy)

    def test_proof_normalizes_partially_initialized_nested_bindings(self) -> None:
        proof = validate()
        partial_root = object.__new__(RootCABinding)
        partial_extension = object.__new__(ExtensionAuthBinding)
        partial_legacy = object.__new__(LegacyTrackingBinding)
        cases = (
            ((partial_root,) + proof.root_ca_bindings[1:],
             proof.extension_auth_binding, proof.legacy_tracking_binding),
            (proof.root_ca_bindings, partial_extension, proof.legacy_tracking_binding),
            (proof.root_ca_bindings, proof.extension_auth_binding, partial_legacy),
        )
        for roots, extension, legacy in cases:
            with self.subTest(binding=type(extension).__name__, legacy=type(legacy).__name__):
                with self.assertRaises(TrustConfigMapsError):
                    TrustConfigMapsProof(roots, extension, legacy)

    def test_constructor_fields_reject_wrong_exact_types_uids_rvs_hashes_and_sets(self) -> None:
        proof = validate()
        root = proof.root_ca_bindings[0]
        valid = [getattr(root, field.name) for field in fields(root)]
        cases = (
            (0, StringSubclass("v1")), (2, StringSubclass(root.namespace)),
            (4, "bad uid"), (5, "01"), (6, "A" * 64), (6, "0" * 63),
        )
        for index, invalid in cases:
            args = valid.copy()
            args[index] = invalid
            with self.subTest(index=index, invalid=invalid):
                with self.assertRaises(TrustConfigMapsError):
                    RootCABinding(*args)
        with self.assertRaises(TrustConfigMapsError):
            TrustConfigMapsProof(tuple(reversed(proof.root_ca_bindings)),
                                 proof.extension_auth_binding, proof.legacy_tracking_binding)
        with self.assertRaises(TrustConfigMapsError):
            TrustConfigMapsProof(proof.root_ca_bindings[:-1],
                                 proof.extension_auth_binding, proof.legacy_tracking_binding)


if __name__ == "__main__":
    unittest.main()
