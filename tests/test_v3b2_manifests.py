from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
import json
from pathlib import Path
import unittest

from kil.canonical import canonical_json
from kil.v3b2_contracts import TRACK_NAMESPACES, V3B2Profile
from kil.v3b2_manifests import (
    ManifestError,
    PolicyEdge,
    WorkloadIdentity,
    expected_object_keys,
    expected_policy_graph,
    render_kind_config,
    render_objects,
    validate_rendered_objects,
)


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "v3b2-" + "1" * 64
KIL_IMAGE_ID = "sha256:" + "2" * 64
ENVOY_IMAGE = "docker.io/envoyproxy/envoy@sha256:" + "3" * 64
LABELS = {"kil.dev/managed": "v3b2"}
ROLE_NAMES = ("driver", "envoy", "authz", "target")
POLICY_NAMES = (
    "default-deny",
    "allow-dns",
    "allow-driver-egress-envoy",
    "allow-envoy-ingress-egress",
    "allow-backends-ingress-envoy",
)


class StringSubclass(str):
    pass


class TupleSubclass(tuple):
    pass


def profile() -> V3B2Profile:
    return V3B2Profile.load(ROOT / "deploy/kind/v3b2-profile.json")


def workload() -> WorkloadIdentity:
    return WorkloadIdentity(RUN_ID, KIL_IMAGE_ID, ENVOY_IMAGE)


def decoded() -> dict[str, object]:
    return json.loads(render_objects(profile(), workload()))


def items_by_namespace(value: dict[str, object], namespace: str) -> list[dict]:
    return [
        item
        for item in value["items"]
        if item["metadata"].get("namespace", item["metadata"]["name"]) == namespace
    ]


def object_named(value: dict[str, object], namespace: str, kind: str, name: str) -> dict:
    matches = [
        item
        for item in value["items"]
        if item["kind"] == kind
        and item["metadata"]["name"] == name
        and item["metadata"].get("namespace", name) == namespace
    ]
    if len(matches) != 1:
        raise AssertionError((namespace, kind, name, len(matches)))
    return matches[0]


