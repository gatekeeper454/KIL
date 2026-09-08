"""Independent fixtures for the two source-rendered platform ConfigMaps."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
from hashlib import sha256
import json
import unittest

from kil.v3b2_source_rendered_configmaps import (
    SourceRenderedConfigMapBinding,
    SourceRenderedConfigMapError,
    SourceRenderedConfigMapsProof,
    validate_source_rendered_configmaps,
)


COREFILE = ".:53 {\n    errors\n    health {\n       lameduck 5s\n    }\n    ready\n    kubernetes cluster.local in-addr.arpa ip6.arpa {\n       pods insecure\n       fallthrough in-addr.arpa ip6.arpa\n       ttl 30\n    }\n    prometheus :9153\n    forward . /etc/resolv.conf {\n       max_concurrent 1000\n    }\n    cache 30 {\n       disable success cluster.local\n       disable denial cluster.local\n    }\n    loop\n    reload\n    loadbalance\n}\n"
CONFIG = "{\n        \"nodePathMap\":[\n        {\n                \"node\":\"DEFAULT_PATH_FOR_NON_LISTED_NODES\",\n                \"paths\":[\"/var/local-path-provisioner\"]\n        }\n        ]\n}"
SETUP = "#!/bin/sh\nset -eu\nmkdir -m 0777 -p \"$VOL_DIR\""
TEARDOWN = "#!/bin/sh\nset -eu\nrm -rf \"$VOL_DIR\""
HELPER = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: helper-pod\nspec:\n  priorityClassName: system-node-critical\n  tolerations:\n    - key: node.kubernetes.io/disk-pressure\n      operator: Exists\n      effect: NoSchedule\n  containers:\n  - name: helper-pod\n    image: docker.io/kindest/local-path-helper:v20260131-7181c60a\n    imagePullPolicy: IfNotPresent"
LOCAL_DATA = {"config.json": CONFIG, "setup": SETUP, "teardown": TEARDOWN,
              "helperPod.yaml": HELPER}
LAST_APPLIED = "kubectl.kubernetes.io/last-applied-configuration"


class StringSubclass(str):
    pass


class MutableEqualityImpostor:
    def __init__(self, value: str) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return self.value == other

    def __ne__(self, other: object) -> bool:
        return self.value != other


class ExplodingEquality:
    def __eq__(self, other: object) -> bool:
        raise RuntimeError("untrusted equality executed")

    def __ne__(self, other: object) -> bool:
        raise RuntimeError("untrusted equality executed")


def source_digest(namespace: str, name: str, data: dict[str, str]) -> str:
    # Independent oracle: the test does not import production canonicalization.
    projected = {"apiVersion": "v1", "kind": "ConfigMap",
                 "metadata": {"name": name, "namespace": namespace}, "data": data}
    encoded = json.dumps(projected, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def applied(*, empty_annotations: bool = False) -> str:
    metadata: dict[str, object] = {
        "name": "local-path-config", "namespace": "local-path-storage"
    }
    if empty_annotations:
        metadata["annotations"] = {}
    return json.dumps({"kind": "ConfigMap", "data": LOCAL_DATA,
                       "metadata": metadata, "apiVersion": "v1"},
                      separators=(", ", ": "))


def metadata(namespace: str, name: str, serial: int) -> dict:
    return {
        "name": name,
        "namespace": namespace,
        "uid": f"uid-{serial}",
        "resourceVersion": str(serial),
        "creationTimestamp": "2026-09-06T01:02:03.123456789Z",
        "managedFields": [{
            "manager": "kubectl-client-side-apply",
            "operation": "Update",
            "apiVersion": "v1",
            "fieldsType": "FieldsV1",
            "fieldsV1": {"f:data": {}},
            "time": "2026-09-06T01:02:03Z",
        }],
    }


def objects() -> list[dict]:
    core = {"apiVersion": "v1", "kind": "ConfigMap",
            "metadata": metadata("kube-system", "coredns", 41),
            "data": {"Corefile": COREFILE}}
    local_metadata = metadata("local-path-storage", "local-path-config", 42)
    local_metadata["annotations"] = {LAST_APPLIED: applied()}
    local = {"apiVersion": "v1", "kind": "ConfigMap",
             "metadata": local_metadata, "data": deepcopy(LOCAL_DATA)}
    return [local, core]


def payload(items: list[dict] | None = None, **root_changes: object) -> bytes:
    root: dict[str, object] = {
        "apiVersion": "v1", "kind": "List",
        "items": objects() if items is None else items,
    }
    root.update(root_changes)
    return json.dumps(root, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def validate(items: list[dict] | None = None) -> SourceRenderedConfigMapsProof:
    return validate_source_rendered_configmaps(payload(items))


class SourceRenderedConfigMapsTest(unittest.TestCase):
    def test_exact_success_is_frozen_sorted_deterministic_and_non_ready(self) -> None:
        self.assertEqual((len(COREFILE.encode()), sha256(COREFILE.encode()).hexdigest()),
                         (420, "22847ad9af7452500838865a67e018076226d8fbfcabf54f8673973571f470f6"))
        for value, length, digest in (
            (CONFIG, 173, "00112e23d095775fb664cbd04ca45734a237bbdd3fe8445c6b04857c702f0381"),
            (SETUP, 45, "b79c9a0bc2128407670551dc4086f4761bece38ca2aee95c23d307ac83ba99da"),
            (TEARDOWN, 35, "b4567ea114784d0ab18a26d0057a0dc3e6945dc15ced1f40f6241e10f94b4d16"),
            (HELPER, 343, "eb44d89e8e474527ec44571f5a2ba0c7bda81e13201124d225d2e9c5727c53be"),
        ):
            self.assertEqual((len(value.encode()), sha256(value.encode()).hexdigest()),
                             (length, digest))
        raw = payload()
        proof = validate_source_rendered_configmaps(raw)
        self.assertIsInstance(proof, SourceRenderedConfigMapsProof)
        self.assertEqual(proof, validate_source_rendered_configmaps(raw))
        self.assertEqual(proof.bindings, tuple(sorted(proof.bindings)))
        self.assertEqual([(row.api_version, row.kind, row.namespace, row.name,
                           row.uid, row.resource_version,
                           row.source_configuration_sha256) for row in proof.bindings], [
            ("v1", "ConfigMap", "kube-system", "coredns", "uid-41", "41",
             source_digest("kube-system", "coredns", {"Corefile": COREFILE})),
            ("v1", "ConfigMap", "local-path-storage", "local-path-config", "uid-42", "42",
             source_digest("local-path-storage", "local-path-config", LOCAL_DATA)),
        ])
        self.assertEqual(tuple(field.name for field in fields(proof.bindings[0])),
                         ("api_version", "kind", "namespace", "name", "uid",
                          "resource_version", "source_configuration_sha256"))
        self.assertIs(proof.runtime_contract_complete, False)
        self.assertEqual(tuple(field.name for field in fields(proof)),
                         ("bindings", "runtime_contract_complete"))
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            proof.bindings = ()  # type: ignore[misc]

    def test_input_is_not_mutated_or_aliased(self) -> None:
        items = objects()
        before = deepcopy(items)
        first = validate(items)
        self.assertEqual(items, before)
        items[0]["metadata"]["uid"] = "mutated-after-validation"
        self.assertEqual(first.bindings[1].uid, "uid-42")

    def test_bindings_and_proof_reject_forged_source_configuration_digests(self) -> None:
        proof = validate()
        for valid in proof.bindings:
            forged_digest = "0" * 64 if valid.source_configuration_sha256 != "0" * 64 else "1" * 64
            arguments = (
                valid.api_version, valid.kind, valid.namespace, valid.name,
                valid.uid, valid.resource_version, forged_digest,
            )
            with self.subTest(boundary="binding", identity=(valid.namespace, valid.name)):
                with self.assertRaises(SourceRenderedConfigMapError):
                    SourceRenderedConfigMapBinding(*arguments)

            forged = object.__new__(SourceRenderedConfigMapBinding)
            for field, value in zip(fields(SourceRenderedConfigMapBinding), arguments):
                object.__setattr__(forged, field.name, value)
            other = next(row for row in proof.bindings if row is not valid)
            forged_bindings = tuple(sorted((forged, other)))
            with self.subTest(boundary="proof", identity=(valid.namespace, valid.name)):
                with self.assertRaises(SourceRenderedConfigMapError):
                    SourceRenderedConfigMapsProof(forged_bindings)

    def test_binding_api_identity_requires_immutable_exact_builtin_strings(self) -> None:
        proof = validate()
        core = proof.bindings[0]
        valid = [
            core.api_version, core.kind, core.namespace, core.name, core.uid,
            core.resource_version, core.source_configuration_sha256,
        ]
        for index, expected in ((0, "v1"), (1, "ConfigMap")):
            for invalid in (StringSubclass(expected), MutableEqualityImpostor(expected),
                            ExplodingEquality()):
                arguments = valid.copy()
                arguments[index] = invalid  # type: ignore[assignment]
                with self.subTest(boundary="constructor", field=index, invalid=type(invalid).__name__):
                    with self.assertRaises(SourceRenderedConfigMapError):
                        SourceRenderedConfigMapBinding(*arguments)  # type: ignore[arg-type]

                forged = object.__new__(SourceRenderedConfigMapBinding)
                for field, value in zip(fields(SourceRenderedConfigMapBinding), arguments):
                    object.__setattr__(forged, field.name, value)
                with self.subTest(boundary="proof", field=index, invalid=type(invalid).__name__):
                    with self.assertRaises(SourceRenderedConfigMapError):
                        SourceRenderedConfigMapsProof((forged, proof.bindings[1]))

                if isinstance(invalid, MutableEqualityImpostor):
                    invalid.value = "mutated-after-rejection"

        self.assertIs(type(core.api_version), str)
        self.assertIs(type(core.kind), str)
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            core.api_version = "v2"  # type: ignore[misc]
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            core.kind = "Secret"  # type: ignore[misc]

    def test_missing_extra_duplicate_and_wrong_identity_are_rejected(self) -> None:
        exact = objects()
        cases = [exact[:1], exact[1:], [], exact + [deepcopy(exact[0])],
                 [deepcopy(exact[0]), deepcopy(exact[0])],
                 [deepcopy(exact[1]), deepcopy(exact[1])]]
        for index in range(2):
            changed = deepcopy(exact)
            changed[index]["metadata"]["name"] += "-foreign"
            cases.append(changed)
            changed = deepcopy(exact)
            changed[index]["metadata"]["namespace"] += "-foreign"
            cases.append(changed)
        extra = deepcopy(exact[0])
        extra["metadata"].update(name="foreign", uid="uid-99", resourceVersion="99")
        cases.append(exact + [extra])
        for case in cases:
            with self.subTest(items=len(case)):
                with self.assertRaises(SourceRenderedConfigMapError):
                    validate(case)

    def test_root_item_metadata_and_data_are_closed_and_required(self) -> None:
        for root_key in ("apiVersion", "kind", "items"):
            root = json.loads(payload())
            del root[root_key]
            with self.subTest(scope="list", operation="missing", key=root_key):
                with self.assertRaises(SourceRenderedConfigMapError):
                    validate_source_rendered_configmaps(json.dumps(root).encode())
        for key, value in (("apiVersion", "v2"), ("kind", "ConfigMap"), ("items", {}),
                           ("metadata", {})):
            with self.subTest(scope="list", operation="extra-or-change", key=key):
                with self.assertRaises(SourceRenderedConfigMapError):
                    validate_source_rendered_configmaps(payload(**{key: value}))
        for item_index in range(2):
            for key in ("apiVersion", "kind", "metadata", "data"):
                changed = objects()
                del changed[item_index][key]
                with self.subTest(scope="item", index=item_index, operation="missing", key=key):
                    with self.assertRaises(SourceRenderedConfigMapError):
                        validate(changed)
            for key, value in (("binaryData", {}), ("immutable", False), ("status", {}), ("extra", None)):
                changed = objects()
                changed[item_index][key] = value
                with self.subTest(scope="item", index=item_index, operation="extra", key=key):
                    with self.assertRaises(SourceRenderedConfigMapError):
                        validate(changed)
            for key in tuple(objects()[item_index]["metadata"]):
                changed = objects()
                del changed[item_index]["metadata"][key]
                with self.subTest(scope="metadata", index=item_index, operation="missing", key=key):
                    with self.assertRaises(SourceRenderedConfigMapError):
                        validate(changed)
            for key, value in (("labels", {}), ("ownerReferences", []), ("finalizers", []),
                               ("deletionTimestamp", None), ("deletionGracePeriodSeconds", 0),
                               ("generation", 1), ("foreign", "value")):
                changed = objects()
                changed[item_index]["metadata"][key] = value
                with self.subTest(scope="metadata", index=item_index, operation="extra", key=key):
                    with self.assertRaises(SourceRenderedConfigMapError):
                        validate(changed)
            data = objects()[item_index]["data"]
            for key in data:
                changed = objects()
                del changed[item_index]["data"][key]
                with self.subTest(scope="data", index=item_index, operation="missing", key=key):
                    with self.assertRaises(SourceRenderedConfigMapError):
                        validate(changed)
            changed = objects()
            changed[item_index]["data"]["foreign"] = "value"
            with self.subTest(scope="data", index=item_index, operation="extra"):
                with self.assertRaises(SourceRenderedConfigMapError):
                    validate(changed)

    def test_api_kind_uid_resource_version_and_runtime_metadata_are_exact(self) -> None:
        mutations = (
            ("root", "apiVersion", "apps/v1"), ("root", "kind", "Secret"),
            ("metadata", "uid", ""), ("metadata", "uid", "x" * 129),
            ("metadata", "uid", "not allowed"), ("metadata", "uid", 1),
            ("metadata", "resourceVersion", "0"), ("metadata", "resourceVersion", "01"),
            ("metadata", "resourceVersion", "18446744073709551616"),
            ("metadata", "resourceVersion", 1),
            ("metadata", "creationTimestamp", "not-a-time"),
            ("metadata", "creationTimestamp", None),
            ("metadata", "managedFields", {}),
            ("metadata", "managedFields", [{"manager": "x"}]),
        )
        for item_index in range(2):
            for scope, key, value in mutations:
                changed = objects()
                target = changed[item_index] if scope == "root" else changed[item_index]["metadata"]
                target[key] = value
                with self.subTest(index=item_index, key=key, value=value):
                    with self.assertRaises(SourceRenderedConfigMapError):
                        validate(changed)

    def test_annotations_are_exact_per_identity(self) -> None:
        core, local = objects()[1], objects()[0]
        core["metadata"]["annotations"] = {}
        with self.assertRaises(SourceRenderedConfigMapError):
            validate([core, local])
        for annotations in ({}, {LAST_APPLIED: applied(), "foreign": "x"},
                            {"foreign": applied()}, {LAST_APPLIED: 1}):
            changed = objects()
            changed[0]["metadata"]["annotations"] = annotations
            with self.subTest(annotations=annotations):
                with self.assertRaises(SourceRenderedConfigMapError):
                    validate(changed)

    def test_every_source_value_rejects_content_whitespace_and_final_lf_drift(self) -> None:
        for item_index, key in ((1, "Corefile"), (0, "config.json"), (0, "setup"),
                                (0, "teardown"), (0, "helperPod.yaml")):
            for mutation in (lambda value: value + "x", lambda value: " " + value,
                             lambda value: value + "\n", lambda value: value[:-1]):
                changed = objects()
                changed[item_index]["data"][key] = mutation(changed[item_index]["data"][key])
                with self.subTest(index=item_index, key=key, mutation=mutation):
                    with self.assertRaises(SourceRenderedConfigMapError):
                        validate(changed)
        changed = objects()
        changed[0]["data"]["setup-renamed"] = changed[0]["data"].pop("setup")
        with self.assertRaises(SourceRenderedConfigMapError):
            validate(changed)

    def test_last_applied_semantic_reordering_and_optional_empty_annotations_are_accepted(self) -> None:
        variants = [applied(), applied(empty_annotations=True), json.dumps({
            "data": dict(reversed(list(LOCAL_DATA.items()))), "metadata": {
                "namespace": "local-path-storage", "name": "local-path-config"
            }, "kind": "ConfigMap", "apiVersion": "v1"
        }, indent=4)]
        proofs = []
        for annotation in variants:
            changed = objects()
            changed[0]["metadata"]["annotations"][LAST_APPLIED] = annotation
            proofs.append(validate(changed))
        self.assertEqual(proofs, [proofs[0]] * len(proofs))

    def test_last_applied_shape_identity_server_fields_and_content_are_closed(self) -> None:
        base = json.loads(applied())
        variants = []
        for key in ("apiVersion", "kind", "metadata", "data"):
            changed = deepcopy(base)
            del changed[key]
            variants.append(changed)
        for key, value in (("extra", {}), ("binaryData", {}), ("status", {})):
            changed = deepcopy(base)
            changed[key] = value
            variants.append(changed)
        for key, value in (("name", "foreign"), ("namespace", "foreign"),
                           ("uid", "uid-42"), ("resourceVersion", "42"),
                           ("creationTimestamp", "2026-09-06T01:02:03Z"),
                           ("managedFields", []), ("labels", {}), ("foreign", "x")):
            changed = deepcopy(base)
            changed["metadata"][key] = value
            variants.append(changed)
        for key in LOCAL_DATA:
            changed = deepcopy(base)
            changed["data"][key] += "x"
            variants.append(changed)
        changed = deepcopy(base)
        changed["metadata"]["annotations"] = {LAST_APPLIED: applied()}
        variants.append(changed)
        changed = deepcopy(base)
        changed["metadata"]["annotations"] = {"foreign": "x"}
        variants.append(changed)
        for value in variants:
            observed = objects()
            observed[0]["metadata"]["annotations"][LAST_APPLIED] = json.dumps(value)
            with self.subTest(keys=value.keys()):
                with self.assertRaises(SourceRenderedConfigMapError):
                    validate(observed)

    def test_duplicate_json_keys_are_rejected_at_outer_and_annotation_depth(self) -> None:
        raw = payload()
        duplicate_outer = raw[:-1] + b',"kind":"List"}'
        with self.assertRaises(SourceRenderedConfigMapError):
            validate_source_rendered_configmaps(duplicate_outer)
        changed = objects()
        changed[0]["metadata"]["annotations"][LAST_APPLIED] = (
            '{"apiVersion":"v1","apiVersion":"v1","kind":"ConfigMap",'
            '"metadata":{"name":"local-path-config","namespace":"local-path-storage"},'
            '"data":' + json.dumps(LOCAL_DATA) + '}'
        )
        with self.assertRaises(SourceRenderedConfigMapError):
            validate(changed)

    def test_lone_surrogates_are_rejected_in_keys_values_and_annotation(self) -> None:
        raw_cases = (
            b'{"apiVersion":"v1","kind":"List","items":[],"\\ud800":"x"}',
            b'{"apiVersion":"v1","kind":"List","items":["\\ud800"]}',
        )
        for raw in raw_cases:
            with self.assertRaises(SourceRenderedConfigMapError):
                validate_source_rendered_configmaps(raw)
        changed = objects()
        changed[0]["metadata"]["annotations"][LAST_APPLIED] = '"\\ud800"'
        with self.assertRaises(SourceRenderedConfigMapError):
            validate(changed)

    def test_bytes_utf8_payload_size_depth_items_integers_and_nonfinite_are_bounded(self) -> None:
        cases: tuple[object, ...] = (
            "not bytes", bytearray(payload()), b"\xff", b"NaN", b"Infinity",
            b'{"apiVersion":"v1","kind":"List","items":[],"number":' + b"9" * 129 + b"}",
            b"[" * 70 + b"0" + b"]" * 70,
            b'{"apiVersion":"v1","kind":"List","items":[' + b"null," * 40000 + b"null]}",
            b" " * (1024 * 1024 + 1),
        )
        for value in cases:
            with self.subTest(type=type(value), length=len(value)):
                with self.assertRaises(SourceRenderedConfigMapError):
                    validate_source_rendered_configmaps(value)  # type: ignore[arg-type]

    def test_all_parser_and_validation_failures_use_domain_error(self) -> None:
        cases = (b"", b"null", b"[]", b"{}", b"1", b'"value"', payload([]))
        for raw in cases:
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(SourceRenderedConfigMapError) as raised:
                    validate_source_rendered_configmaps(raw)
                self.assertIsInstance(raised.exception, ValueError)


if __name__ == "__main__":
    unittest.main()
