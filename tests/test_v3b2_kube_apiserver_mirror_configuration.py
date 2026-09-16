"""Independent disk/API fixtures for the kube-apiserver mirror proof."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import unittest

from kil.v3b2_control_plane_manifest_source import validate_control_plane_manifest_source
from kil.v3b2_runtime_ownership import validate_runtime_ownership
from tests.test_v3b2_control_plane_manifest_source import (
    context as source_context,
    identity as source_identity,
    observations as source_observations,
)
from tests.test_v3b2_driver_pod_configuration import IDENTITY as OWNERSHIP_IDENTITY
from tests.test_v3b2_runtime_ownership import fixture as ownership_fixture, encode


MODULE = "kil.v3b2_kube_apiserver_mirror_configuration"
NODE = "kil-v3-lab-control-plane"
POD_NAME = "kube-apiserver-" + NODE
DEFAULT_IP = "172.18.0.2"
CA_CANDIDATES = (
    ("etc-ca-certificates", "/etc/ca-certificates"),
    ("etc-pki-ca-trust", "/etc/pki/ca-trust"),
    ("etc-pki-tls-certs", "/etc/pki/tls/certs"),
    ("usr-local-share-ca-certificates", "/usr/local/share/ca-certificates"),
    ("usr-share-ca-certificates", "/usr/share/ca-certificates"),
)
MATCHED_OWNERSHIP_IDENTITY = replace(
    OWNERSHIP_IDENTITY,
    cluster_incarnation_uid=source_identity().cluster_incarnation_uid,
)


def _scalar(value):
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


def command(ip):
    return [
        "kube-apiserver",
        f"--advertise-address={ip}",
        "--allow-privileged=true",
        "--authorization-mode=Node,RBAC",
        "--client-ca-file=/etc/kubernetes/pki/ca.crt",
        "--enable-admission-plugins=NodeRestriction",
        "--enable-bootstrap-token-auth=true",
        "--etcd-cafile=/etc/kubernetes/pki/etcd/ca.crt",
        "--etcd-certfile=/etc/kubernetes/pki/apiserver-etcd-client.crt",
        "--etcd-keyfile=/etc/kubernetes/pki/apiserver-etcd-client.key",
        "--etcd-servers=https://127.0.0.1:2379",
        "--kubelet-client-certificate=/etc/kubernetes/pki/apiserver-kubelet-client.crt",
        "--kubelet-client-key=/etc/kubernetes/pki/apiserver-kubelet-client.key",
        "--kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname",
        "--proxy-client-cert-file=/etc/kubernetes/pki/front-proxy-client.crt",
        "--proxy-client-key-file=/etc/kubernetes/pki/front-proxy-client.key",
        "--requestheader-allowed-names=front-proxy-client",
        "--requestheader-client-ca-file=/etc/kubernetes/pki/front-proxy-ca.crt",
        "--requestheader-extra-headers-prefix=X-Remote-Extra-",
        "--requestheader-group-headers=X-Remote-Group",
        "--requestheader-username-headers=X-Remote-User",
        "--secure-port=6443",
        "--service-account-issuer=https://kubernetes.default.svc.cluster.local",
        "--service-account-key-file=/etc/kubernetes/pki/sa.pub",
        "--service-account-signing-key-file=/etc/kubernetes/pki/sa.key",
        "--service-cluster-ip-range=10.96.0.0/16",
        "--tls-cert-file=/etc/kubernetes/pki/apiserver.crt",
        "--tls-private-key-file=/etc/kubernetes/pki/apiserver.key",
    ]


def _mounts(selected):
    pairs = (("ca-certs", "/etc/ssl/certs"), *selected,
             ("k8s-certs", "/etc/kubernetes/pki"))
    return [{"mountPath": path, "name": name, "readOnly": True}
            for name, path in sorted(pairs)]


def _volumes(selected):
    pairs = (("ca-certs", "/etc/ssl/certs"), *selected,
             ("k8s-certs", "/etc/kubernetes/pki"))
    return [{"hostPath": {"path": path, "type": "DirectoryOrCreate"}, "name": name}
            for name, path in sorted(pairs)]


def _api_mounts(selected):
    # Kept separate from the disk candidate builder so API disagreement is
    # capable of failing the validator rather than sharing candidate state.
    pairs = list(selected)
    pairs.extend((("ca-certs", "/etc/ssl/certs"),
                  ("k8s-certs", "/etc/kubernetes/pki")))
    return [{"name": name, "mountPath": path, "readOnly": True}
            for name, path in sorted(pairs, key=lambda pair: pair[0])]


def _api_volumes(selected):
    pairs = list(selected)
    pairs.extend((("ca-certs", "/etc/ssl/certs"),
                  ("k8s-certs", "/etc/kubernetes/pki")))
    return [{"name": name,
             "hostPath": {"type": "DirectoryOrCreate", "path": path}}
            for name, path in sorted(pairs, key=lambda pair: pair[0])]


def _probes(ip):
    return {
        "livenessProbe": {"failureThreshold": 8,
            "httpGet": {"host": ip, "path": "/livez", "port": "probe-port", "scheme": "HTTPS"},
            "initialDelaySeconds": 10, "periodSeconds": 10, "timeoutSeconds": 15},
        "readinessProbe": {"failureThreshold": 3,
            "httpGet": {"host": ip, "path": "/readyz", "port": "probe-port", "scheme": "HTTPS"},
            "periodSeconds": 1, "timeoutSeconds": 15},
        "startupProbe": {"failureThreshold": 24,
            "httpGet": {"host": ip, "path": "/livez", "port": "probe-port", "scheme": "HTTPS"},
            "initialDelaySeconds": 10, "periodSeconds": 10, "timeoutSeconds": 15},
    }


def disk_pod(selected=(), ip=DEFAULT_IP):
    container = {
        "command": command(ip),
        "image": "registry.k8s.io/kube-apiserver:v1.36.1",
        "imagePullPolicy": "IfNotPresent",
        **_probes(ip),
        "name": "kube-apiserver",
        "ports": [{"containerPort": 6443, "name": "probe-port", "protocol": "TCP"}],
        "resources": {"requests": {"cpu": "250m"}},
        "volumeMounts": _mounts(selected),
    }
    return {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {
            "annotations": {"kubeadm.kubernetes.io/kube-apiserver.advertise-address.endpoint": f"{ip}:6443"},
            "labels": {"component": "kube-apiserver", "tier": "control-plane"},
            "name": "kube-apiserver", "namespace": "kube-system",
        },
        "spec": {"containers": [container], "hostNetwork": True, "priority": 2000001000,
            "priorityClassName": "system-node-critical",
            "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
            "volumes": _volumes(selected)},
    }


def api_spec(selected=(), ip=DEFAULT_IP):
    # Deliberately independent of disk_pod: this is the reviewed API fixture.
    container = {
        "name": "kube-apiserver", "image": "registry.k8s.io/kube-apiserver:v1.36.1",
        "imagePullPolicy": "IfNotPresent", "command": command(ip),
        "resources": {"requests": {"cpu": "250m"}},
        "volumeMounts": _api_mounts(selected),
        "ports": [{"name": "probe-port", "containerPort": 6443,
                   "hostPort": 6443, "protocol": "TCP"}],
        **_probes(ip),
    }
    return {
        "nodeName": NODE, "hostNetwork": True,
        "priorityClassName": "system-node-critical", "priority": 2000001000,
        "preemptionPolicy": "PreemptLowerPriority",
        "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
        "tolerations": [{"operator": "Exists", "effect": "NoExecute"}],
        "volumes": _api_volumes(selected), "containers": [container],
    }


def row(document, kind, name):
    return next(item for item in document["items"]
                if item["kind"] == kind and item["metadata"]["name"] == name)


def literal_source_fixture(selected=(), ip=DEFAULT_IP, document=None):
    manifest = disk_pod(selected, ip) if document is None else document
    owned = source_identity()
    return validate_control_plane_manifest_source(
        context=source_context(owned), owned_identity=owned,
        observations=source_observations(owned, apiserver=yaml_bytes(manifest)))


def api_document(selected=(), ip=DEFAULT_IP,
                 owned_identity=MATCHED_OWNERSHIP_IDENTITY):
    args = ownership_fixture(owned_identity=owned_identity)
    document = json.loads(args["runtime_objects"])
    node = row(document, "Node", NODE)
    node["status"] = {"addresses": [
        {"type": "InternalIP", "address": ip},
        {"type": "Hostname", "address": NODE},
    ]}
    observed = row(document, "Pod", POD_NAME)
    observed["metadata"].update(
        generation=1, creationTimestamp="2026-09-15T01:00:00Z",
        labels={"component": "kube-apiserver", "tier": "control-plane"},
    )
    observed["metadata"]["annotations"].update(**{
        "kubernetes.io/config.seen": "2026-09-15T01:00:00.123456789Z",
        "kubeadm.kubernetes.io/kube-apiserver.advertise-address.endpoint": f"{ip}:6443",
    })
    observed["spec"] = api_spec(selected, ip)
    return args, document


def literal_runtime_fixture(selected=(), ip=DEFAULT_IP, document=None,
                            owned_identity=MATCHED_OWNERSHIP_IDENTITY):
    args, default = api_document(selected, ip, owned_identity)
    args["runtime_objects"] = encode(default if document is None else document)
    return validate_runtime_ownership(**args)


class KubeAPIServerMirrorConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE),
                             "kube-apiserver mirror configuration adapter is missing")
        self.module = importlib.import_module(MODULE)

    def validate(self, selected=(), ip=DEFAULT_IP, *, disk=None, api=None):
        return self.module.validate_kube_apiserver_mirror_configuration(
            ownership=literal_runtime_fixture(selected, ip, api),
            source=literal_source_fixture(selected, ip, disk))

    def reject_disk(self, path, value, selected=()):
        document = disk_pod(selected)
        target = document
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with self.assertRaises(self.module.KubeAPIServerMirrorConfigurationError):
            self.validate(selected, disk=document)

    def reject_api(self, path, value, selected=()):
        _args, document = api_document(selected)
        target = row(document, "Pod", POD_NAME)
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with self.assertRaises(self.module.KubeAPIServerMirrorConfigurationError):
            self.validate(selected, api=document)

    def test_all_32_disk_and_api_subsets_are_accepted_in_exact_order(self):
        for mask in range(32):
            selected = tuple(pair for bit, pair in enumerate(CA_CANDIDATES)
                             if mask & (1 << bit))
            with self.subTest(mask=mask):
                proof = self.validate(selected)
                self.assertEqual(proof.bindings[0].conditional_volume_names,
                                 tuple(name for name, _path in selected))
                expected_names = tuple(sorted(("ca-certs", "k8s-certs",
                                               *(name for name, _path in selected))))
                self.assertEqual(tuple(volume["name"] for volume in
                    disk_pod(selected)["spec"]["volumes"]), expected_names)
                self.assertEqual(tuple(mount["name"] for mount in
                    disk_pod(selected)["spec"]["containers"][0]["volumeMounts"]),
                    expected_names)

    def test_all_32_api_subsets_that_differ_from_disk_are_rejected(self):
        for mask in range(32):
            selected = tuple(pair for bit, pair in enumerate(CA_CANDIDATES)
                             if mask & (1 << bit))
            other_mask = mask ^ 1
            api_selected = tuple(pair for bit, pair in enumerate(CA_CANDIDATES)
                                 if other_mask & (1 << bit))
            _args, document = api_document(api_selected)
            with self.subTest(mask=mask), self.assertRaises(
                    self.module.KubeAPIServerMirrorConfigurationError):
                self.validate(selected, api=document)

    def test_unconditional_mounts_and_conditional_pair_shape_fail_closed(self):
        selected = CA_CANDIDATES
        disk_cases = [
            (("spec", "volumes", 0, "hostPath", "path"), "/foreign"),
            (("spec", "volumes", 0, "hostPath", "type"), "Directory"),
            (("spec", "containers", 0, "volumeMounts", 0, "readOnly"), False),
            (("spec", "containers", 0, "volumeMounts", 0, "mountPath"), "/foreign"),
            (("spec", "volumes", 1, "hostPath", "path"), "/wrong-candidate"),
            (("spec", "volumes", 1, "hostPath", "type"), "Directory"),
            (("spec", "containers", 0, "volumeMounts", 1, "readOnly"), False),
            (("spec", "containers", 0, "volumeMounts", 1, "mountPath"), "/wrong-candidate"),
        ]
        for path, value in disk_cases:
            with self.subTest(path=path):
                self.reject_disk(path, value, selected)
        for family, index in (("volumes", 2), ("mounts", 2)):
            document = disk_pod(selected)
            collection = (document["spec"]["volumes"] if family == "volumes" else
                          document["spec"]["containers"][0]["volumeMounts"])
            collection.pop(index)
            with self.subTest(family=family), self.assertRaises(
                    self.module.KubeAPIServerMirrorConfigurationError):
                self.validate(selected, disk=document)
        mutations = ("duplicate", "renamed", "unexpected", "reordered")
        for mutation in mutations:
            document = disk_pod(selected)
            volumes = document["spec"]["volumes"]
            mounts = document["spec"]["containers"][0]["volumeMounts"]
            if mutation == "duplicate":
                volumes.insert(2, deepcopy(volumes[1])); mounts.insert(2, deepcopy(mounts[1]))
            elif mutation == "renamed":
                volumes[1]["name"] = "renamed"; mounts[1]["name"] = "renamed"
            elif mutation == "unexpected":
                volumes.append({"name": "foreign", "hostPath": {"path": "/foreign", "type": "DirectoryOrCreate"}})
                mounts.append({"name": "foreign", "mountPath": "/foreign", "readOnly": True})
            else:
                volumes[1], volumes[2] = volumes[2], volumes[1]
                mounts[1], mounts[2] = mounts[2], mounts[1]
            with self.subTest(mutation=mutation), self.assertRaises(
                    self.module.KubeAPIServerMirrorConfigurationError):
                self.validate(selected, disk=document)

    def test_fixed_disk_pod_and_container_fields_are_closed(self):
        cases = [
            (("metadata", "name"), "foreign"), (("metadata", "namespace"), "default"),
            (("metadata", "labels", "tier"), "foreign"),
            (("metadata", "annotations", "foreign"), "x"),
            (("spec", "hostNetwork"), 1), (("spec", "priority"), True),
            (("spec", "priorityClassName"), "foreign"),
            (("spec", "securityContext", "seccompProfile", "type"), "Unconfined"),
            (("spec", "containers", 0, "image"), "foreign"),
            (("spec", "containers", 0, "imagePullPolicy"), "Always"),
            (("spec", "containers", 0, "resources", "requests", "cpu"), "1"),
            (("spec", "containers", 0, "ports", 0, "containerPort"), 1),
            (("spec", "containers", 0, "ports", 0, "protocol"), "UDP"),
            (("spec", "containers", 0, "command", 2), "--allow-privileged=false"),
            (("spec", "containers", 0, "livenessProbe", "httpGet", "path"), "/healthz"),
            (("spec", "containers", 0, "readinessProbe", "periodSeconds"), 10),
            (("spec", "containers", 0, "startupProbe", "failureThreshold"), 23),
        ]
        for path, value in cases:
            with self.subTest(path=path):
                self.reject_disk(path, value, CA_CANDIDATES[:2])

    def test_owned_node_internal_ip_binds_disk_and_api_dynamic_fields(self):
        self.validate(CA_CANDIDATES[:1], "10.20.30.40")
        for value in (None, True, 1, "0172.18.0.2", "127.0.0.1", "0.0.0.0",
                      "169.254.1.1", "224.0.0.1", "240.0.0.1", "::1"):
            _args, document = api_document()
            row(document, "Node", NODE)["status"]["addresses"][0]["address"] = value
            with self.subTest(value=value), self.assertRaises(
                    self.module.KubeAPIServerMirrorConfigurationError):
                self.validate(api=document)
        malformed = (
            [{"type": "Hostname", "address": NODE},
             {"type": "InternalIP", "address": DEFAULT_IP}],
            [{"type": "ExternalIP", "address": DEFAULT_IP},
             {"type": "Hostname", "address": NODE}],
            [{"type": "InternalIP", "address": DEFAULT_IP},
             {"type": "Hostname", "address": "foreign"}],
            [{"type": "InternalIP", "address": DEFAULT_IP},
             {"type": "Hostname", "address": NODE},
             {"type": "ExternalIP", "address": "1.1.1.1"}],
            [{"type": "InternalIP", "address": DEFAULT_IP, "extra": 1},
             {"type": "Hostname", "address": NODE}],
        )
        for addresses in malformed:
            _args, document = api_document()
            row(document, "Node", NODE)["status"]["addresses"] = addresses
            with self.subTest(addresses=addresses), self.assertRaises(
                    self.module.KubeAPIServerMirrorConfigurationError):
                self.validate(api=document)
        disk = disk_pod((), "10.20.30.40")
        with self.assertRaises(self.module.KubeAPIServerMirrorConfigurationError):
            self.validate((), DEFAULT_IP, disk=disk)
        _args, api = api_document((), "10.20.30.40")
        with self.assertRaises(self.module.KubeAPIServerMirrorConfigurationError):
            self.validate((), DEFAULT_IP, api=api)

    def test_api_metadata_defaults_status_and_spec_drift(self):
        _args, document = api_document(CA_CANDIDATES[:2])
        row(document, "Pod", POD_NAME)["status"] = {"phase": "Failed", "arbitrary": [False, 7]}
        proof = self.validate(CA_CANDIDATES[:2], api=document)
        self.assertEqual(proof.ownership.runtime_objects, encode(document))
        defaulted = deepcopy(document)
        spec = row(defaulted, "Pod", POD_NAME)["spec"]
        spec.update(dnsPolicy="ClusterFirst", restartPolicy="Always",
                    terminationGracePeriodSeconds=30, schedulerName="default-scheduler",
                    enableServiceLinks=True)
        container = spec["containers"][0]
        container.update(terminationMessagePath="/dev/termination-log",
                         terminationMessagePolicy="File")
        for name in ("livenessProbe", "readinessProbe", "startupProbe"):
            container[name]["successThreshold"] = 1
        self.validate(CA_CANDIDATES[:2], api=defaulted)
        cases = [
            (("metadata", "generation"), 2), (("metadata", "creationTimestamp"), "bad"),
            (("metadata", "labels", "tier"), "foreign"),
            (("metadata", "annotations", "foreign"), "x"),
            (("spec", "preemptionPolicy"), "Never"),
            (("spec", "tolerations"), []),
            (("spec", "containers", 0, "ports", 0, "hostPort"), 1),
        ]
        for path, value in cases:
            with self.subTest(path=path):
                self.reject_api(path, value, CA_CANDIDATES[:2])
        for value in (None, 1, "2026-09-15T01:00:00Z",
                      "2026-09-15T01:00:00.1234567890Z",
                      "2025-02-29T01:00:00.123456789Z",
                      "2026-09-15T24:00:00.123456789Z",
                      "2026-09-15T01:00:00.123456789+00:00"):
            with self.subTest(seen=value):
                self.reject_api(("metadata", "annotations",
                                 "kubernetes.io/config.seen"), value,
                                CA_CANDIDATES[:2])

    def test_api_factory_is_fresh_and_source_authenticated(self):
        source = literal_source_fixture(CA_CANDIDATES[::2])
        expected = self.module.kube_apiserver_mirror_api_spec(
            source=source, node_internal_ip=DEFAULT_IP)
        self.assertEqual(expected, api_spec(CA_CANDIDATES[::2]))
        expected["containers"][0]["command"].clear()
        self.assertEqual(self.module.kube_apiserver_mirror_api_spec(
            source=source, node_internal_ip=DEFAULT_IP), api_spec(CA_CANDIDATES[::2]))

    def test_coordinated_retained_proof_tampering_is_reconstructed(self):
        proof = self.validate(CA_CANDIDATES[:1])
        source = deepcopy(proof.source)
        object.__setattr__(source, "bindings", source.bindings[::-1])
        with self.assertRaises(self.module.KubeAPIServerMirrorConfigurationError):
            replace(proof, source=source)
        ownership = deepcopy(proof.ownership)
        _args, document = api_document(CA_CANDIDATES[:1])
        candidate = row(document, "Pod", POD_NAME)
        candidate["metadata"]["annotations"]["kubernetes.io/config.hash"] = "f" * 32
        candidate["metadata"]["annotations"]["kubernetes.io/config.mirror"] = "f" * 32
        object.__setattr__(ownership, "runtime_objects", encode(document))
        with self.assertRaises(self.module.KubeAPIServerMirrorConfigurationError):
            replace(proof, ownership=ownership)
        for path, value in (
                (("metadata", "ownerReferences", 0, "controller"), 1),
                (("metadata", "ownerReferences", 0, "blockOwnerDeletion"), True),
                (("spec", "nodeName"), "foreign")):
            ownership = deepcopy(proof.ownership)
            _args, document = api_document(CA_CANDIDATES[:1])
            target = row(document, "Pod", POD_NAME)
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            object.__setattr__(ownership, "runtime_objects", encode(document))
            with self.subTest(path=path), self.assertRaises(
                    self.module.KubeAPIServerMirrorConfigurationError):
                replace(proof, ownership=ownership)

    def test_cross_proof_cluster_incarnation_mismatch_is_rejected(self):
        ownership = literal_runtime_fixture(owned_identity=replace(
            MATCHED_OWNERSHIP_IDENTITY,
            cluster_incarnation_uid="5b9f7ce2-9876-4f55-9a23-a9f00fbbde11",
        ))
        source = literal_source_fixture()
        ownership.__post_init__(); source.__post_init__()
        self.assertNotEqual(source.cluster_uid,
                            ownership.owned_identity.cluster_incarnation_uid)
        with self.assertRaises(self.module.KubeAPIServerMirrorConfigurationError):
            self.module.validate_kube_apiserver_mirror_configuration(
                ownership=ownership, source=source)

    def test_cross_proof_node_container_mismatch_is_rejected(self):
        ownership = literal_runtime_fixture(owned_identity=replace(
            MATCHED_OWNERSHIP_IDENTITY, node_container_id="b" * 64,
        ))
        source = literal_source_fixture()
        ownership.__post_init__(); source.__post_init__()
        self.assertNotEqual(source.node_container_id,
                            ownership.owned_identity.node_container_id)
        with self.assertRaises(self.module.KubeAPIServerMirrorConfigurationError):
            self.module.validate_kube_apiserver_mirror_configuration(
                ownership=ownership, source=source)

    def test_constructors_exact_dependencies_bindings_and_false_flags(self):
        proof = self.validate(CA_CANDIDATES[:2])
        self.assertEqual(replace(proof), proof)
        self.assertFalse(proof.runtime_contract_complete)
        self.assertFalse(proof.full_application_contract_complete)
        for flag in ("runtime_contract_complete", "full_application_contract_complete"):
            for value in (True, 0, None):
                with self.subTest(flag=flag, value=value), self.assertRaises(
                        self.module.KubeAPIServerMirrorConfigurationError):
                    replace(proof, **{flag: value})
        binding = proof.bindings[0]
        for field, value in (
                ("namespace", "default"), ("pod_name", "foreign"),
                ("pod_uid", None), ("pod_resource_version", True),
                ("config_hash", "x"), ("node_internal_ip", True),
                ("conditional_volume_names", list(binding.conditional_volume_names))):
            with self.subTest(field=field), self.assertRaises(
                    self.module.KubeAPIServerMirrorConfigurationError):
                replace(binding, **{field: value})
        for field, value in (
                ("pod_uid", "foreign"), ("pod_resource_version", "999"),
                ("config_hash", "f" * 32), ("node_internal_ip", "10.20.30.40"),
                ("conditional_volume_names", ())):
            forged = replace(binding, **{field: value})
            with self.subTest(field=field), self.assertRaises(
                    self.module.KubeAPIServerMirrorConfigurationError):
                replace(proof, bindings=(forged,))
        class SubBinding(type(binding)):
            pass
        subclass = SubBinding(**{name: getattr(binding, name)
            for name in binding.__dataclass_fields__})
        for value in ([], (), (subclass,), proof.bindings * 2):
            with self.assertRaises(self.module.KubeAPIServerMirrorConfigurationError):
                replace(proof, bindings=value)
        for field in ("ownership", "source"):
            dependency = getattr(proof, field)
            subclass_type = type("Subclass", (type(dependency),), {})
            forged = subclass_type(**{name: getattr(dependency, name)
                for name in dependency.__dataclass_fields__})
            for value in (None, forged):
                with self.subTest(field=field), self.assertRaises(
                        self.module.KubeAPIServerMirrorConfigurationError):
                    replace(proof, **{field: value})


if __name__ == "__main__":
    unittest.main()
