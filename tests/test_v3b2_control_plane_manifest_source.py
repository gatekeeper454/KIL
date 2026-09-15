"""Closed source proof for the two owned control-plane static manifests."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import json
import unittest

from kil.v3b2_control_plane_manifest_source import (
    COMPONENT_PATHS,
    MAX_MANIFEST_BYTES,
    MAX_SOURCE_RECORD_BYTES,
    ControlPlaneManifestBinding,
    ControlPlaneManifestSourceError,
    ControlPlaneManifestSourceProof,
    control_plane_manifest_observation_specs,
    control_plane_manifest_pod,
    control_plane_manifest_read_argv,
    validate_control_plane_manifest_source,
)
from kil.v3b2_journal import Command, JournalError, OwnedIdentity
from kil.v3b2_proofs import ExpectedContext, RawObservation, canonical


NODE_ID = "a" * 64
CONFIG_ID = "sha256:" + "b" * 64
RUN_ID = "c" * 64
CLUSTER_UID = "4b9f7ce2-9876-4f55-9a23-a9f00fbbde11"
KIND_IMAGE = ("kindest/node:v1.36.1@sha256:"
              "3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5")
KUBECONFIG = "/tmp/kil-private/kubeconfig"
ENV = (
    ("DOCKER_CONFIG", "/tmp/kil-private/docker-config"),
    ("DOCKER_HOST", "unix:///tmp/colima/kil-v3-lab/docker.sock"),
)

PATHS = dict(COMPONENT_PATHS)


def manifest(component: str, *, image: str | None = None) -> bytes:
    selected_image = image or "registry.k8s.io/" + component + ":v1.36.1"
    return (
        "apiVersion: v1\n"
        "kind: Pod\n"
        "metadata:\n"
        f"  name: {component}\n"
        "  namespace: kube-system\n"
        "spec:\n"
        "  containers:\n"
        f"  - name: {component}\n"
        f"    image: {selected_image}\n"
    ).encode("utf-8")


def node(*, node_id: str = NODE_ID, config_id: str = CONFIG_ID,
         requested_image: str = KIND_IMAGE, running: bool = True,
         labels: dict[str, str] | None = None) -> bytes:
    if labels is None:
        labels = {
            "io.x-k8s.kind.cluster": "kil-v3-lab",
            "io.x-k8s.kind.role": "control-plane",
        }
    return canonical([{
        "Id": node_id,
        "Name": "/kil-v3-lab-control-plane",
        "Image": config_id,
        "Config": {"Image": requested_image, "Labels": labels},
        "State": {"Running": running},
    }])


def identity(**changes: object) -> OwnedIdentity:
    values = {
        "colima_profile": "kil-v3-lab",
        "docker_host": ENV[1][1],
        "kind_cluster": "kil-v3-lab",
        "kubeconfig": KUBECONFIG,
        "cluster_incarnation_uid": CLUSTER_UID,
        "node_container_id": NODE_ID,
    }
    values.update(changes)
    return OwnedIdentity(**values)  # type: ignore[arg-type]


def context(owned: OwnedIdentity | None = None, **changes: object) -> ExpectedContext:
    retained = owned or identity()
    inputs = {
        "run_id": RUN_ID,
        "kind_node_image": KIND_IMAGE,
        "owned_identity": {
            "colima_profile": retained.colima_profile,
            "docker_host": retained.docker_host,
            "kind_cluster": retained.kind_cluster,
            "kubeconfig": retained.kubeconfig,
            "cluster_incarnation_uid": retained.cluster_incarnation_uid,
            "node_container_id": retained.node_container_id,
        },
    }
    inputs.update(changes)
    return ExpectedContext(RUN_ID, 5, "control_plane_manifest_source",
                           canonical({"kind_cluster": "kil-v3-lab"}), canonical(inputs))


def observations(owned: OwnedIdentity | None = None, *, before: bytes | None = None,
                 apiserver: bytes | None = None, controller: bytes | None = None,
                 after: bytes | None = None) -> tuple[RawObservation, ...]:
    retained = owned or identity()
    specs = control_plane_manifest_observation_specs(retained)
    payloads = (before or node(), apiserver or manifest("kube-apiserver"),
                controller or manifest("kube-controller-manager"), after or node())
    return tuple(RawObservation(spec.label, spec.command.argv, spec.command.env, 0, payload, b"")
                 for spec, payload in zip(specs, payloads, strict=True))


def sized_manifest(size: int) -> bytes:
    prefix = "apiVersion: v1\nkind: Pod\nmetadata:\n"
    suffix = "spec: {}\n"
    fields = 4
    framing = sum(len(f"  pad{index}: \"\"\n") for index in range(fields))
    remaining = size - len(prefix.encode()) - len(suffix.encode()) - framing
    if remaining < 0:
        raise ValueError("size is too small")
    portions = [remaining // fields] * fields
    for index in range(remaining % fields):
        portions[index] += 1
    return (prefix + "".join(
        f"  pad{index}: \"{'x' * length}\"\n"
        for index, length in enumerate(portions)
    ) + suffix).encode()


class ControlPlaneManifestCommandTest(unittest.TestCase):
    def test_public_constants_and_exports_are_exact(self):
        from kil import v3b2_control_plane_manifest_source as source
        self.assertEqual(COMPONENT_PATHS, (
            ("kube-apiserver", "/etc/kubernetes/manifests/kube-apiserver.yaml"),
            ("kube-controller-manager", "/etc/kubernetes/manifests/kube-controller-manager.yaml"),
        ))
        self.assertEqual(MAX_MANIFEST_BYTES, 1024 * 1024)
        self.assertEqual(MAX_SOURCE_RECORD_BYTES, 4 * 1024 * 1024)
        self.assertEqual(source.__all__, (
            "COMPONENT_PATHS", "MAX_MANIFEST_BYTES", "MAX_SOURCE_RECORD_BYTES",
            "ControlPlaneManifestBinding", "ControlPlaneManifestSourceError",
            "ControlPlaneManifestSourceProof", "control_plane_manifest_observation_specs",
            "control_plane_manifest_pod", "control_plane_manifest_read_argv",
            "validate_control_plane_manifest_source",
        ))

    def test_read_argv_is_closed_to_two_literal_paths(self):
        for component, path in COMPONENT_PATHS:
            with self.subTest(component=component):
                self.assertEqual(control_plane_manifest_read_argv(NODE_ID, component),
                    ("docker", "exec", NODE_ID, "/bin/cat", "--", path))
        for node_id in ("a" * 63, "A" * 64, "g" * 64, NODE_ID + "0", True):
            with self.subTest(node_id=node_id), self.assertRaises(ControlPlaneManifestSourceError):
                control_plane_manifest_read_argv(node_id, "kube-apiserver")  # type: ignore[arg-type]
        for component in ("../kube-scheduler", PATHS["kube-apiserver"], "kube-scheduler", True):
            with self.subTest(component=component), self.assertRaises(ControlPlaneManifestSourceError):
                control_plane_manifest_read_argv(NODE_ID, component)  # type: ignore[arg-type]

    def test_command_grammar_accepts_only_nonmutating_stdin_free_scoped_reads(self):
        for component, _path in COMPONENT_PATHS:
            command = Command(control_plane_manifest_read_argv(NODE_ID, component), 60, env=ENV)
            self.assertFalse(command.mutating)
            self.assertIsNone(command.stdin)
        good = Command(control_plane_manifest_read_argv(NODE_ID, "kube-apiserver"), 60, env=ENV)
        bad_envs = ((), (("DOCKER_HOST", ENV[1][1]),),
                    (("DOCKER_CONFIG", ENV[0][1]),),
                    (("DOCKER_CONFIG", "/tmp/global-docker-config"),
                     ("DOCKER_HOST", ENV[1][1])),
                    (("DOCKER_CONFIG", ENV[0][1]),
                     ("DOCKER_HOST", "unix:///tmp/colima/foreign/docker.sock")))
        for change in ({"mutating": True}, {"stdin": b""},
                       *({"env": value} for value in bad_envs)):
            with self.subTest(change=change), self.assertRaises(JournalError):
                replace(good, **change)
        base = list(good.argv)
        variants = [tuple(base[:-1]), tuple(base + ["extra"]),
                    ("docker", "exec", NODE_ID, "/bin/sh", "-c", "cat " + base[-1]),
                    ("docker", "exec", NODE_ID, "cat", "--", base[-1]),
                    ("docker", "exec", NODE_ID, "/bin/cat", base[-1]),
                    ("docker", "exec", NODE_ID, "/bin/cat", "--", "../manifest.yaml")]
        for argv in variants:
            with self.subTest(argv=argv), self.assertRaises(JournalError):
                Command(argv, 60, env=ENV)

    def test_observation_specs_are_the_exact_owned_identity_bracket(self):
        specs = control_plane_manifest_observation_specs(identity())
        self.assertEqual(tuple(spec.label for spec in specs),
                         ("node_before", "kube-apiserver", "kube-controller-manager", "node_after"))
        self.assertEqual(tuple(spec.command.argv for spec in specs), (
            ("docker", "inspect", "kil-v3-lab-control-plane"),
            control_plane_manifest_read_argv(NODE_ID, "kube-apiserver"),
            control_plane_manifest_read_argv(NODE_ID, "kube-controller-manager"),
            ("docker", "inspect", "kil-v3-lab-control-plane"),
        ))
        self.assertTrue(all(spec.command.env == ENV for spec in specs))


class ControlPlaneManifestProofTest(unittest.TestCase):
    def validate(self, rows: tuple[RawObservation, ...] | None = None,
                 *, owned: OwnedIdentity | None = None,
                 expected: ExpectedContext | None = None) -> ControlPlaneManifestSourceProof:
        retained = owned or identity()
        return validate_control_plane_manifest_source(
            context=expected or context(retained), owned_identity=retained,
            observations=rows or observations(retained))

    def test_valid_pair_retains_four_sources_and_two_sorted_bindings(self):
        proof = self.validate()
        self.assertEqual(proof.run_id, RUN_ID)
        self.assertEqual(proof.cluster_uid, CLUSTER_UID)
        self.assertEqual(proof.node_container_id, NODE_ID)
        self.assertEqual(proof.node_config_id, CONFIG_ID)
        self.assertEqual(len(proof.raw_observations), 4)
        self.assertEqual(tuple(binding.component for binding in proof.bindings),
                         ("kube-apiserver", "kube-controller-manager"))
        self.assertEqual(tuple(binding.path for binding in proof.bindings),
                         tuple(path for _component, path in COMPONENT_PATHS))
        self.assertFalse(proof.runtime_complete)
        self.assertFalse(proof.application_complete)
        for binding, payload in zip(proof.bindings,
                                    (manifest("kube-apiserver"), manifest("kube-controller-manager")),
                                    strict=True):
            self.assertEqual(binding.byte_count, len(payload))
            self.assertEqual(binding.sha256, sha256(payload).hexdigest())

    def test_observations_must_be_exact_ordered_unique_registry(self):
        rows = observations()
        variants = (rows[:-1], rows + (rows[-1],),
                    (rows[0], rows[2], rows[1], rows[3]),
                    (rows[0], rows[1], rows[1], rows[3]))
        for variant in variants:
            with self.subTest(labels=tuple(row.label for row in variant)), \
                    self.assertRaises(ControlPlaneManifestSourceError):
                self.validate(variant)
        for index in range(4):
            changed = list(rows)
            changed[index] = replace(changed[index], label="other")
            with self.subTest(index=index), self.assertRaises(ControlPlaneManifestSourceError):
                self.validate(tuple(changed))

    def test_commands_and_authority_are_revalidated_from_owned_identity(self):
        rows = observations()
        for index in range(4):
            for field, value in (("argv", rows[index].argv + ("extra",)),
                                 ("env", (("DOCKER_CONFIG", ENV[0][1]),
                                          ("DOCKER_HOST", "unix:///tmp/colima/foreign/docker.sock")))):
                changed = list(rows)
                changed[index] = replace(changed[index], **{field: value})
                with self.subTest(index=index, field=field), \
                        self.assertRaises(ControlPlaneManifestSourceError):
                    self.validate(tuple(changed))

    def test_node_bracket_rejects_identity_state_label_image_and_config_drift(self):
        changes = (
            {"node_id": "d" * 64},
            {"config_id": "sha256:" + "e" * 64},
            {"requested_image": "kindest/node:v1.36.1@sha256:" + "f" * 64},
            {"running": False},
            {"labels": {"io.x-k8s.kind.cluster": "foreign",
                        "io.x-k8s.kind.role": "control-plane"}},
            {"labels": {"io.x-k8s.kind.cluster": "kil-v3-lab",
                        "io.x-k8s.kind.role": "worker"}},
            {"labels": {"io.x-k8s.kind.cluster": "kil-v3-lab",
                        "io.x-k8s.kind.role": "control-plane", "extra": "value"}},
        )
        for bracket in ("before", "after"):
            for change in changes:
                with self.subTest(bracket=bracket, change=change), \
                        self.assertRaises(ControlPlaneManifestSourceError):
                    self.validate(observations(**{bracket: node(**change)}))

    def test_context_and_owned_identity_must_bind_run_cluster_node_and_kind_image(self):
        base = identity()
        bad_contexts = (
            context(base, run_id="d" * 64),
            context(base, kind_node_image="kindest/node:v1.36.1"),
            context(identity(cluster_incarnation_uid="other-cluster")),
            ExpectedContext(RUN_ID, 5, "other", canonical({"kind_cluster": "kil-v3-lab"}),
                            context(base).inputs),
        )
        for expected in bad_contexts:
            with self.subTest(family=expected.family), self.assertRaises(ControlPlaneManifestSourceError):
                self.validate(expected=expected)
        with self.assertRaises(ControlPlaneManifestSourceError):
            self.validate(owned=identity(node_container_id="d" * 64),
                          expected=context(base))

    def test_transport_invalid_utf8_and_per_stdout_bound_fail_closed(self):
        rows = observations()
        changes = (
            (1, {"returncode": 1}),
            (1, {"returncode": -1001}),
            (1, {"stderr": b"diagnostic"}),
            (1, {"stdout": b"apiVersion: v1\nkind: Pod\nmetadata: {}\nspec: \xff\n"}),
            (0, {"stdout": b"\xff"}),
        )
        for index, change in changes:
            altered = list(rows)
            altered[index] = replace(altered[index], **change)
            with self.subTest(index=index, change=change), \
                    self.assertRaises(ControlPlaneManifestSourceError):
                self.validate(tuple(altered))
        exact = sized_manifest(MAX_MANIFEST_BYTES)
        proof = self.validate(observations(apiserver=exact))
        self.assertEqual(proof.bindings[0].byte_count, MAX_MANIFEST_BYTES)
        with self.assertRaises(ControlPlaneManifestSourceError):
            self.validate(observations(apiserver=sized_manifest(MAX_MANIFEST_BYTES + 1)))

    def test_closed_yaml_and_exact_pod_envelope_reject_ambiguity(self):
        invalid = (
            b"apiVersion: v1\napiVersion: v1\nkind: Pod\nmetadata: {}\nspec: {}\n",
            b"apiVersion: !tag v1\nkind: Pod\nmetadata: {}\nspec: {}\n",
            b"apiVersion: &version v1\nkind: Pod\nmetadata: {}\nspec: {}\n",
            b"apiVersion: v1\nkind: Pod\nmetadata: *metadata\nspec: {}\n",
            b"apiVersion: v1\nkind: Pod\nmetadata: {}\nspec: {}\n---\nkind: Pod\n",
            b"apiVersion: v1\nkind: Pod\nmetadata: {}\nspec:\n  enabled: yes\n",
            b"apiVersion: v2\nkind: Pod\nmetadata: {}\nspec: {}\n",
            b"apiVersion: v1\nkind: Service\nmetadata: {}\nspec: {}\n",
            b"apiVersion: v1\nkind: Pod\nspec: {}\n",
            b"apiVersion: v1\nkind: Pod\nmetadata: {}\n",
            b"apiVersion: v1\nkind: Pod\nmetadata: []\nspec: {}\n",
            b"apiVersion: v1\nkind: Pod\nmetadata: {}\nspec: []\n",
            b"apiVersion: v1\nkind: Pod\nmetadata: {}\nspec: {}\nstatus: {}\n",
        )
        for payload in invalid:
            with self.subTest(payload=payload[:50]), self.assertRaises(ControlPlaneManifestSourceError):
                self.validate(observations(apiserver=payload))

    def test_raw_and_semantic_digests_are_independent(self):
        original = self.validate()
        equivalent = manifest("kube-apiserver").replace(
            b"name: kube-apiserver", b'name: "kube-apiserver"')
        raw_changed = self.validate(observations(apiserver=equivalent))
        semantic_changed = self.validate(observations(
            apiserver=manifest("kube-apiserver", image="registry.k8s.io/kube-apiserver:v9")))
        self.assertNotEqual(original.bindings[0].sha256, raw_changed.bindings[0].sha256)
        self.assertEqual(original.bindings[0].semantic_sha256,
                         raw_changed.bindings[0].semantic_sha256)
        self.assertNotEqual(original.bindings[0].semantic_sha256,
                            semantic_changed.bindings[0].semantic_sha256)

    def test_record_constructors_recompute_and_reject_forgery(self):
        proof = self.validate()
        with self.assertRaises(FrozenInstanceError):
            proof.run_id = "d" * 64  # type: ignore[misc]
        binding = proof.bindings[0]
        for change in ({"component": "kube-scheduler"}, {"path": "/tmp/manifest"},
                       {"byte_count": True}, {"sha256": "bad"},
                       {"semantic_sha256": True}):
            with self.subTest(change=change), self.assertRaises(ControlPlaneManifestSourceError):
                replace(binding, **change)
        forged_binding = replace(binding, sha256="0" * 64)
        with self.assertRaises(ControlPlaneManifestSourceError):
            replace(proof, bindings=(forged_binding, proof.bindings[1]))
        for field, value in (("argv", [*json.loads(proof.raw_observations[1])["argv"], "extra"]),
                             ("env", [["DOCKER_CONFIG", ENV[0][1]],
                                      ["DOCKER_HOST", "unix:///tmp/colima/foreign/docker.sock"]])):
            retained = list(proof.raw_observations)
            raw = json.loads(retained[1])
            raw[field] = value
            retained[1] = canonical(raw)
            with self.subTest(raw_field=field), self.assertRaises(ControlPlaneManifestSourceError):
                replace(proof, raw_observations=tuple(retained))

    def test_coordinated_raw_tampering_cannot_replace_retained_authority(self):
        proof = self.validate()
        alternate_image = "kindest/node:v1.36.1@sha256:" + "9" * 64

        changed = list(proof.raw_observations)
        for index in (0, 3):
            raw = json.loads(changed[index])
            inspected = json.loads(bytes.fromhex(raw["stdout_hex"]))
            inspected[0]["Config"]["Image"] = alternate_image
            raw["stdout_hex"] = canonical(inspected).hex()
            changed[index] = canonical(raw)
        with self.assertRaises(ControlPlaneManifestSourceError):
            replace(proof, raw_observations=tuple(changed))

        changed = list(proof.raw_observations)
        foreign = [["DOCKER_CONFIG", "/tmp/foreign/docker-config"],
                   ["DOCKER_HOST", "unix:///tmp/foreign/kil-v3-lab/docker.sock"]]
        for index in range(4):
            raw = json.loads(changed[index])
            raw["env"] = foreign
            changed[index] = canonical(raw)
        with self.assertRaises(ControlPlaneManifestSourceError):
            replace(proof, raw_observations=tuple(changed))

        for change in ({"run_id": "d" * 63}, {"run_id": "d" * 64},
                       {"cluster_uid": ""},
                       {"cluster_uid": "11111111-1111-4111-8111-111111111111"},
                       {"node_container_id": "D" * 64},
                       {"node_config_id": "b" * 64},
                       {"raw_observations": proof.raw_observations[:-1]},
                       {"bindings": proof.bindings[::-1]},
                       {"runtime_complete": 0}, {"runtime_complete": True},
                       {"application_complete": 0}, {"application_complete": True}):
            with self.subTest(change=change), self.assertRaises(ControlPlaneManifestSourceError):
                replace(proof, **change)

    def test_exact_types_defeat_subclasses_and_equality_traps(self):
        class EqualString(str):
            def __eq__(self, other):
                return True

            __hash__ = str.__hash__

        class IdentitySubclass(OwnedIdentity):
            pass

        class ContextSubclass(ExpectedContext):
            pass

        class ObservationSubclass(RawObservation):
            pass

        class BindingSubclass(ControlPlaneManifestBinding):
            pass

        with self.assertRaises(ControlPlaneManifestSourceError):
            control_plane_manifest_read_argv(EqualString(NODE_ID), "kube-apiserver")
        with self.assertRaises(ControlPlaneManifestSourceError):
            control_plane_manifest_read_argv(NODE_ID, EqualString("kube-apiserver"))
        base_identity = identity()
        values = tuple(getattr(base_identity, field) for field in base_identity.__dataclass_fields__)
        with self.assertRaises(ControlPlaneManifestSourceError):
            control_plane_manifest_observation_specs(IdentitySubclass(*values))
        expected = context()
        context_values = tuple(getattr(expected, field) for field in expected.__dataclass_fields__)
        with self.assertRaises(ControlPlaneManifestSourceError):
            self.validate(expected=ContextSubclass(*context_values))
        rows = list(observations())
        row = rows[1]
        raw_values = tuple(getattr(row, field) for field in row.__dataclass_fields__)
        rows[1] = ObservationSubclass(*raw_values)
        with self.assertRaises(ControlPlaneManifestSourceError):
            self.validate(tuple(rows))
        proof = self.validate()
        binding = proof.bindings[0]
        binding_values = tuple(getattr(binding, field) for field in binding.__dataclass_fields__)
        with self.assertRaises(ControlPlaneManifestSourceError):
            replace(proof, bindings=(BindingSubclass(*binding_values), proof.bindings[1]))

    def test_returned_pod_is_fresh_and_detached_from_retained_authority(self):
        proof = self.validate()
        pod = control_plane_manifest_pod(source=proof, component="kube-apiserver")
        pod["metadata"]["name"] = "forged"
        fresh = control_plane_manifest_pod(source=proof, component="kube-apiserver")
        self.assertEqual(fresh["metadata"]["name"], "kube-apiserver")
        self.assertIsNot(pod, fresh)
        for component in ("../kube-apiserver", PATHS["kube-apiserver"], True):
            with self.subTest(component=component), self.assertRaises(ControlPlaneManifestSourceError):
                control_plane_manifest_pod(source=proof, component=component)  # type: ignore[arg-type]

    def test_whole_reconstructed_proof_obeys_four_mib_bound(self):
        base = json.loads(node())
        # Two individually admissible inspect payloads cross the proof's encoded
        # 4 MiB budget once exact raw bytes are hex-committed.
        base[0]["Padding"] = "x" * (MAX_MANIFEST_BYTES - len(node()) - 16)
        padded = canonical(base)
        self.assertLessEqual(len(padded), MAX_MANIFEST_BYTES)
        with self.assertRaises(ControlPlaneManifestSourceError):
            self.validate(observations(before=padded, after=padded))


if __name__ == "__main__":
    unittest.main()
