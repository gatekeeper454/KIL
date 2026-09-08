"""Pure, operation-specific observed postconditions for normal and recovery paths.

Expected inputs are immutable canonical bytes captured independently of the
candidate response. A successful process exit is only a successful observation
transport; it never substitutes for the operation's postcondition.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from types import MappingProxyType
from pathlib import Path
from typing import Callable

from kil.v3b2_contracts import LAB_IDENTITY, TRACK_NAMESPACES

MAX_OBSERVATION_BYTES = 32 * 1024 * 1024
# Serialized proof envelopes contain hexadecimal raw bytes plus independently
# bound expected inputs. Their budget is distinct from each raw observation,
# and is shared by serialization preflight, file reads, and replay decoding.
MAX_PROOF_BUNDLE_BYTES = 64 * 1024 * 1024
CLUSTER_INVENTORY_ARGV = ("docker", "container", "ls", "--all", "--no-trunc", "--format", "{{json .}}")
PROFILE_INVENTORY_ARGV = ("colima", "list", "--json")
CALICO_OBJECTS_SHA256 = "de76213b8097d55a674cbe88ef9ac349317b067fb3c6fc326d4280d17c7104a8"
CALICO_SOURCE_SHA256 = "ac5ab7451dda57cfbf47d584ee901b896b1a9ff388d95b6f01b59f1e1130fdfa"


class ProofError(ValueError):
    pass


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProofError("duplicate observation key")
        result[key] = value
    return result


def decode(payload: bytes, *, maximum: int = MAX_OBSERVATION_BYTES) -> object:
    if type(payload) is not bytes or len(payload) > maximum:
        raise ProofError("observation exceeds its byte bound")
    try:
        return json.loads(payload, object_pairs_hook=_object, parse_constant=lambda _: (_ for _ in ()).throw(ProofError("nonfinite observation")))
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ProofError("observation JSON is invalid") from error


def decode_proof_bundle(payload: bytes) -> object:
    """Decode a complete serialized proof under the same budget as its writer."""
    return decode(payload, maximum=MAX_PROOF_BUNDLE_BYTES)


def calico_objects(source: bytes, projection: bytes) -> list[dict[str, object]]:
    """Read the checksummed canonical projection of all 38 pinned YAML docs.

    The sibling was generated with Psych safe_load from the exact vendored
    source; both independent byte commitments are fixed, so runtime validation
    needs no YAML constructors or Kubernetes discovery.
    """
    if sha256(source).hexdigest() != CALICO_SOURCE_SHA256 or sha256(projection).hexdigest() != CALICO_OBJECTS_SHA256:
        raise ProofError("Calico expected document bytes differ from reviewed source")
    value = decode(projection)
    if (type(value) is not dict or set(value) != {"source_sha256", "items"}
            or value["source_sha256"] != CALICO_SOURCE_SHA256
            or type(value["items"]) is not list or len(value["items"]) != 38):
        raise ProofError("Calico expected document projection is invalid")
    return value["items"]


@dataclass(frozen=True, slots=True)
class ExpectedContext:
    run_id: str
    intent_sequence: int
    family: str
    intent: bytes
    inputs: bytes

    def __post_init__(self):
        if type(self.run_id) is not str or re.fullmatch(r"[0-9a-f]{64}", self.run_id) is None:
            raise ProofError("expected run is invalid")
        if type(self.intent_sequence) is not int or self.intent_sequence < 1:
            raise ProofError("expected intent sequence is invalid")
        for payload in (self.intent, self.inputs):
            if type(decode(payload)) is not dict or canonical(decode(payload)) != payload:
                raise ProofError("expected input is not a canonical object")

    @property
    def commitment(self) -> str:
        return sha256(canonical({"run_id": self.run_id, "intent_sequence": self.intent_sequence,
                                 "family": self.family, "intent": decode(self.intent),
                                 "inputs": decode(self.inputs)})).hexdigest()


@dataclass(frozen=True, slots=True)
class RawObservation:
    label: str
    argv: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    returncode: int
    stdout: bytes
    stderr: bytes

    def __post_init__(self):
        if (type(self.label) is not str or not self.label or type(self.argv) is not tuple
                or type(self.env) is not tuple or type(self.returncode) is not int
                or type(self.stdout) is not bytes or type(self.stderr) is not bytes
                or len(self.stdout) + len(self.stderr) > MAX_OBSERVATION_BYTES):
            raise ProofError("raw observation types or bounds are invalid")


@dataclass(frozen=True, slots=True)
class ProofDecision:
    outcome: str
    category: str
    bindings: bytes = b"{}\n"

    def __post_init__(self):
        if self.outcome not in {"complete", "proved_not_applied", "teardown_only", "unknown"}:
            raise ProofError("proof outcome is not closed")
        if type(decode(self.bindings)) is not dict or canonical(decode(self.bindings)) != self.bindings:
            raise ProofError("proof bindings are not canonical")


def _one(observations: tuple[RawObservation, ...], label: str, argv: tuple[str, ...] | None = None) -> RawObservation:
    matches = [row for row in observations if row.label == label]
    if len(matches) != 1 or (argv is not None and matches[0].argv != argv):
        raise ProofError("operation observation is missing or ambiguous")
    result = matches[0]
    if result.returncode != 0 or result.stderr:
        raise ProofError("operation observation transport is not successful")
    return result


def _profile_rows(observations: tuple[RawObservation, ...], authority) -> list[dict[str, object]]:
    from kil.v3b2_colima_inventory import decode_inventory, require_complete
    from kil.v3b2_profile_state import _paths
    paths = _paths(authority)
    observation = _one(observations, "profile_inventory", PROFILE_INVENTORY_ARGV)
    before = _one(observations, 'profile_roster_before', ())
    after = _one(observations, 'profile_roster_after', ())
    labels = [row.label for row in observations]
    index = labels.index('profile_inventory')
    if (index == 0 or labels[index - 1:index + 2] != ['profile_roster_before', 'profile_inventory', 'profile_roster_after']
            or before.env or after.env or observation.env != (
                ('DOCKER_CONFIG', str(paths.private / 'docker-config')), ('TMPDIR', str(paths.tmp)))):
        raise ProofError('profile inventory bracket or environment is invalid')
    rows = decode_inventory(observation.stdout, returncode=observation.returncode, stderr=observation.stderr)
    return require_complete(rows, decode(before.stdout), decode(after.stdout))


def _cluster_absence(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    inputs = decode(context.inputs)
    owned = inputs["owned_identity"]
    observation = _one(observations, "cluster_inventory", CLUSTER_INVENTORY_ARGV)
    if dict(observation.env).get("DOCKER_HOST") != owned["docker_host"]:
        raise ProofError("cluster inventory endpoint differs from bound authority")
    rows = [decode(line) for line in observation.stdout.splitlines() if line]
    ids, owned_rows = set(), []
    for row in rows:
        if (type(row) is not dict or not {"ID", "Names", "Labels", "Image"}.issubset(row)
                or type(row["ID"]) is not str or re.fullmatch(r"[0-9a-f]{64}", row["ID"]) is None
                or row["ID"] in ids or any(type(row[key]) is not str for key in ("Names", "Labels", "Image"))):
            raise ProofError("cluster inventory row is invalid")
        ids.add(row["ID"])
        labels = row["Labels"].split(",")
        if (row["ID"] == owned["node_container_id"] or row["Names"] == LAB_IDENTITY + "-control-plane"
                or "io.x-k8s.kind.cluster=" + LAB_IDENTITY in labels):
            owned_rows.append(row)
    if owned_rows:
        if len(owned_rows) != 1 or owned_rows[0]["ID"] != owned["node_container_id"]:
            return ProofDecision("unknown", "cluster_inventory_ownership_ambiguous")
        return ProofDecision("unknown", "owned_cluster_still_present")
    return ProofDecision("complete", "authoritative_cluster_absence")


def _profile(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    from kil.v3b2_profile_state import absent, creation_binding, unchanged
    inputs = decode(context.inputs)
    rows = _profile_rows(observations, inputs['profile_paths'])
    owned = [row for row in rows if row["name"] == LAB_IDENTITY]
    state = decode(_one(observations, 'profile_state', ()).stdout)
    authority = inputs['profile_paths']
    if context.family == "profile_start" and not owned:
        if absent(authority, state):
            return ProofDecision("proved_not_applied", "owned_profile_absent")
        return ProofDecision('unknown', 'profile_creation_provenance_unproved')
    if context.family in {"profile_delete", "profile_absence_proof"}:
        if owned:
            return ProofDecision("unknown", "owned_profile_still_present")
        if not absent(authority, state):
            if (state['disk'] is not None and state['profile'] is None and state['instance'] is None
                    and state['lima'] is not None and set(state['lima']['entries']) - {'_config', '_networks', '_disks', '_templates', '_cache'}):
                return ProofDecision('unknown', 'reference_absence_unproved')
            return ProofDecision('unknown', 'owned_profile_filesystem_residue')
        paths = decode(_one(observations, "active_paths", ()).stdout)
        if paths != {name: None for name in inputs["active_paths"]}:
            raise ProofError("active profile paths are not all positively absent")
        return ProofDecision("complete", "profile_and_active_paths_absent")
    if len(owned) != 1:
        raise ProofError("owned profile is missing or ambiguous")
    if {key: value for key, value in owned[0].items() if key != "status"} != inputs["profile_configuration"]:
        raise ProofError("owned profile differs from reviewed configuration")
    status = "running" if context.family == "profile_start" else "stopped"
    if owned[0]["status"].lower() != status:
        return ProofDecision("unknown", "owned_profile_wrong_state")
    if context.family == 'profile_start':
        return ProofDecision('complete', 'owned_profile_running', canonical({'profile_binding': creation_binding(authority, state)}))
    if not unchanged(authority, state, inputs['profile_binding'], stopped=True):
        return ProofDecision('unknown', 'profile_creation_binding_changed')
    return ProofDecision("complete", "owned_profile_" + status)


def _driver(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    from kil.v3b2_inventory import parse_runtime_pod_identity
    from kil.v3b1_driver_protocol import parse_result
    inputs, intent = decode(context.inputs), decode(context.intent)
    expected = inputs["driver_binding"]
    namespace, pod = intent["namespace"], intent["pod"]
    if any(expected[key] != intent[key] for key in ("namespace", "pod", "uid")):
        raise ProofError("driver intent differs from established binding")
    argv = ("kubectl", "--kubeconfig", inputs["owned_identity"]["kubeconfig"], "get", "pod", pod,
            "--namespace", namespace, "--output", "json")
    identities = [parse_runtime_pod_identity(_one(observations, label, argv).stdout,
                 expected_namespace=namespace, expected_pod=pod, expected_container="driver",
                 expected_image=expected["image"], require_ready=False)
                  for label in ("driver_pod_before", "driver_pod_after")]
    if any(identity.uid != expected["uid"] or identity.container_id != expected["container_id"] for identity in identities):
        raise ProofError("driver incarnation differs from established binding")
    before, after = identities
    if context.family == "driver_cancel":
        if after.terminated_exit_code is None:
            return ProofDecision("unknown", "driver_not_terminal")
        if after.terminated_exit_code != 0:
            return ProofDecision("teardown_only", "driver_terminal_nonzero")
        return ProofDecision("complete", "driver_terminal_zero")
    if not before.ready or not after.ready or before.resource_version != after.resource_version:
        raise ProofError("driver readiness source changed during capture")
    track = next(track for track, candidate in TRACK_NAMESPACES if candidate == namespace)
    log_argv = ("kubectl", "--kubeconfig", inputs["owned_identity"]["kubeconfig"], "logs", "pod/driver",
                "--namespace", namespace, "--limit-bytes=1048576")
    payload = _one(observations, "driver_logs", log_argv).stdout
    record = parse_result(payload, expected_track=track)
    if record.get("schema_version") != "kil.v3b1-driver-readiness.v1":
        raise ProofError("driver source is not exactly one readiness record")
    return ProofDecision("complete", "driver_readiness_bound")


def _object_key(item: dict[str, object]) -> tuple[str, str, str, str]:
    from kil.v3b2_api_defaults import object_key
    return object_key(item)


def _matches_applied(expected: object, actual: object) -> bool:
    from kil.v3b2_api_defaults import matches_configuration
    return matches_configuration(expected, actual)


def validate_applied_objects(expected: list[dict[str, object]], payload: bytes, *,
                             profile=None, workload=None, prior_service_bindings=None) -> bytes | None:
    """Compare static objects, optionally proving the fixed nine Service allocations.

    Allocation authority requires independent profile/workload inputs. The
    returned canonical binding array is absent for ordinary static callers.
    """
    observed = decode(payload)
    if type(observed) is dict and observed.get("kind") != "List":
        observed = {"apiVersion": "v1", "kind": "List", "items": [observed]}
    if type(observed) is not dict or observed.get("kind") != "List" or type(observed.get("items")) is not list:
        raise ProofError("applied observation is not a Kubernetes object list")
    desired = {_object_key(item): item for item in expected}
    indexed = {_object_key(item): item for item in observed["items"]}
    if len(desired) != len(expected) or len(indexed) != len(observed["items"]) or set(indexed) != set(desired):
        raise ProofError("applied object identities are not the exact expected set")
    bindings = None
    if profile is not None or workload is not None:
        from kil.v3b2_manifests import render_objects
        from kil.v3b2_service_bindings import validate_service_allocations
        # Compare the caller's desired Service portion to an independent render;
        # neither candidate values nor a caller-replaced expected list define it.
        services = [item for item in decode(render_objects(profile, workload))["items"] if item["kind"] == "Service"]
        expected_services = [item for item in expected if item["kind"] == "Service"]
        if canonical(sorted(expected_services, key=_object_key)) != canonical(sorted(services, key=_object_key)):
            raise ProofError("expected Services differ from independently rendered inputs")
        allocation = validate_service_allocations([item for key, item in indexed.items() if key[1] == "Service"],
            profile=profile, workload=workload, prior_bindings=prior_service_bindings)
        bindings = allocation.bindings
        for item in decode(allocation.configurations):
            indexed[_object_key(item)] = item
    elif prior_service_bindings is not None:
        raise ProofError("Service bindings lack independent profile and workload context")
    for key, item in indexed.items():
        metadata = item["metadata"]
        if (type(metadata.get("uid")) is not str or not metadata["uid"]
                or type(metadata.get("resourceVersion")) is not str or not metadata["resourceVersion"]
                or not _matches_applied(desired[key], item)):
            raise ProofError("applied object configuration differs from reviewed inputs")
    return bindings


def _applied(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    inputs = decode(context.inputs)
    argv = ("kubectl", "--kubeconfig", inputs["owned_identity"]["kubeconfig"], "get", "--filename", "-", "--output", "json")
    result = _one(observations, "applied_objects", argv)
    service_context = {}
    if context.family == "application_apply" and ("profile" in inputs or "workload" in inputs):
        from kil.v3b2_contracts import V3B2Profile
        from kil.v3b2_manifests import WorkloadIdentity
        service_context = {"profile": V3B2Profile.from_mapping(inputs["profile"]),
                           "workload": WorkloadIdentity(**inputs["workload"]),
                           "prior_service_bindings": inputs["prior_service_bindings"]}
    bindings = validate_applied_objects(inputs["applied_objects"], result.stdout, **service_context)
    return ProofDecision("complete", "exact_applied_configuration",
                         canonical({"service_bindings": decode(bindings)}) if bindings is not None else b"{}\n")


def node_images_argv(node_id: str) -> tuple[str, ...]:
    return ("docker", "exec", node_id, "/usr/local/bin/ctr", "--address", "/run/containerd/containerd.sock",
            "--namespace", "k8s.io", "images", "check", "--snapshotter", "overlayfs")


def _image_load(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    inputs = decode(context.inputs)
    identity = inputs["owned_identity"]
    observed = _one(observations, "node_images", node_images_argv(identity["node_container_id"]))
    if dict(observed.env).get("DOCKER_HOST") != identity["docker_host"]:
        raise ProofError("image store endpoint differs from the bound node")
    lines = observed.stdout.decode("utf-8", errors="strict").splitlines()
    if not lines or lines[0].split() != ["REF", "TYPE", "DIGEST", "STATUS", "SIZE", "UNPACKED"]:
        raise ProofError("node image check header is invalid")
    indexed = {}
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 7 or parts[0] in indexed:
            raise ProofError("node image check row is malformed or duplicated")
        indexed[parts[0]] = parts
    for expected in inputs["images"]:
        parts = indexed.get(expected["reference"])
        if parts is None:
            return ProofDecision("teardown_only", "node_image_missing")
        counts = re.fullmatch(r"\(([1-9][0-9]*)/([1-9][0-9]*)\)", parts[4])
        if (parts[1] not in {"application/vnd.oci.image.manifest.v1+json", "application/vnd.oci.image.index.v1+json",
                             "application/vnd.docker.distribution.manifest.v2+json", "application/vnd.docker.distribution.manifest.list.v2+json"}
                or parts[2] != expected["manifest_digest"] or parts[3] != "complete" or counts is None
                or counts.group(1) != counts.group(2) or parts[-1] != "true"):
            return ProofDecision("teardown_only", "node_image_content_incomplete")
    return ProofDecision("complete", "bound_node_image_store_complete")


def _cluster(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    inputs = decode(context.inputs)
    identity = inputs["owned_identity"]
    node_observation = _one(observations, "node", ("docker", "inspect", "kil-v3-lab-control-plane"))
    if dict(node_observation.env).get("DOCKER_HOST") != identity["docker_host"]:
        raise ProofError("node endpoint differs from owned authority")
    nodes = decode(node_observation.stdout)
    if type(nodes) is not list or len(nodes) != 1:
        raise ProofError("node observation is ambiguous")
    node = nodes[0]
    if (node["Name"] != "/kil-v3-lab-control-plane" or node["Config"]["Image"] != inputs["kind_node_image"]
            or re.fullmatch(r"[0-9a-f]{64}", node["Id"]) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", node["Image"]) is None
            or node["Config"]["Labels"].get("io.x-k8s.kind.cluster") != LAB_IDENTITY
            or node["Config"]["Labels"].get("io.x-k8s.kind.role") != "control-plane"):
        raise ProofError("node identity differs from the fixed cluster")
    namespace = decode(_one(observations, "cluster_namespace", ("kubectl", "--kubeconfig", identity["kubeconfig"],
                       "get", "namespace", "kube-system", "--output", "json")).stdout)
    uid = namespace["metadata"]["uid"]
    if (namespace["kind"] != "Namespace" or namespace["apiVersion"] != "v1" or namespace["metadata"]["name"] != "kube-system"
            or re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", uid) is None):
        raise ProofError("cluster namespace incarnation is invalid")
    if (identity.get("node_container_id") not in (None, node["Id"])
            or identity.get("cluster_incarnation_uid") not in (None, uid)):
        raise ProofError("observed cluster incarnation changed")
    configuration = _one(observations, "kind_configuration", ()).stdout
    if sha256(configuration).hexdigest() != inputs["kind_config_sha256"]:
        raise ProofError("Kind configuration changed")
    return ProofDecision("complete", "owned_cluster_incarnation", canonical({
        "node_container_id": node["Id"], "cluster_incarnation_uid": uid, "docker_host": identity["docker_host"],
    }))


def _image_import(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    inputs = decode(context.inputs)
    archive = _one(observations, "image_archive", ()).stdout
    if "archive_byte_count" in inputs:
        measured = decode(archive)
        valid_archive = measured == {"path": inputs["archive_path"], "byte_count": inputs["archive_byte_count"],
                                     "sha256": inputs["archive_sha256"]}
    else:
        valid_archive = sha256(archive).hexdigest() == inputs["archive_sha256"]
    if not valid_archive:
        raise ProofError("retained import archive differs from reviewed content")
    if len(inputs["images"]) != 2:
        raise ProofError("expected import image set is not exact")
    for index, expected in enumerate(inputs["images"]):
        observed = _one(observations, "image_" + str(index), ("docker", "image", "inspect", expected["reference"]))
        if dict(observed.env).get("DOCKER_HOST") != inputs["owned_identity"]["docker_host"]:
            raise ProofError("imported image endpoint differs from the owned daemon")
        records = decode(observed.stdout)
        if type(records) is not list or len(records) != 1:
            raise ProofError("imported image inspection is ambiguous")
        row = records[0]
        if (row.get("Id") != expected["config_digest"] or type(row.get("RepoTags")) is not list
                or type(row.get("RepoDigests")) is not list
                or expected["reference"] not in (*row["RepoTags"], *row["RepoDigests"])):
            return ProofDecision("teardown_only", "imported_image_content_mismatch")
    return ProofDecision("complete", "owned_image_contents_resolved")


RUNTIME_RESOURCES = "namespaces,pods,services,endpoints,endpointslices,serviceaccounts,configmaps,deployments,daemonsets,networkpolicies"


def _readiness(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    from kil.v3b2_contracts import V3B2Profile
    from kil.v3b2_manifests import WorkloadIdentity, render_objects
    from kil.v3b2_inventory import parse_runtime_inventory
    inputs = decode(context.inputs)
    if inputs.get("runtime_contract_complete") is False:
        return ProofDecision("unknown", "platform_inventory_contract_pending")
    if inputs.get("prior_service_bindings") is None:
        raise ProofError("readiness lacks established Service allocation bindings")
    identity = inputs["owned_identity"]
    profile = V3B2Profile.from_mapping(inputs["profile"])
    workload = WorkloadIdentity(**inputs["workload"])
    argv = ("kubectl", "--kubeconfig", identity["kubeconfig"], "get", RUNTIME_RESOURCES, "--all-namespaces", "--output", "json")
    observed = _one(observations, "runtime_inventory", argv)
    snapshot = parse_runtime_inventory(observed.stdout, profile=profile, workload=workload,
                                       node_container_id=identity["node_container_id"], docker_host=identity["docker_host"])
    if snapshot.cluster_incarnation_uid != identity["cluster_incarnation_uid"]:
        raise ProofError("readiness cluster incarnation changed")
    desired = decode(render_objects(profile, workload))["items"]
    keys = {_object_key(item) for item in desired}
    selected = [item for item in decode(observed.stdout)["items"] if _object_key(item) in keys]
    validate_applied_objects(desired, canonical({"apiVersion": "v1", "kind": "List", "items": selected}),
                             profile=profile, workload=workload,
                             prior_service_bindings=inputs["prior_service_bindings"])
    return ProofDecision("complete", "closed_runtime_readiness", canonical({"runtime_snapshot": asdict(snapshot)}))


ACTIVE_GAUGES = frozenset({"http.kil_v3b_ingress.downstream_cx_active", "http.kil_v3b_ingress.downstream_rq_active",
                         "cluster.kil-v3b-authz.upstream_rq_active", "cluster.kil-v3b-target.upstream_rq_active"})


def _quiescence(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    from kil.v3b2_inventory import parse_runtime_pod_identity
    from kil.v3b2_journal import OwnedIdentity, kubectl_envoy_quiesce_commands
    inputs = decode(context.inputs)
    identity = OwnedIdentity(**inputs["owned_identity"])
    bindings = inputs["envoy_bindings"]
    if [row["namespace"] for row in bindings] != [namespace for _track, namespace in TRACK_NAMESPACES]:
        raise ProofError("quiescence workload bindings are not the closed set")
    for binding in bindings:
        namespace, pod = binding["namespace"], binding["pod"]
        argv = ("kubectl", "--kubeconfig", identity.kubeconfig, "get", "pod", pod, "--namespace", namespace, "--output", "json")
        for phase in ("before", "after"):
            observed = parse_runtime_pod_identity(_one(observations, namespace + ":" + phase, argv).stdout,
                       expected_namespace=namespace, expected_pod=pod, expected_container="envoy", expected_image=binding["image"], require_ready=False)
            if observed.uid != binding["uid"] or observed.container_id != binding["container_id"] or observed.terminated_exit_code is not None:
                raise ProofError("quiescence workload incarnation changed or terminated")
        inspect = kubectl_envoy_quiesce_commands(identity, namespace, pod)[1]
        raw = decode(_one(observations, namespace + ":stats", inspect.argv).stdout)
        if type(raw) is not dict or set(raw) != {"listener_refused", "stats"} or raw["listener_refused"] is not True or type(raw["stats"]) is not list:
            raise ProofError("quiescence lacks explicit listener refusal")
        gauges = [row for row in raw["stats"] if type(row) is dict and row.get("name") in ACTIVE_GAUGES]
        if (len(gauges) != len(ACTIVE_GAUGES) or {row["name"] for row in gauges} != ACTIVE_GAUGES
                or any(set(row) != {"name", "value"} or type(row["value"]) is not int or row["value"] != 0 for row in gauges)):
            raise ProofError("quiescence gauges are missing, duplicate, or active")
    return ProofDecision("complete", "same_envoy_process_quiescent")


def _freeze(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    inputs, intent = decode(context.inputs), decode(context.intent)
    payload = _one(observations, "capture_manifest", ()).stdout
    if sha256(payload).hexdigest() != intent["evidence_sha256"]:
        raise ProofError("frozen capture manifest differs from its intent")
    manifest = decode(payload)
    if type(manifest) is not dict or set(manifest) != {"run_id", "sources"} or manifest["run_id"] != "v3b2-" + context.run_id:
        raise ProofError("capture manifest identity is invalid")
    expected_pairs = [(track, kind) for track, _namespace in TRACK_NAMESPACES for kind in ("driver", "decision", "envoy", "target")]
    if [(row["track"], row["kind"]) for row in manifest["sources"]] != expected_pairs:
        raise ProofError("capture manifest does not bind every source")
    for source in manifest["sources"]:
        capture = source["capture"]
        if not any(all(image.get(key) == capture[key] for key in ("namespace", "pod", "container", "uid", "container_id"))
                   for image in inputs["source_images"]):
            raise ProofError("frozen source identity differs from the established incarnation")
        actual = _one(observations, source["track"] + ":" + source["kind"], ()).stdout
        if (capture["byte_count"] != len(actual) or capture["sha256"] != sha256(actual).hexdigest()
                or actual != b"".join(canonical(row) for row in capture["raw_records"])):
            raise ProofError("frozen source bytes differ from their complete commitment")
    return ProofDecision("complete", "all_source_boundaries_frozen")


def _foreign(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    from kil.v3b2_colima_inventory import validate_records
    inputs = decode(context.inputs)
    profiles = _profile_rows(observations, inputs['profile_paths'])
    if any(row["name"] == LAB_IDENTITY for row in profiles):
        raise ProofError("foreign comparison still includes owned resources")
    raw_context = _one(observations, "global_context", ("docker", "context", "show")).stdout
    current_context = raw_context.decode("utf-8", errors="strict").strip()
    if not current_context or len(raw_context) > 4096:
        raise ProofError("global context observation is invalid")
    unchanged = profiles == validate_records(inputs["foreign_before"]) and current_context == inputs["global_context_before"]
    attestation = canonical({'profiles': profiles, 'global_context': current_context})
    return ProofDecision("complete", "foreign_state_compared", canonical({
        'unchanged': unchanged, 'foreign_after': profiles, 'global_context_after': current_context,
        'attestation_sha256': sha256(attestation).hexdigest()}))


def _publication(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    from pathlib import Path
    from kil.v3b2_evidence import PUBLIC_FILES, _verify_sums, _verify_v3b2
    inputs, intent = decode(context.inputs), decode(context.intent)
    if Path(intent["destination"]) != Path(inputs["public_parent"]) / ("v3b2-" + context.run_id):
        raise ProofError("publication destination differs from the bound run")
    for family in ("cluster_absence_proof", "profile_absence_proof", "foreign_snapshot_comparison"):
        records = [row for row in inputs["history"] if row["event"] == family + "_complete"]
        if len(records) != 1 or re.fullmatch(r"[0-9a-f]{64}", records[0]["details"]["observed_proof_sha256"]) is None:
            raise ProofError("publication lacks completed absence/comparison proofs")
    tree = decode(_one(observations, "publication_tree", ()).stdout)
    if type(tree) is not dict or set(tree) != PUBLIC_FILES:
        raise ProofError("publication tree is not closed")
    payloads = {name: bytes.fromhex(value) for name, value in tree.items()}
    if sha256(canonical({name: sha256(value).hexdigest() for name, value in payloads.items()})).hexdigest() != intent["tree_commitment_sha256"]:
        raise ProofError("publication tree commitment differs from its intent")
    _verify_sums(payloads, set(PUBLIC_FILES))
    verified = _verify_v3b2(payloads)
    if verified.run_id != "v3b2-" + context.run_id or verified.public_commitment != intent["public_commitment_sha256"]:
        raise ProofError("publication semantics differ from the bound run")
    if inputs["teardown_only"] and verified.result_class not in {"diagnostic_foreign_state_mismatch"}:
        raise ProofError("failed lifecycle cannot publish nominal or readiness success")
    return ProofDecision("complete", "complete_publication_reverified")


@dataclass(frozen=True, slots=True)
class ObservationRequest:
    """An exact command or local read, derived only from immutable expectations."""
    label: str
    command: object = None
    source: str = "command"
    paths: tuple[str, ...] = ()


def _command(label, argv, inputs, *, stdin=None):
    from kil.v3b2_journal import Command
    env = ()
    if argv[0] == 'colima':
        private = Path(inputs['profile_paths']['private'])
        env = (('DOCKER_CONFIG', str(private / 'docker-config')), ('TMPDIR', str(private / 'runtime-tmp')))
    if argv[0] == "docker" and argv != ("docker", "context", "show"):
        identity = inputs["owned_identity"]
        env = (("DOCKER_CONFIG", str(Path(identity["kubeconfig"]).parent / "docker-config")),
               ("DOCKER_HOST", identity["docker_host"]))
    return ObservationRequest(label, Command(argv, 60, stdin=stdin, env=env))


def inventory_requests(inputs):
    return (ObservationRequest('profile_roster_before', source='profile_roster'),
            _command('profile_inventory', PROFILE_INVENTORY_ARGV, inputs),
            ObservationRequest('profile_roster_after', source='profile_roster'))


def _profile_requests(context):
    inputs = decode(context.inputs)
    requests = [*inventory_requests(inputs),
                ObservationRequest('profile_state', source='profile_state')]
    if context.family in {"profile_delete", "profile_absence_proof"}:
        requests.append(ObservationRequest("active_paths", source="lstat", paths=tuple(inputs["active_paths"])))
    return tuple(requests)


def _cluster_requests(context):
    inputs = decode(context.inputs)
    return (_command("node", ("docker", "inspect", LAB_IDENTITY + "-control-plane"), inputs),
            _command("cluster_namespace", ("kubectl", "--kubeconfig", inputs["owned_identity"]["kubeconfig"],
                "get", "namespace", "kube-system", "--output", "json"), inputs),
            ObservationRequest("kind_configuration", source="file", paths=(inputs["kind_config_path"],)))


def _cluster_absence_requests(context):
    extra = _cluster_requests(context) if context.family == "cluster_delete" else ()
    return (_command("cluster_inventory", CLUSTER_INVENTORY_ARGV, decode(context.inputs)), *extra)


def _image_import_requests(context):
    inputs = decode(context.inputs)
    return (ObservationRequest("image_archive", source="hash", paths=(inputs["archive_path"],)),
            *(_command("image_" + str(index), ("docker", "image", "inspect", row["reference"]), inputs)
              for index, row in enumerate(inputs["images"])), *_cluster_requests(context))


def _image_load_requests(context):
    inputs = decode(context.inputs)
    return (_command("node_images", node_images_argv(inputs["owned_identity"]["node_container_id"]), inputs),
            *_cluster_requests(context))


def _applied_requests(context):
    inputs = decode(context.inputs)
    # The exact static reviewed list is sent as stdin; no discovery-selected names.
    manifest = canonical({"apiVersion": "v1", "kind": "List", "items": inputs["applied_objects"]})
    return (_command("applied_objects", ("kubectl", "--kubeconfig", inputs["owned_identity"]["kubeconfig"],
                     "get", "--filename", "-", "--output", "json"), inputs, stdin=manifest),
            *_cluster_requests(context))


def _readiness_requests(context):
    inputs = decode(context.inputs)
    return (_command("runtime_inventory", ("kubectl", "--kubeconfig", inputs["owned_identity"]["kubeconfig"],
            "get", RUNTIME_RESOURCES, "--all-namespaces", "--output", "json"), inputs), *_cluster_requests(context))


def _driver_requests(context):
    inputs, intent = decode(context.inputs), decode(context.intent)
    argv = ("kubectl", "--kubeconfig", inputs["owned_identity"]["kubeconfig"], "get", "pod", intent["pod"],
            "--namespace", intent["namespace"], "--output", "json")
    middle = () if context.family == "driver_cancel" else (_command("driver_logs", (
        "kubectl", "--kubeconfig", inputs["owned_identity"]["kubeconfig"], "logs", "pod/driver",
        "--namespace", intent["namespace"], "--limit-bytes=1048576"), inputs),)
    return (_command("driver_pod_before", argv, inputs), *middle, _command("driver_pod_after", argv, inputs))


def _quiescence_requests(context):
    from kil.v3b2_journal import OwnedIdentity, kubectl_envoy_quiesce_commands
    inputs = decode(context.inputs)
    requests = []
    for binding in inputs["envoy_bindings"]:
        namespace, pod = binding["namespace"], binding["pod"]
        argv = ("kubectl", "--kubeconfig", inputs["owned_identity"]["kubeconfig"], "get", "pod", pod,
                "--namespace", namespace, "--output", "json")
        requests.extend((_command(namespace + ":before", argv, inputs),
            ObservationRequest(namespace + ":stats", kubectl_envoy_quiesce_commands(OwnedIdentity(**inputs["owned_identity"]), namespace, pod)[1]),
            _command(namespace + ":after", argv, inputs)))
    return tuple(requests)


def _freeze_requests(context):
    inputs = decode(context.inputs)
    private = Path(inputs["private_path"])
    return (ObservationRequest("capture_manifest", source="file", paths=(str(private / "source-captures.json"),)),
            *(ObservationRequest(track + ":" + kind, source="file", paths=(str(private / ("source-" + track + "-" + kind + ".jsonl")),))
              for track, _namespace in TRACK_NAMESPACES for kind in ("driver", "decision", "envoy", "target")))


def _foreign_requests(context):
    inputs = decode(context.inputs)
    return (*inventory_requests(inputs),
            _command("global_context", ("docker", "context", "show"), inputs))


def _publication_requests(context):
    # The destination is derived from immutable public_parent/run, not the candidate intent.
    inputs = decode(context.inputs)
    return (ObservationRequest("publication_tree", source="tree", paths=(str(Path(inputs["public_parent"]) / ("v3b2-" + context.run_id)),)),)


@dataclass(frozen=True, slots=True)
class Operation:
    requests: Callable
    validate: Callable


OPERATIONS = MappingProxyType({
    "profile_start": Operation(_profile_requests, _profile),
    "cluster_create": Operation(_cluster_requests, _cluster),
    "image_import": Operation(_image_import_requests, _image_import),
    "image_load": Operation(_image_load_requests, _image_load),
    "calico_apply": Operation(_applied_requests, _applied),
    "application_apply": Operation(_applied_requests, _applied),
    "readiness": Operation(_readiness_requests, _readiness),
    "driver_start": Operation(_driver_requests, _driver),
    "driver_cancel": Operation(_driver_requests, _driver),
    "envoy_quiesce": Operation(_quiescence_requests, _quiescence),
    "evidence_freeze": Operation(_freeze_requests, _freeze),
    "cluster_delete": Operation(_cluster_absence_requests, _cluster_absence),
    "cluster_absence_proof": Operation(_cluster_absence_requests, _cluster_absence),
    "profile_stop": Operation(_profile_requests, _profile),
    "profile_delete": Operation(_profile_requests, _profile),
    "profile_absence_proof": Operation(_profile_requests, _profile),
    "foreign_snapshot_comparison": Operation(_foreign_requests, _foreign),
    "publication": Operation(_publication_requests, _publication),
})


def cleanup_commands(context: ExpectedContext, observations: tuple[RawObservation, ...]):
    """Return exact retry mutations only after affirmative current ownership.

    This is not a completion path. Every retry is followed by the same registry
    observation/validator and durable terminal writer as the normal operation.
    No setup or request command can be returned here.
    """
    from kil.v3b2_journal import Command, OwnedIdentity, kind_delete_command, kubectl_cancel_driver_command
    from kil.v3b2_inventory import parse_runtime_pod_identity
    inputs, intent = decode(context.inputs), decode(context.intent)
    identity = OwnedIdentity(**inputs["owned_identity"])
    try:
        if context.family in {"profile_stop", "profile_delete"}:
            from kil.v3b2_profile_state import orphan_authorized, unchanged, _paths
            owned = [row for row in _profile_rows(observations, inputs['profile_paths']) if row["name"] == LAB_IDENTITY]
            state = decode(_one(observations, 'profile_state', ()).stdout)
            authority, binding = inputs['profile_paths'], inputs.get('profile_binding')
            if context.family == 'profile_delete' and not owned:
                if orphan_authorized(authority, state, binding):
                    return (Command(('limactl', 'disk', 'delete', 'colima-kil-v3-lab'), 300,
                                    env=(('LIMA_HOME', str(_paths(authority).lima)),), mutating=True),)
                return ()
            if len(owned) != 1 or {key: value for key, value in owned[0].items() if key != "status"} != inputs["profile_configuration"]:
                return ()
            required = "running" if context.family == "profile_stop" else "stopped"
            if owned[0]["status"].lower() != required:
                return ()
            if not unchanged(authority, state, binding, stopped=context.family == 'profile_delete'):
                return ()
            operation = "stop" if context.family == "profile_stop" else "delete"
            suffix = () if operation == "stop" else ("--force", "--data")
            private = Path(authority['private'])
            env = (('DOCKER_CONFIG', str(private / 'docker-config')), ('TMPDIR', str(private / 'runtime-tmp')))
            return (Command(("colima", operation, "--profile", LAB_IDENTITY, *suffix), 300, env=env, mutating=True),)
        if context.family == "cluster_delete":
            if _cluster_absence(context, observations).category != "owned_cluster_still_present":
                return ()
            if _cluster(context, observations).outcome != "complete":
                return ()
            return (kind_delete_command(identity),)
        if context.family == "driver_cancel":
            expected = inputs["driver_binding"]
            argv = ("kubectl", "--kubeconfig", identity.kubeconfig, "get", "pod", intent["pod"],
                    "--namespace", intent["namespace"], "--output", "json")
            before = parse_runtime_pod_identity(_one(observations, "driver_pod_before", argv).stdout,
                expected_namespace=intent["namespace"], expected_pod=intent["pod"], expected_container="driver",
                expected_image=expected["image"], require_ready=False)
            after = parse_runtime_pod_identity(_one(observations, "driver_pod_after", argv).stdout,
                expected_namespace=intent["namespace"], expected_pod=intent["pod"], expected_container="driver",
                expected_image=expected["image"], require_ready=False)
            if any(row.uid != expected["uid"] or row.container_id != expected["container_id"]
                   or row.terminated_exit_code is not None or not row.ready for row in (before, after)):
                return ()
            return (kubectl_cancel_driver_command(identity, intent),)
    except (ProofError, ValueError, TypeError, KeyError, IndexError):
        return ()
    return ()


def decide(context: ExpectedContext, observations: tuple[RawObservation, ...]) -> ProofDecision:
    if type(context) is not ExpectedContext or type(observations) is not tuple or len(observations) > 512:
        raise ProofError("proof inputs are not exact bounded records")
    if context.family not in OPERATIONS:
        return ProofDecision("unknown", "unrecognized_event_family")
    try:
        for row in observations:
            if type(row) is not RawObservation:
                raise ProofError("raw observation type is invalid")
            row.__post_init__()
        inputs = decode(context.inputs)
        if (context.family == "profile_start"
                and inputs.get("profile_start_refused_sequence") == context.intent_sequence):
            return ProofDecision("unknown", "profile_start_dispatch_refused")
        if "expected_inputs_sha256" in inputs:
            requests = OPERATIONS[context.family].requests(context)
            expected = [(request.label, () if request.command is None else request.command.argv,
                         () if request.command is None else request.command.env) for request in requests]
            actual = [(row.label, row.argv, row.env) for row in observations]
            if actual != expected:
                return ProofDecision("unknown", "observation_registry_binding_mismatch")
        decision = OPERATIONS[context.family].validate(context, observations)
    except (ProofError, KeyError, TypeError, ValueError, IndexError, AttributeError):
        decision = ProofDecision("unknown", "invalid_or_missing_observation")
    inputs = decode(context.inputs)
    if inputs.get("teardown_only"):
        if context.family in {"profile_start", "cluster_create", "image_import", "image_load", "calico_apply",
                              "application_apply", "readiness", "driver_start"} and decision.outcome == "complete":
            return ProofDecision("teardown_only", "observed_owned_state_after_failure", decision.bindings)
        # These partial operations have no independent resources outside the
        # already proved cluster. A fresh exact incarnation proof is required
        # before abandoning them; transport errors alone confer no authority.
        if context.family in {"image_import", "image_load", "calico_apply", "application_apply", "readiness"} and decision.outcome == "unknown":
            try:
                established = _cluster(context, observations)
                if established.outcome == "complete":
                    return ProofDecision("teardown_only", "observed_owned_cluster_partial_stage", established.bindings)
            except (ProofError, KeyError, TypeError, ValueError, IndexError, AttributeError):
                pass
    return decision


def _expected_for_intent(base, journal, intent, prior, established):
    """No candidate argument: dynamic authority comes only from preceding proofs."""
    if {"service_bindings", "prior_service_bindings"} & base.keys():
        raise ProofError("immutable inputs cannot claim runtime Service allocation bindings")
    inputs = {**base, "owned_identity": {**base["owned_identity"], **established.get("cluster", {})},
              "expected_inputs_sha256": journal["expected_inputs_sha256"], "history": prior,
              "profile_start_refused_sequence": journal["profile_start_refused_sequence"],
              "teardown_only": journal["teardown_from_sequence"] is not None}
    inputs["prior_service_bindings"] = established.get("service_bindings")
    if 'profile_binding' in established:
        inputs['profile_binding'] = established['profile_binding']
    if 'foreign_comparison' in established:
        inputs['foreign_comparison'] = established['foreign_comparison']
    family = intent["event"][:-7]
    if family in {"calico_apply", "application_apply"}:
        inputs["applied_objects"] = base["calico_objects" if family == "calico_apply" else "application_objects"]
    snapshot = established.get("runtime_snapshot")
    images = [] if snapshot is None else snapshot["pod_images"]
    inputs["source_images"] = images
    if family in {"driver_start", "driver_cancel"}:
        matches = [row for row in images if row["namespace"] == intent["details"]["namespace"]
                   and row["pod"] == "driver" and row["container"] == "driver"]
        if len(matches) == 1:
            inputs["driver_binding"] = dict(matches[0])
    if family == "envoy_quiesce":
        inputs["envoy_bindings"] = [dict(row) for _track, namespace in TRACK_NAMESPACES
                                   for row in images if row["namespace"] == namespace and row["container"] == "envoy"]
    return ExpectedContext(journal["run_id"], intent["sequence"], family, canonical(intent["details"]), canonical(inputs))


def terminal_event(context: ExpectedContext, decision: ProofDecision, digest: str):
    """The single terminal encoding used both by the writer and proof replay."""
    if decision.outcome == "unknown":
        raise ProofError("unknown observations cannot produce a terminal event")
    bindings = decode(decision.bindings)
    event_bindings = bindings if context.family == "cluster_create" and decision.outcome == "complete" else {}
    if context.family == 'profile_start' and decision.outcome in {'complete', 'teardown_only'}:
        event_bindings = {'profile_binding': bindings['profile_binding']}
    if context.family == "foreign_snapshot_comparison":
        event_bindings = {key: bindings[key] for key in ('unchanged', 'attestation_sha256')}
    details = {**decode(context.intent), **event_bindings, "observed_proof_sha256": digest}
    if decision.outcome == "complete":
        event = context.family + "_complete"
    elif decision.outcome == "proved_not_applied":
        event = context.family + "_failed"
        details.update(failure_category="not_applied", proof_sha256=digest)
    else:
        event = context.family + "_abandoned_for_teardown"
        details.update(abandoned_family=context.family, stage_category="uncertain_or_partial",
                       observation_sha256=digest, promotion_forbidden=True)
    return {"sequence": context.intent_sequence + 1, "event": event, "details": details}


def expected_context(base_payload: bytes, journal: dict, read_proof: Callable) -> ExpectedContext:
    """Re-derive every incorporated runtime binding from its durable raw proof.

    The terminal writer invokes this too, so a caller cannot smuggle a copied
    candidate into ExpectedContext. Prior proofs are replayed with their original
    latch state; the current pending operation sees the permanent current latch.
    """
    if sha256(base_payload).hexdigest() != journal["expected_inputs_sha256"]:
        raise ProofError("immutable expected inputs commitment changed")
    base = decode(base_payload)
    if canonical(base) != base_payload or base["run_id"] != journal["run_id"] or base["owned_identity"] != journal["owned_identity"]:
        raise ProofError("immutable expected inputs identity changed")
    established, prior, pending = {}, [], None
    for event in journal["events"]:
        name = event["event"]
        if name == "request_intent" or name == "request_result":
            prior.append(event)
            continue
        if name.endswith("_intent"):
            pending = event
            prior.append(event)
            continue
        if pending is None:
            raise ProofError("terminal event lacks pending observed proof")
        digest = event["details"].get("observed_proof_sha256")
        if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ProofError("runtime binding lacks a durable observed proof")
        payload = read_proof(pending["sequence"], digest)
        if sha256(payload).hexdigest() != digest:
            raise ProofError("runtime proof bytes changed")
        document = decode_proof_bundle(payload)
        historical = {**journal, "teardown_from_sequence": journal["teardown_from_sequence"]
                      if journal["teardown_from_sequence"] is not None and journal["teardown_from_sequence"] <= event["sequence"] else None}
        context = _expected_for_intent(base, historical, pending, prior[:-1], established)
        if (document["expected_sha256"] != context.commitment or document["expected_inputs"] != decode(context.inputs)
                or document["intent"] != decode(context.intent) or document["family"] != context.family):
            raise ProofError("runtime proof expected inputs were not independently derived")
        observations = tuple(RawObservation(row["label"], tuple(row["argv"]), tuple(tuple(pair) for pair in row["env"]),
                             row["returncode"], bytes.fromhex(row["stdout_hex"]), bytes.fromhex(row["stderr_hex"])) for row in document["observations"])
        decision = decide(context, observations)
        if decision.outcome != document["outcome"] or decision.outcome == "unknown" or decode(decision.bindings) != document["bindings"]:
            raise ProofError("runtime proof does not revalidate")
        if payload != observation_bundle(context, observations, decision) or event != terminal_event(context, decision, digest):
            raise ProofError("terminal event does not encode its exact observed proof")
        bindings = decode(decision.bindings)
        if context.family == 'profile_start' and decision.outcome in {'complete', 'teardown_only'}:
            established['profile_binding'] = bindings['profile_binding']
        if context.family == "cluster_create" and decision.outcome in {"complete", "teardown_only"}:
            established["cluster"] = {key: bindings[key] for key in ("node_container_id", "cluster_incarnation_uid", "docker_host")}
        if context.family == "readiness" and decision.outcome == "complete":
            established["runtime_snapshot"] = bindings["runtime_snapshot"]
        if context.family == "application_apply" and decision.outcome == "complete" and "service_bindings" in bindings:
            established["service_bindings"] = bindings["service_bindings"]
        if context.family == 'foreign_snapshot_comparison' and decision.outcome == 'complete':
            established['foreign_comparison'] = bindings
        prior.append(event)
        pending = None
    if pending is None:
        raise ProofError("journal has no pending non-request operation")
    return _expected_for_intent(base, journal, pending, prior[:-1], established)


def observation_bundle(context: ExpectedContext, observations: tuple[RawObservation, ...], decision: ProofDecision) -> bytes:
    """Canonical, lossless private proof bytes persisted before a terminal event."""
    # Reject an already-too-large lower bound before allocating hex strings.
    # The exact final check also includes labels, argv/env and envelope fields.
    lower_bound = (2 * sum(len(row.stdout) + len(row.stderr) for row in observations)
                   + len(context.inputs) + len(context.intent) + len(decision.bindings))
    if lower_bound > MAX_PROOF_BUNDLE_BYTES:
        raise ProofError("durable observation bundle exceeds its bound")
    payload = canonical({
        "schema_version": "kil.v3b2-observed-proof.v1", "run_id": context.run_id,
        "intent_sequence": context.intent_sequence, "family": context.family,
        "expected_sha256": context.commitment, "outcome": decision.outcome,
        "expected_inputs": decode(context.inputs), "intent": decode(context.intent), "category": decision.category,
        "bindings": decode(decision.bindings),
        "observations": [{"label": row.label, "argv": list(row.argv), "env": [list(pair) for pair in row.env],
                          "returncode": row.returncode, "stdout_hex": row.stdout.hex(), "stderr_hex": row.stderr.hex()}
                         for row in observations],
    })
    if len(payload) > MAX_PROOF_BUNDLE_BYTES:
        raise ProofError("durable observation bundle exceeds its bound")
    return payload
