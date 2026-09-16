"""Independent reviewed controller-manager disk and API fixtures."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, replace
import importlib
import importlib.util
import json
import unittest

from kil.v3b2_control_plane_manifest_source import validate_control_plane_manifest_source
from kil.v3b2_runtime_ownership import validate_runtime_ownership
from tests.test_v3b2_control_plane_manifest_source import (
    context as source_context, identity as source_identity,
    observations as source_observations,
    node as source_node,
)
from tests.test_v3b2_driver_pod_configuration import (
    PROFILE as OWNERSHIP_PROFILE, WORKLOAD as OWNERSHIP_WORKLOAD,
)
from tests.test_v3b2_runtime_ownership import fixture as ownership_fixture, encode


MODULE = "kil.v3b2_kube_controller_manager_mirror_configuration"
NODE = "kil-v3-lab-control-plane"
COMPONENT = "kube-controller-manager"
POD_NAME = COMPONENT + "-" + NODE
CA_CANDIDATES = (
    ("etc-ca-certificates", "/etc/ca-certificates"),
    ("etc-pki-ca-trust", "/etc/pki/ca-trust"),
    ("etc-pki-tls-certs", "/etc/pki/tls/certs"),
    ("usr-local-share-ca-certificates", "/usr/local/share/ca-certificates"),
    ("usr-share-ca-certificates", "/usr/share/ca-certificates"),
)
MATCHED_OWNERSHIP_IDENTITY = source_identity()
MATCHED_WORKLOAD = replace(OWNERSHIP_WORKLOAD,
                           run_id="v3b2-" + source_context().run_id)


def _scalar(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if type(value) is int:
        return str(value)
    if type(value) is str:
        return json.dumps(value)
    raise TypeError(value)


def _yaml_lines(value, indent=0):
    prefix = " " * indent
    if type(value) is dict:
        if not value:
            return [prefix + "{}"]
        rows = []
        for key, member in value.items():
            if type(member) in (dict, list) and member:
                rows.append(f"{prefix}{key}:")
                rows.extend(_yaml_lines(member, indent + 2))
            elif type(member) is dict:
                rows.append(f"{prefix}{key}: {{}}")
            elif type(member) is list:
                rows.append(f"{prefix}{key}: []")
            else:
                rows.append(f"{prefix}{key}: {_scalar(member)}")
        return rows
    if type(value) is list:
        if not value:
            return [prefix + "[]"]
        rows = []
        for member in value:
            if type(member) in (dict, list) and member:
                rows.append(prefix + "-")
                rows.extend(_yaml_lines(member, indent + 2))
            elif type(member) is dict:
                rows.append(prefix + "- {}")
            elif type(member) is list:
                rows.append(prefix + "- []")
            else:
                rows.append(prefix + "- " + _scalar(member))
        return rows
    return [prefix + _scalar(value)]


def yaml_bytes(document):
    return ("\n".join(_yaml_lines(document)) + "\n").encode()


def disk_pod(selected=()):
    pairs = sorted((("ca-certs", "/etc/ssl/certs"), *selected,
                    ("k8s-certs", "/etc/kubernetes/pki"),
                    ("kubeconfig", "/etc/kubernetes/controller-manager.conf")))
    return {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"labels": {"component": COMPONENT, "tier": "control-plane"},
                     "name": COMPONENT, "namespace": "kube-system"},
        "spec": {
            "hostNetwork": True, "priority": 2000001000,
            "priorityClassName": "system-node-critical",
            "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
            "volumes": [{"name": name, "hostPath": {"path": path,
                "type": "FileOrCreate" if name == "kubeconfig" else "DirectoryOrCreate"}}
                for name, path in pairs],
            "containers": [{
                "name": COMPONENT,
                "image": "registry.k8s.io/kube-controller-manager:v1.36.1",
                "imagePullPolicy": "IfNotPresent",
                "command": [
                    "kube-controller-manager", "--allocate-node-cidrs=true",
                    "--authentication-kubeconfig=/etc/kubernetes/controller-manager.conf",
                    "--authorization-kubeconfig=/etc/kubernetes/controller-manager.conf",
                    "--bind-address=127.0.0.1",
                    "--client-ca-file=/etc/kubernetes/pki/ca.crt",
                    "--cluster-cidr=10.244.0.0/16", "--cluster-name=kil-v3-lab",
                    "--cluster-signing-cert-file=/etc/kubernetes/pki/ca.crt",
                    "--cluster-signing-key-file=/etc/kubernetes/pki/ca.key",
                    "--controllers=*,bootstrapsigner,tokencleaner",
                    "--enable-hostpath-provisioner=true",
                    "--kubeconfig=/etc/kubernetes/controller-manager.conf",
                    "--leader-elect=true",
                    "--requestheader-client-ca-file=/etc/kubernetes/pki/front-proxy-ca.crt",
                    "--root-ca-file=/etc/kubernetes/pki/ca.crt",
                    "--service-account-private-key-file=/etc/kubernetes/pki/sa.key",
                    "--service-cluster-ip-range=10.96.0.0/16",
                    "--use-service-account-credentials=true",
                ],
                "resources": {"requests": {"cpu": "200m"}},
                "ports": [{"name": "probe-port", "containerPort": 10257, "protocol": "TCP"}],
                "volumeMounts": [{"name": name, "mountPath": path, "readOnly": True}
                                 for name, path in pairs],
                "livenessProbe": {"httpGet": {"host": "127.0.0.1", "path": "/healthz",
                    "port": "probe-port", "scheme": "HTTPS"}, "initialDelaySeconds": 10,
                    "periodSeconds": 10, "timeoutSeconds": 15, "failureThreshold": 8},
                "startupProbe": {"httpGet": {"host": "127.0.0.1", "path": "/healthz",
                    "port": "probe-port", "scheme": "HTTPS"}, "initialDelaySeconds": 10,
                    "periodSeconds": 10, "timeoutSeconds": 15, "failureThreshold": 24},
            }],
        },
    }


def api_spec(selected=()):
    # Independent API literals: no disk builder or production expected factory.
    api_pairs = list(selected)
    api_pairs.extend((("kubeconfig", "/etc/kubernetes/controller-manager.conf"),
                      ("ca-certs", "/etc/ssl/certs"),
                      ("k8s-certs", "/etc/kubernetes/pki")))
    api_pairs.sort(key=lambda pair: pair[0])
    return {
        "nodeName": NODE, "hostNetwork": True, "priority": 2000001000,
        "priorityClassName": "system-node-critical", "preemptionPolicy": "PreemptLowerPriority",
        "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
        "tolerations": [{"operator": "Exists", "effect": "NoExecute"}],
        "volumes": [{"hostPath": {"type": "FileOrCreate" if name == "kubeconfig"
            else "DirectoryOrCreate", "path": path}, "name": name} for name, path in api_pairs],
        "containers": [{
            "image": "registry.k8s.io/kube-controller-manager:v1.36.1",
            "name": COMPONENT, "imagePullPolicy": "IfNotPresent",
            "command": [
                "kube-controller-manager", "--allocate-node-cidrs=true",
                "--authentication-kubeconfig=/etc/kubernetes/controller-manager.conf",
                "--authorization-kubeconfig=/etc/kubernetes/controller-manager.conf",
                "--bind-address=127.0.0.1", "--client-ca-file=/etc/kubernetes/pki/ca.crt",
                "--cluster-cidr=10.244.0.0/16", "--cluster-name=kil-v3-lab",
                "--cluster-signing-cert-file=/etc/kubernetes/pki/ca.crt",
                "--cluster-signing-key-file=/etc/kubernetes/pki/ca.key",
                "--controllers=*,bootstrapsigner,tokencleaner", "--enable-hostpath-provisioner=true",
                "--kubeconfig=/etc/kubernetes/controller-manager.conf", "--leader-elect=true",
                "--requestheader-client-ca-file=/etc/kubernetes/pki/front-proxy-ca.crt",
                "--root-ca-file=/etc/kubernetes/pki/ca.crt",
                "--service-account-private-key-file=/etc/kubernetes/pki/sa.key",
                "--service-cluster-ip-range=10.96.0.0/16", "--use-service-account-credentials=true",
            ],
            "resources": {"requests": {"cpu": "200m"}},
            "ports": [{"containerPort": 10257, "hostPort": 10257,
                       "protocol": "TCP", "name": "probe-port"}],
            "volumeMounts": [{"mountPath": path, "readOnly": True, "name": name}
                             for name, path in api_pairs],
            "livenessProbe": {"failureThreshold": 8, "initialDelaySeconds": 10,
                "periodSeconds": 10, "timeoutSeconds": 15, "httpGet": {"host": "127.0.0.1",
                    "path": "/healthz", "port": "probe-port", "scheme": "HTTPS"}},
            "startupProbe": {"failureThreshold": 24, "initialDelaySeconds": 10,
                "periodSeconds": 10, "timeoutSeconds": 15, "httpGet": {"host": "127.0.0.1",
                    "path": "/healthz", "port": "probe-port", "scheme": "HTTPS"}},
        }],
    }


def row(document):
    return next(item for item in document["items"] if item["kind"] == "Pod"
                and item["metadata"]["name"] == POD_NAME)


def literal_source_fixture(selected=(), document=None, *, source_inputs=None):
    owned = source_identity()
    inputs = {} if source_inputs is None else source_inputs
    requested_image = inputs.get("kind_node_image", OWNERSHIP_PROFILE.kind_node_image)
    return validate_control_plane_manifest_source(
        context=source_context(owned, **inputs), owned_identity=owned,
        observations=source_observations(owned, controller=yaml_bytes(
            disk_pod(selected) if document is None else document),
            before=source_node(requested_image=requested_image),
            after=source_node(requested_image=requested_image)))


def profile_mapping():
    profile = asdict(OWNERSHIP_PROFILE)
    profile["calico_images"] = dict(OWNERSHIP_PROFILE.calico_images)
    return profile


def api_document(selected=(), owned_identity=MATCHED_OWNERSHIP_IDENTITY,
                 workload=MATCHED_WORKLOAD):
    args = ownership_fixture(owned_identity=owned_identity, workload=workload)
    document = json.loads(args["runtime_objects"])
    pod = row(document)
    pod["metadata"].update(generation=1, creationTimestamp="2026-09-16T01:00:00Z",
                          labels={"component": COMPONENT, "tier": "control-plane"})
    pod["metadata"]["annotations"]["kubernetes.io/config.seen"] = "2026-09-16T01:00:00.123456789Z"
    pod["spec"] = api_spec(selected)
    return args, document


def literal_runtime_fixture(selected=(), document=None, owned_identity=MATCHED_OWNERSHIP_IDENTITY,
                            workload=MATCHED_WORKLOAD):
    args, default = api_document(selected, owned_identity, workload)
    args["runtime_objects"] = encode(default if document is None else document)
    return validate_runtime_ownership(**args)


def mutate(document, path, value):
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


class KubeControllerManagerMirrorConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE),
                             "controller-manager mirror configuration adapter is missing")
        self.module = importlib.import_module(MODULE)
        self.error = self.module.KubeControllerManagerMirrorConfigurationError

    def validate(self, selected=(), *, disk=None, api=None):
        return self.module.validate_kube_controller_manager_mirror_configuration(
            ownership=literal_runtime_fixture(selected, api),
            source=literal_source_fixture(selected, disk))

    def test_all_32_subsets_accept_and_factory_has_exact_order(self):
        for mask in range(32):
            selected = tuple(pair for bit, pair in enumerate(CA_CANDIDATES) if mask & (1 << bit))
            with self.subTest(mask=mask):
                proof = self.validate(selected)
                self.assertEqual(proof.bindings[0].component, COMPONENT)
                self.assertEqual(proof.bindings[0].conditional_volume_names,
                                 tuple(name for name, _path in selected))
                self.assertIs(proof.runtime_complete, False)
                self.assertIs(proof.application_complete, False)
                actual = self.module.kube_controller_manager_mirror_api_spec(source=proof.source)
                self.assertEqual(actual, api_spec(selected))
                names = sorted(("ca-certs", "k8s-certs", "kubeconfig", *(name for name, _ in selected)))
                for spec in (disk_pod(selected)["spec"], actual):
                    self.assertEqual([v["name"] for v in spec["volumes"]], names)
                    self.assertEqual([m["name"] for m in spec["containers"][0]["volumeMounts"]], names)

    def test_all_32_disk_api_subset_mismatches_reject(self):
        for mask in range(32):
            selected = tuple(pair for bit, pair in enumerate(CA_CANDIDATES) if mask & (1 << bit))
            other = tuple(pair for bit, pair in enumerate(CA_CANDIDATES) if (mask ^ 1) & (1 << bit))
            _args, document = api_document(other)
            with self.subTest(mask=mask), self.assertRaises(self.error):
                self.validate(selected, api=document)

    def test_every_unconditional_and_conditional_pair_is_closed(self):
        for family in ("disk", "api"):
            for index in range(8):
                for kind, key, value in (
                    ("volume", "path", "/foreign"), ("volume", "type", "Directory"),
                    ("mount", "mountPath", "/foreign"), ("mount", "readOnly", False),
                    ("mount", "readOnly", 1),
                ):
                    disk = disk_pod(CA_CANDIDATES)
                    _args, api = api_document(CA_CANDIDATES)
                    spec = disk["spec"] if family == "disk" else row(api)["spec"]
                    target = (spec["volumes"][index]["hostPath"] if kind == "volume"
                              else spec["containers"][0]["volumeMounts"][index])
                    target[key] = value
                    with self.subTest(family=family, index=index, key=key, value=value), self.assertRaises(self.error):
                        self.validate(CA_CANDIDATES, **{family: disk if family == "disk" else api})

    def test_malformed_duplicate_renamed_unexpected_incomplete_and_reordered_pairs(self):
        for family in ("disk", "api"):
            for mutation in ("duplicate", "renamed", "unexpected", "reordered", "volume-only",
                             "mount-only", "missing-required", "malformed", "not-list"):
                disk = disk_pod(CA_CANDIDATES)
                _args, api = api_document(CA_CANDIDATES)
                spec = disk["spec"] if family == "disk" else row(api)["spec"]
                volumes, mounts = spec["volumes"], spec["containers"][0]["volumeMounts"]
                if mutation == "duplicate":
                    volumes.insert(2, deepcopy(volumes[1])); mounts.insert(2, deepcopy(mounts[1]))
                elif mutation == "renamed":
                    volumes[1]["name"] = "renamed"; mounts[1]["name"] = "renamed"
                elif mutation == "unexpected":
                    volumes.append({"name": "foreign", "hostPath": {"path": "/foreign", "type": "DirectoryOrCreate"}})
                    mounts.append({"name": "foreign", "mountPath": "/foreign", "readOnly": True})
                elif mutation == "reordered":
                    volumes.reverse(); mounts.reverse()
                elif mutation == "volume-only":
                    mounts.pop(1)
                elif mutation == "mount-only":
                    volumes.pop(1)
                elif mutation == "missing-required":
                    volumes.pop(5); mounts.pop(5)  # kubeconfig
                elif mutation == "malformed":
                    volumes[1] = None
                else:
                    spec["volumes"] = {}
                with self.subTest(family=family, mutation=mutation), self.assertRaises(self.error):
                    self.validate(CA_CANDIDATES, **{family: disk if family == "disk" else api})

    def test_fixed_disk_and_api_configuration_fields_are_closed(self):
        base = disk_pod()["spec"]["containers"][0]
        cases = [
            (("metadata", "labels", "tier"), "foreign"),
            (("spec", "hostNetwork"), 1), (("spec", "priority"), True),
            (("spec", "priorityClassName"), "foreign"),
            (("spec", "securityContext", "seccompProfile", "type"), "Unconfined"),
            (("spec", "containers", 0, "image"), "foreign"),
            (("spec", "containers", 0, "imagePullPolicy"), "Always"),
            (("spec", "containers", 0, "name"), "foreign"),
            (("spec", "containers", 0, "resources", "requests", "cpu"), "250m"),
            (("spec", "containers", 0, "ports", 0, "containerPort"), 10259),
            (("spec", "containers", 0, "ports", 0, "protocol"), "UDP"),
            (("spec", "containers", 0, "readinessProbe"), {}),
            (("spec", "foreign"), "x"),
        ]
        cases.extend((("spec", "containers", 0, "command", i), value + "-foreign")
                     for i, value in enumerate(base["command"]))
        for probe in ("livenessProbe", "startupProbe"):
            for key, value in (("failureThreshold", 1), ("periodSeconds", 1),
                               ("timeoutSeconds", 1), ("initialDelaySeconds", 1)):
                cases.append((("spec", "containers", 0, probe, key), value))
            for key, value in (("host", "172.18.0.2"), ("path", "/livez"),
                               ("port", 10257), ("scheme", "HTTP")):
                cases.append((("spec", "containers", 0, probe, "httpGet", key), value))
        for family in ("disk", "api"):
            for path, value in cases:
                disk = disk_pod()
                _args, api = api_document()
                mutate(disk if family == "disk" else row(api), path, value)
                with self.subTest(family=family, path=path), self.assertRaises(self.error):
                    self.validate(**{family: disk if family == "disk" else api})
        for path, value in ((("metadata", "name"), "foreign"),
                            (("metadata", "namespace"), "default"),
                            (("metadata", "annotations"), {}), (("status",), {})):
            disk = disk_pod()
            mutate(disk, path, value)
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.validate(disk=disk)

    def test_api_metadata_defaulting_and_arbitrary_status_retention(self):
        _args, document = api_document(CA_CANDIDATES[:2])
        pod = row(document)
        pod["status"] = {"phase": "Failed", "arbitrary": [False, 7, None]}
        pod["metadata"]["managedFields"] = []
        proof = self.validate(CA_CANDIDATES[:2], api=document)
        self.assertEqual(proof.ownership.runtime_objects, encode(document))
        spec = pod["spec"]
        spec.update(dnsPolicy="ClusterFirst", restartPolicy="Always", terminationGracePeriodSeconds=30,
                    schedulerName="default-scheduler", enableServiceLinks=True)
        container = spec["containers"][0]
        container.update(terminationMessagePath="/dev/termination-log", terminationMessagePolicy="File")
        for probe in ("livenessProbe", "startupProbe"):
            container[probe]["successThreshold"] = 1
        self.validate(CA_CANDIDATES[:2], api=document)

    def test_api_metadata_and_kubelet_defaults_fail_closed(self):
        cases = [
            (("metadata", "generation"), True), (("metadata", "generation"), 2),
            (("metadata", "creationTimestamp"), "bad"), (("metadata", "foreign"), "x"),
            (("metadata", "managedFields"), [{}]), (("metadata", "annotations", "foreign"), "x"),
            (("spec", "preemptionPolicy"), "Never"), (("spec", "tolerations"), []),
            (("spec", "dnsPolicy"), "Default"), (("spec", "enableServiceLinks"), 1),
            (("spec", "containers", 0, "ports", 0, "hostPort"), 1),
            (("spec", "containers", 0, "livenessProbe", "successThreshold"), 2),
            (("spec", "serviceAccountName"), "default"), (("foreign",), {}),
        ]
        for path, value in cases:
            _args, document = api_document()
            mutate(row(document), path, value)
            with self.subTest(path=path), self.assertRaises(self.error):
                self.validate(api=document)
        for value in (None, 1, "2026-09-16T01:00:00Z", "2026-09-16T01:00:00.1234567890Z",
                      "2025-02-29T01:00:00.123456789Z", "2026-09-16T24:00:00.123456789Z",
                      "2026-09-16T01:00:00.123456789+00:00", "2026-09-16T01:00:00.123456789+24:00"):
            _args, document = api_document()
            row(document)["metadata"]["annotations"]["kubernetes.io/config.seen"] = value
            with self.subTest(seen=value), self.assertRaises(self.error):
                self.validate(api=document)
        for value in ("2020-01-01T00:00:00.000000000Z", "2026-09-16T01:00:00.123456789-07:00"):
            _args, document = api_document()
            row(document)["metadata"]["annotations"]["kubernetes.io/config.seen"] = value
            self.validate(api=document)

    def test_factory_is_fresh_and_reconstructs_source(self):
        source = literal_source_fixture(CA_CANDIDATES[::2])
        actual = self.module.kube_controller_manager_mirror_api_spec(source=source)
        actual["containers"][0]["command"].clear()
        self.assertEqual(self.module.kube_controller_manager_mirror_api_spec(source=source),
                         api_spec(CA_CANDIDATES[::2]))
        forged = deepcopy(source)
        object.__setattr__(forged, "bindings", source.bindings[::-1])
        for candidate in (None, forged):
            with self.assertRaises(self.error):
                self.module.kube_controller_manager_mirror_api_spec(source=candidate)

    def test_dependency_and_coordinated_configuration_tampering_reconstruct(self):
        proof = self.validate(CA_CANDIDATES[:1])
        source = deepcopy(proof.source)
        object.__setattr__(source, "bindings", source.bindings[::-1])
        with self.assertRaises(self.error):
            replace(proof, source=source)
        ownership = deepcopy(proof.ownership)
        _args, document = api_document(CA_CANDIDATES[:1])
        for key in ("kubernetes.io/config.hash", "kubernetes.io/config.mirror"):
            row(document)["metadata"]["annotations"][key] = "f" * 32
        object.__setattr__(ownership, "runtime_objects", encode(document))
        with self.assertRaises(self.error):
            replace(proof, ownership=ownership)
        disk = disk_pod(CA_CANDIDATES[:1])
        _args, api = api_document(CA_CANDIDATES[:1])
        for candidate in (disk, row(api)):
            candidate["spec"]["containers"][0]["command"][7] = "--cluster-name=foreign"
        with self.assertRaises(self.error):
            self.validate(CA_CANDIDATES[:1], disk=disk, api=api)
        for path, value in ((("metadata", "ownerReferences", 0, "controller"), 1),
                            (("metadata", "ownerReferences", 0, "blockOwnerDeletion"), True),
                            (("spec", "nodeName"), "foreign")):
            ownership = deepcopy(proof.ownership)
            _args, document = api_document(CA_CANDIDATES[:1])
            mutate(row(document), path, value)
            object.__setattr__(ownership, "runtime_objects", encode(document))
            with self.subTest(path=path), self.assertRaises(self.error):
                replace(proof, ownership=ownership)

    def test_independently_valid_cross_proof_identity_mismatches_reject(self):
        source = literal_source_fixture()
        for changes in ({"cluster_incarnation_uid": "5b9f7ce2-9876-4f55-9a23-a9f00fbbde11"},
                        {"node_container_id": "b" * 64}):
            ownership = literal_runtime_fixture(owned_identity=replace(MATCHED_OWNERSHIP_IDENTITY, **changes))
            source.__post_init__(); ownership.__post_init__()
            with self.subTest(changes=changes), self.assertRaises(self.error):
                self.module.validate_kube_controller_manager_mirror_configuration(ownership=ownership, source=source)

    def reject_independently_valid_authority_mismatch(self, **changes):
        proof = self.validate()
        self.assertEqual(proof.source.run_id,
                         proof.ownership.workload.run_id.removeprefix("v3b2-"))
        self.assertEqual(source_identity(), proof.ownership.owned_identity)
        ownership = literal_runtime_fixture(**changes)
        proof.source.__post_init__()
        ownership.__post_init__()
        self.assertEqual(proof.source.cluster_uid,
                         ownership.owned_identity.cluster_incarnation_uid)
        self.assertEqual(proof.source.node_container_id,
                         ownership.owned_identity.node_container_id)
        for boundary in ("validator", "constructor"):
            with self.subTest(boundary=boundary), self.assertRaises(self.error):
                if boundary == "validator":
                    self.module.validate_kube_controller_manager_mirror_configuration(
                        ownership=ownership, source=proof.source)
                else:
                    replace(proof, ownership=ownership)

    def test_independently_valid_run_only_mismatch_is_rejected(self):
        workload = replace(MATCHED_WORKLOAD, run_id="v3b2-" + "d" * 64)
        self.assertNotEqual(workload.run_id, MATCHED_WORKLOAD.run_id)
        self.reject_independently_valid_authority_mismatch(workload=workload)

    def test_independently_valid_docker_endpoint_only_mismatch_is_rejected(self):
        owned = replace(MATCHED_OWNERSHIP_IDENTITY,
                        docker_host="unix:///tmp/other/kil-v3-lab/docker.sock")
        self.assertNotEqual(owned.docker_host, MATCHED_OWNERSHIP_IDENTITY.docker_host)
        self.reject_independently_valid_authority_mismatch(owned_identity=owned)

    def test_independently_valid_kubeconfig_only_mismatch_is_rejected(self):
        owned = replace(MATCHED_OWNERSHIP_IDENTITY, kubeconfig="/tmp/other/kubeconfig")
        self.assertNotEqual(owned.kubeconfig, MATCHED_OWNERSHIP_IDENTITY.kubeconfig)
        self.reject_independently_valid_authority_mismatch(owned_identity=owned)

    def reject_independently_valid_producer_authority(self, source):
        proof = self.validate()
        source.__post_init__()
        proof.ownership.__post_init__()
        self.assertEqual(source.run_id, proof.source.run_id)
        self.assertEqual(source.cluster_uid, proof.source.cluster_uid)
        self.assertEqual(source.node_container_id, proof.source.node_container_id)
        for boundary in ("validator", "constructor"):
            with self.subTest(boundary=boundary), self.assertRaises(self.error):
                if boundary == "validator":
                    self.module.validate_kube_controller_manager_mirror_configuration(
                        ownership=proof.ownership, source=source)
                else:
                    replace(proof, source=source)

    def test_source_requested_image_must_match_owned_profile(self):
        alternate_image = "kindest/node:v1.36.1@sha256:" + "d" * 64
        self.assertNotEqual(alternate_image, OWNERSHIP_PROFILE.kind_node_image)
        for include_profile in (False, True):
            inputs = {"kind_node_image": alternate_image}
            if include_profile:
                inputs["profile"] = profile_mapping()
            with self.subTest(include_profile=include_profile):
                self.reject_independently_valid_producer_authority(
                    literal_source_fixture(source_inputs=inputs))

    def test_matching_full_profile_and_minimal_contexts_are_accepted(self):
        for inputs in ({}, {"profile": profile_mapping()}):
            source = literal_source_fixture(CA_CANDIDATES[:1], source_inputs=inputs)
            ownership = literal_runtime_fixture(CA_CANDIDATES[:1])
            proof = self.module.validate_kube_controller_manager_mirror_configuration(
                ownership=ownership, source=source)
            self.assertEqual(replace(proof), proof)

    def test_optional_source_profile_must_reconstruct_exact_owned_profile(self):
        cases = []
        for field, value in (("kind_node_image", "kindest/node:v1.36.1@sha256:" + "d" * 64),
                             ("pod_subnet", "10.245.0.0/16"), ("service_subnet", "10.97.0.0/16"),
                             ("kind_version", True)):
            profile = profile_mapping()
            profile[field] = value
            cases.append((field, profile))
        missing = profile_mapping()
        del missing["kind_node_image"]
        extra = profile_mapping()
        extra["foreign"] = "x"
        cases.extend((("missing", missing), ("extra", extra), ("scalar-bool", True),
                      ("non-schema-calico-array", asdict(OWNERSHIP_PROFILE))))
        for label, profile in cases:
            with self.subTest(profile=label):
                self.reject_independently_valid_producer_authority(
                    literal_source_fixture(source_inputs={"profile": profile}))

    def test_exact_constructors_bindings_false_flags_and_frozen_slots(self):
        proof = self.validate(CA_CANDIDATES[:2])
        self.assertEqual(replace(proof), proof)
        self.assertIs(proof.runtime_contract_complete, False)
        self.assertIs(proof.full_application_contract_complete, False)
        for flag in ("runtime_complete", "application_complete", "runtime_contract_complete", "full_application_contract_complete"):
            for value in (True, 0, None):
                with self.subTest(flag=flag, value=value), self.assertRaises(self.error):
                    replace(proof, **{flag: value})
        binding = proof.bindings[0]
        for field, value in (("component", "etcd"), ("namespace", "default"), ("pod_name", "foreign"),
                             ("pod_uid", None), ("pod_resource_version", True), ("config_hash", "x"),
                             ("conditional_volume_names", list(binding.conditional_volume_names)),
                             ("conditional_volume_names", tuple(reversed(binding.conditional_volume_names)))):
            with self.subTest(field=field), self.assertRaises(self.error):
                replace(binding, **{field: value})
        for field, value in (("pod_uid", "foreign"), ("pod_resource_version", "999"),
                             ("config_hash", "f" * 32), ("conditional_volume_names", ())):
            forged = replace(binding, **{field: value})
            with self.subTest(field=field), self.assertRaises(self.error):
                replace(proof, bindings=(forged,))
        subclass_type = type("SubBinding", (type(binding),), {})
        subclass = subclass_type(**{name: getattr(binding, name) for name in binding.__dataclass_fields__})
        for bindings in ([], (), (subclass,), proof.bindings * 2):
            with self.assertRaises(self.error):
                replace(proof, bindings=bindings)
        for field in ("ownership", "source"):
            dependency = getattr(proof, field)
            subclass_type = type("SubDependency", (type(dependency),), {})
            subclass = subclass_type(**{name: getattr(dependency, name) for name in dependency.__dataclass_fields__})
            for value in (None, subclass):
                with self.subTest(field=field), self.assertRaises(self.error):
                    replace(proof, **{field: value})
        self.assertFalse(hasattr(proof, "__dict__"))
        self.assertFalse(hasattr(binding, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            proof.bindings = ()
        with self.assertRaises(FrozenInstanceError):
            binding.component = "etcd"


if __name__ == "__main__":
    unittest.main()
