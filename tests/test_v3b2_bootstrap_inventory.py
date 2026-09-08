from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
from hashlib import sha256
import json
from pathlib import Path
import unittest

from kil.v3b2_bootstrap_inventory import (
    BootstrapIdentityBinding,
    BootstrapIdentitySnapshot,
    BootstrapInventoryError,
    validate_bootstrap_identities,
)
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_inventory import InventoryAttestation, InventorySnapshot
from kil.v3b2_manifests import WorkloadIdentity, render_objects
from kil.v3b2_proofs import calico_objects


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "v3b2-" + "1" * 64
WORKLOAD = WorkloadIdentity(
    RUN_ID,
    "sha256:" + "2" * 64,
    "docker.io/envoyproxy/envoy@sha256:" + "3" * 64,
)
NAMESPACES = (
    "default", "kil-v3-baseline", "kil-v3-local-reduce", "kil-v3-signed",
    "kube-node-lease", "kube-public", "kube-system", "local-path-storage",
)
CONTROLLER_ACCOUNTS = (
    "attachdetach-controller", "bootstrap-signer", "certificate-controller",
    "clusterrole-aggregation-controller", "cronjob-controller",
    "daemon-set-controller", "deployment-controller",
    "device-taint-eviction-controller", "disruption-controller",
    "endpoint-controller", "endpointslice-controller",
    "endpointslicemirroring-controller", "ephemeral-volume-controller",
    "expand-controller", "generic-garbage-collector",
    "horizontal-pod-autoscaler", "job-controller",
    "legacy-service-account-token-cleaner", "namespace-controller",
    "node-controller", "persistent-volume-binder", "pod-garbage-collector",
    "pv-protection-controller", "pvc-protection-controller",
    "replicaset-controller", "replication-controller",
    "resource-claim-controller", "resourcequota-controller",
    "root-ca-cert-publisher", "service-account-controller",
    "service-cidrs-controller", "statefulset-controller", "token-cleaner",
    "ttl-after-finished-controller", "ttl-controller",
    "validatingadmissionpolicy-status-controller",
    "volumeattributesclass-protection-controller",
)
PLATFORM_SERVICE_ACCOUNTS = tuple(sorted(
    [(namespace, "default") for namespace in NAMESPACES]
    + [("kube-system", name) for name in CONTROLLER_ACCOUNTS]
    + [
        ("kube-system", "coredns"),
        ("kube-system", "kube-proxy"),
        ("local-path-storage", "local-path-provisioner-service-account"),
    ]
))
CALICO_SERVICE_ACCOUNTS = tuple(
    ("kube-system", name)
    for name in ("calico-node", "calico-cni-plugin", "calico-kube-controllers")
)
KIL_SERVICE_ACCOUNTS = tuple(
    (namespace, name)
    for namespace in ("kil-v3-baseline", "kil-v3-signed", "kil-v3-local-reduce")
    for name in ("driver", "envoy", "authz", "target")
)
PLATFORM_CONFIG_MAPS = tuple(sorted(
    [(namespace, "kube-root-ca.crt") for namespace in NAMESPACES]
    + [
        ("kube-system", "coredns"),
        ("kube-system", "extension-apiserver-authentication"),
        ("kube-system", "kube-apiserver-legacy-service-account-token-tracking"),
        ("kube-system", "kube-proxy"),
        ("kube-system", "kubeadm-config"),
        ("kube-system", "kubelet-config"),
        ("kube-public", "cluster-info"),
        ("local-path-storage", "local-path-config"),
    ]
))
CALICO_CONFIG_MAPS = (("kube-system", "calico-config"),)
KIL_CONFIG_MAPS = tuple(
    (namespace, name)
    for namespace in ("kil-v3-baseline", "kil-v3-signed", "kil-v3-local-reduce")
    for name in ("authz-config", "target-config", "envoy-config")
)


def profile() -> V3B2Profile:
    return V3B2Profile.load(ROOT / "deploy/kind/v3b2-profile.json")


def expected_source_objects() -> dict[tuple[str, str, str], dict]:
    application = json.loads(render_objects(profile(), WORKLOAD))["items"]
    calico = calico_objects(
        (ROOT / "deploy/kind/calico-v3.32.0.yaml").read_bytes(),
        (ROOT / "deploy/kind/calico-v3.32.0.objects.json").read_bytes(),
    )
    return {
        (
            item["kind"],
            item["metadata"].get("namespace", ""),
            item["metadata"]["name"],
        ): item
        for item in (*application, *calico)
        if item["kind"] in {"Namespace", "ServiceAccount", "ConfigMap"}
    }