class V3B2ManifestTest(unittest.TestCase):
    def test_kind_config_is_exact_closed_and_deterministic(self) -> None:
        expected = {
            "apiVersion": "kind.x-k8s.io/v1alpha4",
            "kind": "Cluster",
            "networking": {
                "disableDefaultCNI": True,
                "podSubnet": "10.244.0.0/16",
                "serviceSubnet": "10.96.0.0/16",
            },
            "nodes": [{"role": "control-plane"}],
        }
        rendered = render_kind_config(profile())
        self.assertEqual(rendered, (canonical_json(expected) + "\n").encode())
        self.assertEqual(rendered, render_kind_config(profile()))
        text = rendered.decode()
        for forbidden in (
            "extraPortMappings", "extraMounts", "hostPath", "apiServerAddress",
            "apiServerPort",
        ):
            self.assertNotIn(forbidden, text)

    def test_renderers_reject_wrong_or_mutated_profile(self) -> None:
        for invalid in (None, object(), {}):
            with self.subTest(invalid=type(invalid).__name__):
                with self.assertRaises(ManifestError):
                    render_kind_config(invalid)  # type: ignore[arg-type]
        changed = profile()
        object.__setattr__(changed, "pod_subnet", "0.0.0.0/0")
        with self.assertRaises(ManifestError):
            render_kind_config(changed)
        with self.assertRaises(ManifestError):
            render_objects(changed, workload())

    def test_workload_identity_is_exact_typed_closed_and_deeply_immutable(self) -> None:
        identity = workload()
        self.assertEqual(
            tuple(field.name for field in fields(identity)),
            ("run_id", "kil_image_id", "envoy_image_digest"),
        )
        for name in ("run_id", "kil_image_id", "envoy_image_digest"):
            with self.assertRaises((FrozenInstanceError, AttributeError)):
                setattr(identity, name, "changed")
        with self.assertRaises((AttributeError, TypeError)):
            identity.extra = "no"  # type: ignore[attr-defined]
        invalid_values = (
            (StringSubclass(RUN_ID), KIL_IMAGE_ID, ENVOY_IMAGE),
            ("v3b2-" + "A" * 64, KIL_IMAGE_ID, ENVOY_IMAGE),
            (RUN_ID, StringSubclass(KIL_IMAGE_ID), ENVOY_IMAGE),
            (RUN_ID, "sha256:" + "g" * 64, ENVOY_IMAGE),
            (RUN_ID, KIL_IMAGE_ID, StringSubclass(ENVOY_IMAGE)),
            (RUN_ID, KIL_IMAGE_ID, "envoy:v1.39.1"),
            (RUN_ID, KIL_IMAGE_ID, "@sha256:" + "3" * 64),
        )
        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(ManifestError):
                    WorkloadIdentity(*values)
        changed = workload()
        object.__setattr__(changed, "run_id", RUN_ID[:-1] + "A")
        with self.assertRaises(ManifestError):
            render_objects(profile(), changed)

    def test_policy_edge_has_narrow_exact_canonical_types(self) -> None:
        edge = PolicyEdge(
            "kil-v3-baseline", ("driver", "envoy"), "kube-system",
            ("kube-dns",), (("TCP", 53), ("UDP", 53)),
        )
        self.assertEqual(
            tuple(field.name for field in fields(edge)),
            ("namespace", "source_roles", "destination_namespace", "destination_roles", "protocol_ports"),
        )
        with self.assertRaises(FrozenInstanceError):
            edge.namespace = "changed"  # type: ignore[misc]
        invalid = (
            (StringSubclass("kil-v3-baseline"), ("driver",), "kil-v3-baseline", ("envoy",), (("TCP", 8080),)),
            ("kil-v3-baseline", TupleSubclass(("driver",)), "kil-v3-baseline", ("envoy",), (("TCP", 8080),)),
            ("kil-v3-baseline", ("envoy", "driver"), "kube-system", ("kube-dns",), (("TCP", 53), ("UDP", 53))),
            ("kil-v3-baseline", ("driver",), "kil-v3-baseline", ("envoy",), (("UDP", 53), ("TCP", 53))),
            ("kil-v3-baseline", ("driver", "driver"), "kil-v3-baseline", ("envoy",), (("TCP", 8080),)),
        )
        for args in invalid:
            with self.subTest(args=args):
                with self.assertRaises(ManifestError):
                    PolicyEdge(*args)

    def test_canonical_list_has_exact_sixty_keys_in_reviewed_order(self) -> None:
        payload = render_objects(profile(), workload())
        self.assertTrue(payload.endswith(b"\n"))
        self.assertFalse(payload.endswith(b"\n\n"))
        self.assertEqual(payload, render_objects(profile(), workload()))
        value = json.loads(payload)
        self.assertEqual(payload, (canonical_json(value) + "\n").encode())
        self.assertEqual((value["apiVersion"], value["kind"]), ("v1", "List"))
        self.assertEqual(len(value["items"]), 60)
        actual_keys = tuple(
            (item["apiVersion"], item["kind"], item["metadata"].get("namespace", ""), item["metadata"]["name"])
            for item in value["items"]
        )
        self.assertEqual(actual_keys, expected_object_keys(profile()))

    def test_run_annotation_and_cluster_scoped_key_representation_are_fixed(self) -> None:
        value = decoded()
        self.assertEqual(
            expected_object_keys(profile())[0],
            ("v1", "Namespace", "", "kil-v3-baseline"),
        )
        for item in value["items"]:
            self.assertEqual(item["metadata"]["annotations"], {"kil.dev/run-id": RUN_ID})
            if item["kind"] == "Deployment":
                self.assertEqual(
                    item["spec"]["template"]["metadata"]["annotations"],
                    {"kil.dev/run-id": RUN_ID},
                )

    def test_each_namespace_has_independent_exact_inventory(self) -> None:
        expected = (
            (("Namespace",), ("kil-v3-baseline",)),
            (("ServiceAccount",) * 4, ROLE_NAMES),
            (("ConfigMap",) * 3, ("authz-config", "target-config", "envoy-config")),
            (("NetworkPolicy",) * 5, POLICY_NAMES),
            (("Service",) * 3, ("envoy", "authz", "target")),
            (("Deployment",) * 3, ("envoy", "authz", "target")),
            (("Pod",), ("driver",)),
        )
        value = decoded()
        for _, namespace in TRACK_NAMESPACES:
            objects = items_by_namespace(value, namespace)
            self.assertEqual(len(objects), 20)
            actual = tuple((item["kind"], item["metadata"]["name"]) for item in objects)
            flattened = tuple(
                (kind, name)
                for (kinds, names) in expected
                for kind, name in zip(kinds, names, strict=True)
            )
            expected_ns = (("Namespace", namespace),) + flattened[1:]
            self.assertEqual(actual, expected_ns)

    def test_all_policies_precede_all_application_workloads_per_namespace(self) -> None:
        value = decoded()
        for _, namespace in TRACK_NAMESPACES:
            kinds = [item["kind"] for item in items_by_namespace(value, namespace)]
            last_policy = max(i for i, kind in enumerate(kinds) if kind == "NetworkPolicy")
            first_workload = min(i for i, kind in enumerate(kinds) if kind in {"Deployment", "Pod"})
            self.assertLess(last_policy, first_workload)

    def test_expected_policy_graph_is_an_independent_exact_oracle(self) -> None:
        expected = []
        for _, namespace in TRACK_NAMESPACES:
            expected.extend(
                (
                    PolicyEdge(namespace, ("driver",), namespace, ("envoy",), (("TCP", 8080),)),
                    PolicyEdge(namespace, ("envoy",), namespace, ("authz",), (("TCP", 8080),)),
                    PolicyEdge(namespace, ("envoy",), namespace, ("target",), (("TCP", 8080),)),
                    PolicyEdge(namespace, ("driver", "envoy"), "kube-system", ("kube-dns",), (("TCP", 53), ("UDP", 53))),
                )
            )
        self.assertEqual(expected_policy_graph(profile()), tuple(expected))

    def test_policies_have_exact_and_peer_semantics_and_no_extra_edges(self) -> None:
        value = decoded()
        for track, namespace in TRACK_NAMESPACES:
            policies = {
                item["metadata"]["name"]: item
                for item in items_by_namespace(value, namespace)
                if item["kind"] == "NetworkPolicy"
            }
            self.assertEqual(tuple(policies), POLICY_NAMES)
            default = policies["default-deny"]["spec"]
            self.assertEqual(default, {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]})
            for name, policy in policies.items():
                selector = policy["spec"]["podSelector"]
                if name != "default-deny":
                    self.assertNotEqual(selector, {})
                self.assertNotIn("ipBlock", json.dumps(policy))
                self.assertNotIn("SCTP", json.dumps(policy))
            dns = policies["allow-dns"]["spec"]
            self.assertEqual(dns["policyTypes"], ["Egress"])
            self.assertEqual(dns["podSelector"]["matchLabels"], {**LABELS, "kil.dev/track": track})
            self.assertEqual(dns["podSelector"]["matchExpressions"], [{"key": "kil.dev/role", "operator": "In", "values": ["driver", "envoy"]}])
            peer = dns["egress"][0]["to"]
            self.assertEqual(len(peer), 1)
            self.assertEqual(set(peer[0]), {"namespaceSelector", "podSelector"})
            self.assertEqual(peer[0]["namespaceSelector"], {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}})
            self.assertEqual(peer[0]["podSelector"], {"matchLabels": {"k8s-app": "kube-dns"}})
            self.assertEqual(dns["egress"][0]["ports"], [{"port": 53, "protocol": "TCP"}, {"port": 53, "protocol": "UDP"}])

            driver = policies["allow-driver-egress-envoy"]["spec"]
            envoy = policies["allow-envoy-ingress-egress"]["spec"]
            backends = policies["allow-backends-ingress-envoy"]["spec"]
            self.assertEqual(driver["policyTypes"], ["Egress"])
            self.assertEqual(envoy["policyTypes"], ["Ingress", "Egress"])
            self.assertEqual(backends["policyTypes"], ["Ingress"])
            self.assertNotIn("egress", backends)
            app_rules = [driver["egress"][0], envoy["ingress"][0], *envoy["egress"], backends["ingress"][0]]
            self.assertEqual(len(app_rules), 5)
            for rule in app_rules:
                peers = rule.get("to", rule.get("from"))
                self.assertEqual(len(peers), 1)
                self.assertEqual(set(peers[0]), {"namespaceSelector", "podSelector"})
                self.assertEqual(rule["ports"], [{"port": 8080, "protocol": "TCP"}])

    def test_labels_services_workloads_and_security_are_closed(self) -> None:
        value = decoded()
        expected_resources = {
            "requests": {"cpu": "100m", "memory": "64Mi", "ephemeral-storage": "16Mi"},
            "limits": {"cpu": "500m", "memory": "256Mi", "ephemeral-storage": "64Mi"},
        }
        derived_image = "kil.local/kil-v3b2:sha256-" + "2" * 64
        for track, namespace in TRACK_NAMESPACES:
            ns = object_named(value, namespace, "Namespace", namespace)
            self.assertEqual(ns["metadata"]["labels"], {**LABELS, "kil.dev/track": track})
            for role in ROLE_NAMES:
                sa = object_named(value, namespace, "ServiceAccount", role)
                self.assertEqual(sa["metadata"]["labels"], {**LABELS, "kil.dev/track": track, "kil.dev/role": role})
            for role in ("envoy", "authz", "target"):
                service = object_named(value, namespace, "Service", role)
                self.assertEqual(service["spec"], {
                    "type": "ClusterIP", "selector": {**LABELS, "kil.dev/track": track, "kil.dev/role": role},
                    "ports": [{"name": "http", "port": 8080, "protocol": "TCP", "targetPort": 8080}],
                })
            for role in ("envoy", "authz", "target", "driver"):
                obj = object_named(value, namespace, "Pod" if role == "driver" else "Deployment", role)
                pod = obj["spec"] if role == "driver" else obj["spec"]["template"]["spec"]
                labels = obj["metadata"]["labels"] if role == "driver" else obj["spec"]["template"]["metadata"]["labels"]
                exact_labels = {**LABELS, "kil.dev/track": track, "kil.dev/role": role}
                self.assertEqual(labels, exact_labels)
                if role != "driver":
                    self.assertEqual(obj["spec"]["replicas"], 1)
                    self.assertEqual(obj["spec"]["strategy"], {"type": "Recreate"})
                    self.assertEqual(obj["spec"]["selector"], {"matchLabels": exact_labels})
                self.assertEqual(pod["serviceAccountName"], role)
                self.assertIs(pod["automountServiceAccountToken"], False)
                self.assertIs(pod["enableServiceLinks"], False)
                self.assertEqual(pod["restartPolicy"], "Never" if role == "driver" else "Always")
                for forbidden in ("hostNetwork", "hostPID", "hostIPC"):
                    self.assertNotIn(forbidden, pod)
                self.assertEqual(pod["securityContext"], {"runAsNonRoot": True, "runAsUser": 65532, "runAsGroup": 65532, "fsGroup": 65532, "seccompProfile": {"type": "RuntimeDefault"}})
                container = pod["containers"][0]
                self.assertEqual(container["image"], ENVOY_IMAGE if role == "envoy" else derived_image)
                self.assertEqual(container["imagePullPolicy"], "Never")
                self.assertEqual(container["resources"], expected_resources)
                self.assertEqual(container["securityContext"], {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "runAsNonRoot": True, "runAsUser": 65532, "runAsGroup": 65532, "capabilities": {"drop": ["ALL"]}})
                for port in container.get("ports", []):
                    self.assertEqual(port, {"containerPort": 8080, "name": "http", "protocol": "TCP"})
                    self.assertNotIn("hostPort", port)
                for volume in pod["volumes"]:
                    self.assertNotIn("hostPath", volume)
                    if "emptyDir" in volume:
                        self.assertEqual(volume["emptyDir"], {"sizeLimit": "16Mi"})
                config_mounts = [mount for mount in container["volumeMounts"] if mount["name"] == "config"]
                if config_mounts:
                    self.assertIs(config_mounts[0]["readOnly"], True)

    def test_strict_service_configs_are_readonly_file_mounts(self) -> None:
        # Whole ConfigMap directory projection exposes symlinks. Both fixed
        # application loaders require a readonly regular file instead.
        value = decoded()
        for _, namespace in TRACK_NAMESPACES:
            for role in ('authz', 'target'):
                pod = object_named(value, namespace, 'Deployment', role)['spec']['template']['spec']
                container = pod['containers'][0]
                mount = [row for row in container['volumeMounts'] if row['name'] == 'config']
                self.assertEqual(mount, [{'name': 'config', 'mountPath': '/config/' + role + '.json',
                                         'subPath': role + '.json', 'readOnly': True}])
                volume = [row for row in pod['volumes'] if row['name'] == 'config']
                self.assertEqual(volume, [{'name': 'config', 'configMap':
                    {'name': role + '-config', 'defaultMode': 292}}])
                self.assertTrue(container['securityContext']['readOnlyRootFilesystem'])
            envoy = object_named(value, namespace, 'Deployment', 'envoy')['spec']['template']['spec']['containers'][0]
            self.assertEqual([row for row in envoy['volumeMounts'] if row['name'] == 'config'],
                             [{'name': 'config', 'mountPath': '/config', 'readOnly': True}])

    def test_driver_has_exact_retained_stdin_contract(self) -> None:
        value = decoded()
        for _, namespace in TRACK_NAMESPACES:
            container = object_named(value, namespace, "Pod", "driver")["spec"]["containers"][0]
            self.assertIs(container.get("stdin"), True)
            self.assertIs(container.get("stdinOnce"), True)
            self.assertIs(container.get("tty"), False)

    def test_commands_and_public_configmaps_are_exact_and_safe(self) -> None:
        value = decoded()
        for track, namespace in TRACK_NAMESPACES:
            driver = object_named(value, namespace, "Pod", "driver")["spec"]["containers"][0]
            self.assertEqual(driver["command"], ["python", "-m", "kil.v3b1_request_driver", "--track", track, "--endpoint", "envoy:8080"])
            authz = object_named(value, namespace, "Deployment", "authz")["spec"]["template"]["spec"]["containers"][0]
            target = object_named(value, namespace, "Deployment", "target")["spec"]["template"]["spec"]["containers"][0]
            self.assertIn("set -C", authz["command"][2])
            self.assertIn(": > /evidence/decisions.jsonl", authz["command"][2])
            self.assertIn("python -m kil.ext_authz_http --config /config/authz.json", authz["command"][2])
            self.assertIn("set -C", target["command"][2])
            self.assertIn(": > /evidence/targets.jsonl", target["command"][2])
            self.assertIn("python -m kil.target_http --config /config/target.json", target["command"][2])
            maps = {name: object_named(value, namespace, "ConfigMap", name) for name in ("authz-config", "target-config", "envoy-config")}
            target_config = json.loads(maps["target-config"]["data"]["target.json"])
            self.assertEqual(target_config, {"schema_version": "kil.v3b-target-http.v1", "run_id": RUN_ID, "track": track, "bind_host": "0.0.0.0", "bind_port": 8080, "ledger_path": "/evidence/targets.jsonl"})
            authz_config = json.loads(maps["authz-config"]["data"]["authz.json"])
            self.assertEqual(authz_config["track"], track)
            self.assertEqual(authz_config["bind_host"], "0.0.0.0")
            self.assertEqual(authz_config["bind_port"], 8080)
            self.assertEqual(authz_config["records_path"], "/evidence/decisions.jsonl")
            self.assertEqual(authz_config["fixtures"][0]["request_id"], "v3b1-central-request")
            self.assertEqual(
                authz_config["fixtures"][0]["expected_authorization_sha256"],
                "6439999a7bf4ce84849af7b26150003ef0ee42642fe46921805929a0d68dcdb7",
            )
            self.assertEqual(
                len(authz_config["public_keys"]),
                0 if track == "credential_policy_baseline" else 1,
            )
            envoy_text = maps["envoy-config"]["data"]["envoy.json"]
            self.assertIn('"address":"authz"', envoy_text)
            self.assertIn('"address":"target"', envoy_text)
            self.assertIn(track, envoy_text)
            for data in (maps["authz-config"]["data"], maps["target-config"]["data"], maps["envoy-config"]["data"]):
                self.assertTrue(all(type(entry) is str for entry in data.values()))
                self.assertTrue(all(entry.endswith("\n") for entry in data.values()))
                lowered = " ".join(data.values()).lower()
                for forbidden in ("private_key", "execution_nonce", "q_state_jws", "bearer v3b-lab-credential", "hostpath"):
                    self.assertNotIn(forbidden, lowered)
        self.assertNotIn('"kind":"Secret"', render_objects(profile(), workload()).decode())

    def test_validator_accepts_bytes_and_exact_decoded_structure(self) -> None:
        payload = render_objects(profile(), workload())
        self.assertIsNone(validate_rendered_objects(payload, profile(), workload()))
        self.assertIsNone(validate_rendered_objects(json.loads(payload), profile(), workload()))
        for invalid in ("not bytes", bytearray(payload), [], None):
            with self.subTest(invalid=type(invalid).__name__):
                with self.assertRaises(ManifestError):
                    validate_rendered_objects(invalid, profile(), workload())

    def test_validator_rejects_json_equality_type_bypasses(self) -> None:
        value = decoded()
        object_named(value, "kil-v3-baseline", "Deployment", "envoy")["spec"]["replicas"] = True
        with self.assertRaises(ManifestError):
            validate_rendered_objects(value, profile(), workload())

    def test_validator_rejects_closed_set_and_security_mutations(self) -> None:
        base = decoded()
        mutations = []
        def mutate(label, fn):
            value = deepcopy(base)
            fn(value)
            mutations.append((label, value))

        service = lambda value: object_named(value, "kil-v3-baseline", "Service", "envoy")
        driver = lambda value: object_named(value, "kil-v3-baseline", "Pod", "driver")
        deployment = lambda value: object_named(value, "kil-v3-baseline", "Deployment", "envoy")
        mutate("nodeport", lambda v: service(v)["spec"].update(type="NodePort", ports=[{"port": 8080, "nodePort": 30080}]))
        for field in ("hostNetwork", "hostPID", "hostIPC", "automountServiceAccountToken"):
            mutate(field, lambda v, field=field: driver(v)["spec"].__setitem__(field, True))
        mutate("privileged", lambda v: driver(v)["spec"]["containers"][0]["securityContext"].update(privileged=True))
        mutate("hostPath", lambda v: driver(v)["spec"]["volumes"].append({"name": "host", "hostPath": {"path": "/"}}))
        mutate("hostPort", lambda v: driver(v)["spec"]["containers"][0].setdefault("ports", []).append({"containerPort": 8080, "hostPort": 8080}))
        for field, value in (("externalIPs", ["1.1.1.1"]), ("externalName", "public.invalid"), ("loadBalancerIP", "1.1.1.1")):
            mutate(field, lambda v, field=field, value=value: service(v)["spec"].__setitem__(field, value))
        mutate("pull policy", lambda v: driver(v)["spec"]["containers"][0].__setitem__("imagePullPolicy", "Always"))
        mutate("image", lambda v: driver(v)["spec"]["containers"][0].__setitem__("image", "kil:latest"))
        mutate("security", lambda v: driver(v)["spec"]["containers"][0]["securityContext"].__setitem__("allowPrivilegeEscalation", True))
        mutate("resources", lambda v: driver(v)["spec"]["containers"][0]["resources"]["limits"].__setitem__("memory", "1Gi"))
        mutate("volume bounds", lambda v: driver(v)["spec"]["volumes"][0]["emptyDir"].__setitem__("sizeLimit", "1Gi"))
        mutate("stdin", lambda v: driver(v)["spec"]["containers"][0].__setitem__("stdin", False))
        mutate("stdinOnce", lambda v: driver(v)["spec"]["containers"][0].__setitem__("stdinOnce", False))
        mutate("tty", lambda v: driver(v)["spec"]["containers"][0].__setitem__("tty", True))
        mutate("missing fsGroup", lambda v: driver(v)["spec"]["securityContext"].pop("fsGroup", None))
        mutate("changed fsGroup", lambda v: driver(v)["spec"]["securityContext"].__setitem__("fsGroup", 0))
        mutate("replicas", lambda v: deployment(v)["spec"].__setitem__("replicas", 2))
        mutate("selector", lambda v: deployment(v)["spec"]["selector"]["matchLabels"].__setitem__("kil.dev/track", "signed_state_only"))
        mutate("cross track", lambda v: driver(v)["metadata"]["labels"].__setitem__("kil.dev/track", "signed_state_only"))
        mutate("missing", lambda v: v["items"].pop())
        mutate("extra", lambda v: v["items"].append(deepcopy(v["items"][-1])))
        mutate("duplicate", lambda v: v["items"].__setitem__(-1, deepcopy(v["items"][0])))
        mutate("secret", lambda v: v["items"].append({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "bad", "namespace": "kil-v3-baseline"}}))
        for label, value in mutations:
            with self.subTest(label=label):
                with self.assertRaises(ManifestError):
                    validate_rendered_objects(value, profile(), workload())

    def test_validator_rejects_policy_selector_and_peer_mutations(self) -> None:
        base = decoded()
        mutations = []
        def mutate(label, name, fn):
            value = deepcopy(base)
            fn(object_named(value, "kil-v3-baseline", "NetworkPolicy", name)["spec"])
            mutations.append((label, value))
        mutate("empty allow selector", "allow-dns", lambda spec: spec.__setitem__("podSelector", {}))
        mutate("separate OR peer", "allow-dns", lambda spec: spec["egress"][0].__setitem__("to", [{"namespaceSelector": spec["egress"][0]["to"][0]["namespaceSelector"]}, {"podSelector": spec["egress"][0]["to"][0]["podSelector"]}]))
        mutate("extra edge", "allow-driver-egress-envoy", lambda spec: spec["egress"].append(deepcopy(spec["egress"][0])))
        mutate("wrong protocol", "allow-driver-egress-envoy", lambda spec: spec["egress"][0]["ports"][0].__setitem__("protocol", "UDP"))
        mutate("cross track peer", "allow-driver-egress-envoy", lambda spec: spec["egress"][0]["to"][0]["namespaceSelector"]["matchLabels"].__setitem__("kil.dev/track", "signed_state_only"))
        for label, value in mutations:
            with self.subTest(label=label):
                with self.assertRaises(ManifestError):
                    validate_rendered_objects(value, profile(), workload())

    def test_validator_identifies_reviewed_adversarial_mutations(self) -> None:
        cases = []

        value = decoded()
        object_named(value, "kil-v3-baseline", "Service", "envoy")["spec"]["type"] = "NodePort"
        cases.append(("ClusterIP", value))

        value = decoded()
        object_named(value, "kil-v3-baseline", "Deployment", "envoy")["spec"]["template"]["spec"]["hostNetwork"] = True
        cases.append(("hostNetwork", value))

        value = decoded()
        object_named(value, "kil-v3-baseline", "Deployment", "envoy")["spec"]["template"]["spec"]["containers"][0]["securityContext"]["privileged"] = True
        cases.append(("privileged", value))

        value = decoded()
        object_named(value, "kil-v3-baseline", "NetworkPolicy", "allow-driver-egress-envoy")["spec"]["podSelector"] = {}
        cases.append(("selector", value))

        for token, value in cases:
            with self.subTest(token=token):
                with self.assertRaisesRegex(ManifestError, token):
                    validate_rendered_objects(value, profile(), workload())


if __name__ == "__main__":
    unittest.main()