def runtime_metadata(document: dict, uid: str, resource_version: str) -> dict:
    value = deepcopy(document)
    metadata = value["metadata"]
    metadata.update({
        "uid": uid,
        "resourceVersion": resource_version,
        "creationTimestamp": "2026-09-06T01:02:03Z",
        "managedFields": [],
    })
    if value["kind"] == "Namespace":
        metadata.setdefault("labels", {})["kubernetes.io/metadata.name"] = metadata["name"]
        value.setdefault("spec", {}).setdefault("finalizers", ["kubernetes"])
        value["status"] = {"phase": "Active"}
    return value


def bootstrap_items() -> list[dict]:
    source = expected_source_objects()
    items: list[dict] = []
    serial = 1

    for namespace in NAMESPACES:
        key = ("Namespace", "", namespace)
        desired = source.get(key, {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": namespace,
                "labels": {"kubernetes.io/metadata.name": namespace},
            },
            "spec": {"finalizers": ["kubernetes"]},
        })
        items.append(runtime_metadata(desired, f"uid-{serial:03d}", str(serial)))
        serial += 1

    for namespace, name in PLATFORM_SERVICE_ACCOUNTS:
        desired = {
            "apiVersion": "v1", "kind": "ServiceAccount",
            "metadata": {"namespace": namespace, "name": name},
        }
        items.append(runtime_metadata(desired, f"uid-{serial:03d}", str(serial)))
        serial += 1
    for namespace, name in (*CALICO_SERVICE_ACCOUNTS, *KIL_SERVICE_ACCOUNTS):
        desired = source[("ServiceAccount", namespace, name)]
        items.append(runtime_metadata(desired, f"uid-{serial:03d}", str(serial)))
        serial += 1

    for namespace, name in PLATFORM_CONFIG_MAPS:
        metadata: dict[str, object] = {"namespace": namespace, "name": name}
        if name == "kube-root-ca.crt":
            metadata["annotations"] = {
                "kubernetes.io/description": (
                    "Contains a CA bundle that can be used to verify the kube-apiserver "
                    "when using internal endpoints such as the internal service IP or "
                    "kubernetes.default.svc. No other usage is guaranteed across distributions."
                )
            }
        desired = {
            "apiVersion": "v1", "kind": "ConfigMap", "metadata": metadata,
            "data": {"fixture": f"configuration for {namespace}/{name}"},
        }
        items.append(runtime_metadata(desired, f"uid-{serial:03d}", str(serial)))
        serial += 1
    for namespace, name in (*CALICO_CONFIG_MAPS, *KIL_CONFIG_MAPS):
        desired = source[("ConfigMap", namespace, name)]
        items.append(runtime_metadata(desired, f"uid-{serial:03d}", str(serial)))
        serial += 1
    return items


def payload(items: list[dict] | None = None) -> bytes:
    selected = bootstrap_items() if items is None else items
    return json.dumps({"apiVersion": "v1", "kind": "List", "items": selected}).encode()


def validate(items: list[dict] | None = None, **changes) -> BootstrapIdentitySnapshot:
    arguments = {
        "profile": profile(),
        "workload": WORKLOAD,
        "cluster_incarnation_uid": "uid-007",
        "prior": None,
    }
    arguments.update(changes)
    return validate_bootstrap_identities(payload(items), **arguments)


def relevant_key(item: dict) -> tuple[str, str, str]:
    return (
        item["kind"], item["metadata"].get("namespace", ""),
        item["metadata"]["name"],
    )


class BootstrapInventoryTest(unittest.TestCase):
    def test_exact_97_object_identity_snapshot_is_frozen_and_sorted(self) -> None:
        items = bootstrap_items()
        original = deepcopy(items)
        snapshot = validate(items)
        self.assertEqual((len(snapshot.namespace_bindings), len(snapshot.service_account_bindings),
                          len(snapshot.config_map_bindings)), (8, 63, 26))
        self.assertEqual(len(PLATFORM_SERVICE_ACCOUNTS), 48)
        self.assertEqual(len(PLATFORM_CONFIG_MAPS), 16)
        self.assertEqual(len(snapshot.unvalidated_platform_configurations), 16)
        self.assertEqual(items, original)
        self.assertFalse(isinstance(snapshot, InventorySnapshot))
        self.assertFalse(isinstance(snapshot, InventoryAttestation))
        for records in (snapshot.namespace_bindings, snapshot.service_account_bindings,
                        snapshot.config_map_bindings, snapshot.unvalidated_platform_configurations):
            self.assertEqual(records, tuple(sorted(records)))
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            snapshot.namespace_bindings = ()  # type: ignore[misc]
        self.assertEqual(
            tuple(field.name for field in fields(snapshot)),
            ("namespace_bindings", "service_account_bindings", "config_map_bindings",
             "unvalidated_platform_configurations"),
        )

    def test_every_missing_extra_and_duplicate_identity_fails_closed(self) -> None:
        complete = bootstrap_items()
        relevant = [item for item in complete if item["kind"] in {"Namespace", "ServiceAccount", "ConfigMap"}]
        for index, item in enumerate(relevant):
            with self.subTest(case="missing", key=relevant_key(item)):
                with self.assertRaises(BootstrapInventoryError):
                    validate(complete[:index] + complete[index + 1:])
            duplicate = deepcopy(complete)
            duplicate.append(deepcopy(item))
            with self.subTest(case="duplicate", key=relevant_key(item)):
                with self.assertRaises(BootstrapInventoryError):
                    validate(duplicate)
        extras = (
            ("Namespace", "", "foreign"),
            ("ServiceAccount", "kube-system", "tokens-controller"),
            ("ConfigMap", "kube-system", "foreign"),
        )
        for kind, namespace, name in extras:
            extra = runtime_metadata({
                "apiVersion": "v1", "kind": kind,
                "metadata": {"name": name, **({"namespace": namespace} if namespace else {})},
                **({"spec": {"finalizers": ["kubernetes"]}} if kind == "Namespace" else {}),
            }, f"uid-extra-{kind}", "999")
            if kind == "Namespace":
                extra["metadata"]["labels"] = {"kubernetes.io/metadata.name": name}
            with self.subTest(case="extra", key=(kind, namespace, name)):
                with self.assertRaises(BootstrapInventoryError):
                    validate([*complete, extra])

    def test_prior_bindings_preserve_uids_allow_rv_advance_and_ignore_platform_content(self) -> None:
        first_items = bootstrap_items()
        platform = next(item for item in first_items if relevant_key(item) ==
                        ("ConfigMap", "kube-system", "coredns"))
        platform["data"] = {"z": "last", "a": "first"}
        prior = validate(first_items)

        def digest(snapshot: BootstrapIdentitySnapshot) -> str:
            matches = [
                row.unvalidated_configuration_sha256
                for row in snapshot.unvalidated_platform_configurations
                if (row.namespace, row.name) == ("kube-system", "coredns")
            ]
            self.assertEqual(len(matches), 1)
            return matches[0]

        expected_document = deepcopy(platform)
        for field in ("uid", "resourceVersion", "creationTimestamp", "managedFields"):
            expected_document["metadata"].pop(field)
        expected_digest = sha256(json.dumps(
            expected_document, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        self.assertEqual(digest(prior), expected_digest)

        metadata_only = deepcopy(first_items)
        metadata_target = next(item for item in metadata_only if relevant_key(item) ==
                               ("ConfigMap", "kube-system", "coredns"))
        metadata_target["metadata"].update({
            "uid": "uid-metadata-only", "resourceVersion": "9999",
            "creationTimestamp": "2026-09-07T01:02:03Z",
            "managedFields": [{
                "manager": "kube-controller-manager", "operation": "Update",
                "apiVersion": "v1", "fieldsType": "FieldsV1",
                "fieldsV1": {"f:data": {}},
            }],
        })
        self.assertEqual(digest(validate(metadata_only)), digest(prior))

        reordered = deepcopy(first_items)
        reordered_target = next(item for item in reordered if relevant_key(item) ==
                                ("ConfigMap", "kube-system", "coredns"))
        reordered_target["data"] = {"a": "first", "z": "last"}
        reordered_target["metadata"] = dict(reversed(tuple(reordered_target["metadata"].items())))
        self.assertEqual(digest(validate(reordered)), digest(prior))

        content_changed = deepcopy(first_items)
        content_target = next(item for item in content_changed if relevant_key(item) ==
                              ("ConfigMap", "kube-system", "coredns"))
        content_target["data"]["z"] = "changed"
        self.assertNotEqual(digest(validate(content_changed)), digest(prior))

        advanced = deepcopy(first_items)
        for item in advanced:
            item["metadata"]["resourceVersion"] = str(int(item["metadata"]["resourceVersion"]) + 1000)
        advanced_platform = next(item for item in advanced if relevant_key(item) ==
                                 ("ConfigMap", "kube-system", "coredns"))
        advanced_platform["data"] = {"Corefile": "changed but still unvalidated"}
        current = validate(advanced, prior=prior)
        self.assertNotEqual(digest(prior), digest(current))
        self.assertEqual([row.uid for row in prior.config_map_bindings],
                         [row.uid for row in current.config_map_bindings])
        replaced = deepcopy(advanced)
        replaced[0]["metadata"]["uid"] = "replacement-uid"
        with self.assertRaises(BootstrapInventoryError):
            validate(replaced, prior=prior)
        regressed = deepcopy(advanced)
        regressed[1]["metadata"]["resourceVersion"] = "1"
        with self.assertRaises(BootstrapInventoryError):
            validate(regressed, prior=prior)

    def test_namespace_scope_state_metadata_and_configuration_are_exact(self) -> None:
        explicit_empty = bootstrap_items()
        explicit_empty[0]["metadata"]["namespace"] = ""
        validate(explicit_empty)
        mutations = (
            (("status", "phase"), "Terminating"),
            (("status", "extra"), True),
            (("metadata", "deletionTimestamp"), "2026-09-06T01:02:03Z"),
            (("metadata", "deletionGracePeriodSeconds"), 30),
            (("metadata", "namespace"), "default"),
            (("metadata", "labels", "kubernetes.io/metadata.name"), "wrong"),
            (("metadata", "labels", "foreign"), "label"),
            (("metadata", "annotations"), {"foreign": "annotation"}),
            (("spec", "finalizers"), []),
            (("spec", "foreign"), True),
        )
        for path, value in mutations:
            items = bootstrap_items()
            target = items[0]
            cursor = target
            for part in path[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor[path[-1]] = value
            with self.subTest(path=path, value=value):
                with self.assertRaises(BootstrapInventoryError):
                    validate(items)

    def test_uid_resource_version_and_global_incarnation_are_exact(self) -> None:
        for field, invalid in (
            ("uid", ""), ("uid", "bad uid"), ("uid", 1), ("uid", True),
            ("resourceVersion", "0"), ("resourceVersion", "01"),
            ("resourceVersion", str(2**64)), ("resourceVersion", 1),
            ("resourceVersion", True),
        ):
            items = bootstrap_items()
            items[0]["metadata"][field] = invalid
            with self.subTest(field=field, invalid=invalid):
                with self.assertRaises(BootstrapInventoryError):
                    validate(items)
        duplicate_uid = bootstrap_items()
        duplicate_uid[-1]["metadata"]["uid"] = duplicate_uid[0]["metadata"]["uid"]
        with self.assertRaises(BootstrapInventoryError):
            validate(duplicate_uid)
        with self.assertRaises(BootstrapInventoryError):
            validate(cluster_incarnation_uid="uid-001")

    def test_swapped_namespace_wrong_api_and_forbidden_accounts_fail(self) -> None:
        for mutation in ("namespace", "apiVersion", "forbidden"):
            items = bootstrap_items()
            account = next(item for item in items if relevant_key(item) ==
                           ("ServiceAccount", "kube-system", "coredns"))
            if mutation == "namespace":
                account["metadata"]["namespace"] = "default"
            elif mutation == "apiVersion":
                account["apiVersion"] = "v1beta1"
            else:
                account["metadata"]["name"] = "resource-pool-status-controller"
            with self.subTest(mutation=mutation):
                with self.assertRaises(BootstrapInventoryError):
                    validate(items)

    def test_service_accounts_reject_runtime_or_configuration_additions(self) -> None:
        for field, value in (
            ("status", {}), ("secrets", []), ("imagePullSecrets", []),
            ("automountServiceAccountToken", False), ("foreign", True),
        ):
            items = bootstrap_items()
            account = next(item for item in items if relevant_key(item) ==
                           ("ServiceAccount", "default", "default"))
            account[field] = value
            with self.subTest(field=field):
                with self.assertRaises(BootstrapInventoryError):
                    validate(items)

    def test_kil_and_calico_configurations_are_independently_exact(self) -> None:
        for key in (
            ("ConfigMap", "kil-v3-baseline", "authz-config"),
            ("ConfigMap", "kube-system", "calico-config"),
        ):
            items = bootstrap_items()
            config_map = next(item for item in items if relevant_key(item) == key)
            config_map["data"][next(iter(config_map["data"]))] = "drifted"
            with self.subTest(key=key):
                with self.assertRaises(BootstrapInventoryError):
                    validate(items)

    def test_platform_configmaps_are_closed_and_bounded_but_not_semantically_accepted(self) -> None:
        mutations = (
            ("root", "status", {}),
            ("root", "immutable", False),
            ("root", "foreign", True),
            ("root", "data", None),
            ("root", "binaryData", {"key": "eA=="}),
            ("root", "binaryData", {"key": "not-base64!"}),
            ("metadata", "ownerReferences", []),
            ("metadata", "deletionTimestamp", "2026-09-06T01:02:03Z"),
            ("metadata", "foreign", True),
        )
        for location, field, value in mutations:
            items = bootstrap_items()
            config_map = next(item for item in items if relevant_key(item) ==
                              ("ConfigMap", "kube-system", "coredns"))
            target = config_map if location == "root" else config_map["metadata"]
            target[field] = value
            with self.subTest(location=location, field=field):
                with self.assertRaises(BootstrapInventoryError):
                    validate(items)

    def test_platform_configmap_lone_surrogates_are_normalized_to_domain_errors(self) -> None:
        surrogate = "\ud800"
        mutations = (
            ("labels", {"safe": surrogate}),
            ("labels", {surrogate: "safe"}),
            ("annotations", {"safe": surrogate}),
            ("annotations", {surrogate: "safe"}),
            ("data", {"safe": surrogate}),
            ("data", {surrogate: "safe"}),
        )
        for field, value in mutations:
            items = bootstrap_items()
            config_map = next(item for item in items if relevant_key(item) ==
                              ("ConfigMap", "kube-system", "coredns"))
            target = config_map if field == "data" else config_map["metadata"]
            target[field] = value
            with self.subTest(field=field, surrogate_in="key" if surrogate in value else "value"):
                with self.assertRaises(BootstrapInventoryError):
                    validate(items)

    def test_nonselected_kinds_do_not_expand_the_claim(self) -> None:
        items = bootstrap_items()
        items.append({"apiVersion": "example/v1", "kind": "Unreviewed",
                      "metadata": {"name": "ignored"}, "arbitrary": {"nested": True}})
        snapshot = validate(items)
        self.assertEqual(sum((len(snapshot.namespace_bindings),
                              len(snapshot.service_account_bindings),
                              len(snapshot.config_map_bindings))), 97)

    def test_payload_contract_and_duplicate_json_keys_fail_closed(self) -> None:
        for invalid in (None, {}, "text", bytearray(b"{}"), b"[]", b'{"apiVersion":"v1","apiVersion":"v1"}'):
            with self.subTest(invalid=type(invalid).__name__):
                with self.assertRaises(BootstrapInventoryError):
                    validate_bootstrap_identities(
                        invalid, profile=profile(), workload=WORKLOAD,
                        cluster_incarnation_uid="uid-007",
                    )
        with self.assertRaises(BootstrapInventoryError):
            validate(prior=object())

    def test_forged_prior_shape_and_oversized_platform_content_fail_with_domain_error(self) -> None:
        prior = validate()
        changed = list(prior.namespace_bindings)
        first = changed[0]
        changed[0] = BootstrapIdentityBinding(
            first.api_version, first.kind, first.namespace, "aaa-forged",
            first.uid, first.resource_version,
        )
        object.__setattr__(prior, "namespace_bindings", tuple(changed))
        with self.assertRaises(BootstrapInventoryError):
            validate(prior=prior)

        items = bootstrap_items()
        config_map = next(item for item in items if relevant_key(item) ==
                          ("ConfigMap", "kube-system", "coredns"))
        config_map["data"] = {"large": "x" * 1_000_001}
        with self.assertRaises(BootstrapInventoryError):
            validate(items)


if __name__ == "__main__":
    unittest.main()
