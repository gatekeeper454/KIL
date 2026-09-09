"""Bound the two imported image reference chains in the owned Kind node.

Expected descriptors must come from committed accepted inputs, never from the
candidate CRI/ctr responses. This proof ties observations to the retained node
and Docker endpoint; registry integration must bracket actual cluster identity
and Pod captures. It does not prove temporal stability or runtime readiness.

Pinned source rules: containerd v2.3.1 internal/cri/server/images/image_status.go
and internal/cri/server/container_status.go use the same ordered reference
parser. The latter chooses repoDigests[0] or config identity for ImageRef, and
repoTags[0] or saved ContainerConfig.Image.Image for Image. For Kubernetes
v1.36.1's Never-pull path, kuberuntime_image.go:GetImageRef returns the CRI
config ID; kuberuntime_container.go:generateContainerConfig stores it as Image,
separately from UserSpecifiedImage. Hence the no-tag fallback here is the
independently expected config digest, not the desired repository reference.

crictl v1.36.0 image.go and util.go define quiet single-inspection JSON and
EmitDefaultValues (unset message fields omitted). No verbose info is admitted.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re

from kil.v3b2_journal import OwnedIdentity
from kil.v3b2_proofs import RawObservation, node_images_argv


_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_HEX = re.compile(r"[0-9a-f]{64}")
_TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
_REPOSITORIES = {"kil": "kil.local/kil-v3b2", "envoy": "docker.io/envoyproxy/envoy"}
_TYPES = frozenset({"application/vnd.oci.image.manifest.v1+json",
                    "application/vnd.oci.image.index.v1+json",
                    "application/vnd.docker.distribution.manifest.v2+json",
                    "application/vnd.docker.distribution.manifest.list.v2+json"})
_STATUS = frozenset({"id", "repoTags", "repoDigests", "size", "username", "pinned"})
_MAX_INSPECT = 16384
_MAX_NODE = 262144


class NodeImageReferenceError(ValueError):
    """Image reference evidence is incomplete, unbounded, or inconsistent."""


def _text(value: object, label: str, maximum: int = 512, *, empty=False) -> str:
    if (type(value) is not str or len(value) > maximum or (not empty and not value)
            or any(ord(char) < 32 or ord(char) > 126 for char in value)):
        raise NodeImageReferenceError(f"{label} is not bounded printable ASCII")
    return value


def _digest(value: object) -> str:
    if _DIGEST.fullmatch(_text(value, "digest", 71)) is None:
        raise NodeImageReferenceError("digest is not canonical sha256")
    return value


def _path(value: object) -> str:
    result = _text(value, "path", 4096)
    path = PurePosixPath(result)
    if not path.is_absolute() or str(path) != result or ".." in path.parts:
        raise NodeImageReferenceError("path is not canonical absolute")
    return result


def _tuple(value: object, maximum: int, label: str, *, count=None) -> tuple:
    if type(value) is not tuple or len(value) > maximum or (count is not None and len(value) != count):
        raise NodeImageReferenceError(f"{label} cardinality/type is not exact")
    return value


def _decimal(value: object, *, signed=False, positive=False) -> str:
    text = _text(value, "integer", 20)
    pattern = r"(?:0|[1-9][0-9]*|-[1-9][0-9]*)" if signed else r"(?:0|[1-9][0-9]*)"
    if re.fullmatch(pattern, text) is None:
        raise NodeImageReferenceError("integer string is not canonical")
    integer = int(text)
    low, high = (-2**63, 2**63 - 1) if signed else (0, 2**64 - 1)
    if not low <= integer <= high or (positive and integer == 0):
        raise NodeImageReferenceError("integer is out of range")
    return text


@dataclass(frozen=True, slots=True)
class ExpectedNodeImage:
    role: str
    query_reference: str
    config_digest: str
    target_digest: str
    target_media_type: str
    allowed_repo_tags: tuple[str, ...]
    allowed_repo_digests: tuple[str, ...]
    saved_container_image: str

    def __post_init__(self):
        # Cardinality checks precede iteration, set creation and sorting.
        _tuple(self.allowed_repo_tags, 8, "allowed tags")
        _tuple(self.allowed_repo_digests, 8, "allowed digests")
        role = _text(self.role, "role", 5)
        if role not in _REPOSITORIES:
            raise NodeImageReferenceError("role is not kil or envoy")
        repository = _REPOSITORIES[role]
        query = _text(self.query_reference, "query")
        _digest(self.config_digest); _digest(self.target_digest)
        _text(self.target_media_type, "media type", 128)
        if self.target_media_type not in _TYPES or self.config_digest == self.target_digest:
            raise NodeImageReferenceError("manifest/config identity or media type is invalid")
        if _digest(self.saved_container_image) != self.config_digest:
            raise NodeImageReferenceError("Never-pull saved image must be expected config identity")
        expected_query = (repository + ":sha256-" + self.target_digest[7:]
                          if role == "kil" else repository + "@" + self.target_digest)
        if query != expected_query:
            raise NodeImageReferenceError("query does not bind the reviewed role and target")
        for tag in self.allowed_repo_tags:
            _text(tag, "allowed tag")
            prefix = repository + ":"
            if not tag.startswith(prefix) or _TAG.fullmatch(tag[len(prefix):]) is None:
                raise NodeImageReferenceError("allowed tag is outside the role repository")
        for digest in self.allowed_repo_digests:
            if _text(digest, "allowed digest") != repository + "@" + self.target_digest:
                raise NodeImageReferenceError("allowed digest does not bind repository/target")
        for refs in (self.allowed_repo_tags, self.allowed_repo_digests):
            if tuple(sorted(set(refs))) != refs:
                raise NodeImageReferenceError("allowlists must be canonical and unique")
        if query not in (*self.allowed_repo_tags, *self.allowed_repo_digests):
            raise NodeImageReferenceError("query is absent from reviewed aliases")


def node_image_inspect_argv(node_id: str, reference: str) -> tuple[str, ...]:
    if _HEX.fullmatch(_text(node_id, "node container ID", 64)) is None:
        raise NodeImageReferenceError("node container ID is not exact")
    _text(reference, "reference")
    if re.fullmatch(r"(?:kil\.local/kil-v3b2:sha256-|docker\.io/envoyproxy/envoy@sha256:)[0-9a-f]{64}", reference) is None:
        raise NodeImageReferenceError("query is not an exact reviewed immutable reference")
    return ("docker", "exec", node_id, "/usr/local/bin/crictl", "--runtime-endpoint",
            "unix:///run/containerd/containerd.sock", "--image-endpoint",
            "unix:///run/containerd/containerd.sock", "--timeout", "10s",
            "inspecti", "--quiet", "--output", "json", reference)


def _refs(value: object, allowed: tuple[str, ...]) -> tuple[str, ...]:
    if type(value) is not tuple or len(value) > 8:
        raise NodeImageReferenceError("observed reference cardinality/type is invalid")
    for ref in value:
        if _text(ref, "observed reference") not in allowed:
            raise NodeImageReferenceError("observed reference is not independently allowlisted")
    if len(set(value)) != len(value):
        raise NodeImageReferenceError("duplicate observed reference")
    return value


@dataclass(frozen=True, slots=True)
class NodeImageReferenceBinding:
    expected: ExpectedNodeImage
    repo_tags: tuple[str, ...]
    repo_digests: tuple[str, ...]
    size: str
    username: str
    pinned: bool
    uid: str | None
    runtime_image: str
    image_ref: str

    def __post_init__(self):
        _tuple(self.repo_tags, 8, "observed tags")
        _tuple(self.repo_digests, 8, "observed digests")
        if type(self.expected) is not ExpectedNodeImage:
            raise NodeImageReferenceError("binding expected descriptor type is invalid")
        self.expected.__post_init__()
        tags = _refs(self.repo_tags, self.expected.allowed_repo_tags)
        digests = _refs(self.repo_digests, self.expected.allowed_repo_digests)
        if self.expected.query_reference not in (*tags, *digests):
            raise NodeImageReferenceError("resolved query is not in CRI references")
        _decimal(self.size, positive=True)
        _text(self.username, "username", 256, empty=True)
        if type(self.pinned) is not bool:
            raise NodeImageReferenceError("pinned must be exact bool")
        if self.uid is not None:
            _decimal(self.uid, signed=True)
            if self.username:
                raise NodeImageReferenceError("numeric UID and username are mutually exclusive")
        if _text(self.runtime_image, "runtime image") != (tags[0] if tags else self.expected.saved_container_image):
            raise NodeImageReferenceError("runtime Image is not source-derived")
        if _text(self.image_ref, "image ref") != (digests[0] if digests else self.expected.config_digest):
            raise NodeImageReferenceError("runtime ImageRef is not source-derived")


def _precheck_observation(row: object, maximum: int):
    if type(row) is not RawObservation:
        raise NodeImageReferenceError("observation type is not exact")
    _tuple(row.argv, 16, "argv")
    _tuple(row.env, 2, "environment", count=2)
    if (type(row.stdout) is not bytes or len(row.stdout) > maximum
            or type(row.stderr) is not bytes or len(row.stderr) > 4096):
        raise NodeImageReferenceError("observation byte bound exceeded")
    _text(row.label, "label", 32)
    for arg in row.argv: _text(arg, "argument", 4096)
    for pair in row.env:
        _tuple(pair, 2, "environment entry", count=2)
        for text in pair: _text(text, "environment", 4096)
    if type(row.returncode) is not int or row.returncode != 0 or row.stderr != b"":
        raise NodeImageReferenceError("observation transport was unsuccessful")
    row.__post_init__()


def _closed(value: object, keys: frozenset[str]) -> dict:
    if (type(value) is not dict or len(value) != len(keys)
            or any(type(key) is not str for key in value) or set(value) != keys):
        raise NodeImageReferenceError("quiet JSON shape is open or incomplete")
    return value


def _pairs(pairs):
    if len(pairs) > 16:
        raise NodeImageReferenceError("JSON object is too wide")
    result = {}
    for key, value in pairs:
        if key in result: raise NodeImageReferenceError("duplicate JSON key")
        result[key] = value
    return result


def _reject_number(value):
    raise NodeImageReferenceError("quiet image integers must be protobuf decimal strings")


def _inspection(payload: bytes, expected: ExpectedNodeImage) -> NodeImageReferenceBinding:
    try:
        document = json.loads(payload, object_pairs_hook=_pairs, parse_int=_reject_number,
                              parse_float=_reject_number, parse_constant=_reject_number)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise NodeImageReferenceError("quiet image JSON is invalid") from error
    status = _closed(document, frozenset({"status"}))["status"]
    if type(status) is not dict or len(status) not in (6, 7):
        raise NodeImageReferenceError("quiet status cardinality is invalid")
    status = _closed(status, _STATUS | ({"uid"} if "uid" in status else set()))
    if _digest(status["id"]) != expected.config_digest:
        raise NodeImageReferenceError("CRI config ID differs from independently expected content")
    for name in ("repoTags", "repoDigests"):
        if type(status[name]) is not list or len(status[name]) > 8:
            raise NodeImageReferenceError("CRI reference array is invalid")
    tags, digests = tuple(status["repoTags"]), tuple(status["repoDigests"])
    uid = _closed(status["uid"], frozenset({"value"}))["value"] if "uid" in status else None
    return NodeImageReferenceBinding(expected, tags, digests, status["size"], status["username"],
        status["pinned"], uid, tags[0] if tags else expected.saved_container_image,
        digests[0] if digests else expected.config_digest)


def _node_rows(payload: bytes) -> dict[str, tuple[str, ...]]:
    try: text = payload.decode("ascii")
    except UnicodeError as error: raise NodeImageReferenceError("ctr table is not ASCII") from error
    if (text.count("\n") > 257 or not text.endswith("\n")
            or any(char not in "\n\t" and not " " <= char <= "~" for char in text)):
        raise NodeImageReferenceError("ctr table row bound/framing is invalid")
    # ctr emits LF-delimited rows. str.splitlines() would also accept CR/VT/FF
    # separators and defeat a bound measured against LF bytes.
    lines = text[:-1].split("\n")
    if len(lines) > 257:
        raise NodeImageReferenceError("ctr table exceeds 256 data rows")
    if not lines or lines[0].split() != ["REF", "TYPE", "DIGEST", "STATUS", "SIZE", "UNPACKED"]:
        raise NodeImageReferenceError("ctr table header is invalid")
    rows = {}
    for line in lines[1:]:
        if len(line) > 2048:
            raise NodeImageReferenceError("ctr row is oversized")
        parts = tuple(line.split())
        if len(parts) != 8 or parts[0] in rows:
            raise NodeImageReferenceError("ctr table row is malformed or duplicated")
        _text(parts[0], "ctr reference")
        rows[parts[0]] = parts
    return rows


def _commitment(row: RawObservation) -> str:
    payload = json.dumps([row.label, row.argv, row.env, row.returncode,
                          row.stdout.hex(), row.stderr.hex()], separators=(",", ":")).encode()
    return sha256(payload).hexdigest()


def _compute(identity, docker_config, expected_images, inspections, node_images):
    # All external cardinalities and byte bounds precede constructor traversal,
    # JSON parsing, sorting, or hashing.
    _tuple(expected_images, 2, "expected image pair", count=2)
    _tuple(inspections, 2, "inspection pair", count=2)
    for row in inspections: _precheck_observation(row, _MAX_INSPECT)
    _precheck_observation(node_images, _MAX_NODE)
    if type(identity) is not OwnedIdentity:
        raise NodeImageReferenceError("owned identity type is not exact")
    try: identity.__post_init__()
    except (TypeError, ValueError, AttributeError) as error:
        raise NodeImageReferenceError("owned identity no longer validates") from error
    for value in (identity.docker_host, identity.kind_cluster, identity.kubeconfig,
                  identity.cluster_incarnation_uid, identity.node_container_id):
        _text(value, "complete owned identity", 4096)
    _path(identity.docker_host.removeprefix("unix://"))
    _path(docker_config)
    environment = (("DOCKER_CONFIG", docker_config), ("DOCKER_HOST", identity.docker_host))
    for index, expected in enumerate(expected_images):
        if type(expected) is not ExpectedNodeImage:
            raise NodeImageReferenceError("expected image type is not exact")
        expected.__post_init__()
        if expected.role != ("kil", "envoy")[index]:
            raise NodeImageReferenceError("expected image order must be kil/envoy")
        row = inspections[index]
        if (row.label != "cri_image_" + str(index) or row.env != environment
                or row.argv != node_image_inspect_argv(identity.node_container_id, expected.query_reference)):
            raise NodeImageReferenceError("inspection command/node/environment is not bound")
    if (node_images.label != "node_images" or node_images.env != environment
            or node_images.argv != node_images_argv(identity.node_container_id)):
        raise NodeImageReferenceError("ctr command/node/environment is not bound")
    identities = tuple(digest for image in expected_images
                       for digest in (image.config_digest, image.target_digest))
    if len(set(identities)) != 4:
        raise NodeImageReferenceError("the four expected config/target identities must be distinct")
    rows = _node_rows(node_images.stdout)
    bindings = tuple(_inspection(row.stdout, expected) for row, expected in zip(inspections, expected_images))
    for binding in bindings:
        expected = binding.expected
        for alias in (*binding.repo_tags, *binding.repo_digests):
            parts = rows.get(alias)
            if parts is None:
                raise NodeImageReferenceError("CRI alias has no node-store target")
            counts = re.fullmatch(r"\(([1-9][0-9]{0,9})/([1-9][0-9]{0,9})\)", parts[4])
            if (parts[1] != expected.target_media_type or parts[2] != expected.target_digest
                    or parts[3] != "complete" or counts is None or counts[1] != counts[2]
                    or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", parts[5]) is None
                    or parts[6] not in {"B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"}
                    or parts[7] != "true"):
                raise NodeImageReferenceError("node-store alias target/content is unproved")
    return bindings, tuple(_commitment(row) for row in (*inspections, node_images))


@dataclass(frozen=True, slots=True)
class NodeImageReferenceProof:
    identity: OwnedIdentity
    docker_config: str
    expected_images: tuple[ExpectedNodeImage, ...]
    inspections: tuple[RawObservation, ...]
    node_images: RawObservation
    bindings: tuple[NodeImageReferenceBinding, ...]
    observation_sha256: tuple[str, ...]
    runtime_contract_complete: bool = False

    def __post_init__(self):
        _tuple(self.bindings, 2, "binding pair", count=2)
        _tuple(self.observation_sha256, 3, "observation commitments", count=3)
        if type(self.runtime_contract_complete) is not bool or self.runtime_contract_complete:
            raise NodeImageReferenceError("node image proof cannot complete runtime readiness")
        for binding in self.bindings:
            if type(binding) is not NodeImageReferenceBinding:
                raise NodeImageReferenceError("binding type is not exact")
            binding.__post_init__()
        for digest in self.observation_sha256:
            if _HEX.fullmatch(_text(digest, "commitment", 64)) is None:
                raise NodeImageReferenceError("observation commitment is invalid")
        calculated, commitments = _compute(self.identity, self.docker_config, self.expected_images,
                                           self.inspections, self.node_images)
        if self.bindings != calculated or self.observation_sha256 != commitments:
            raise NodeImageReferenceError("reconstructed proof differs from retained raw observations")


def validate_node_image_references(*, identity: OwnedIdentity, docker_config: str,
                                   expected_images: tuple[ExpectedNodeImage, ...],
                                   inspections: tuple[RawObservation, ...],
                                   node_images: RawObservation) -> NodeImageReferenceProof:
    try:
        bindings, commitments = _compute(identity, docker_config, expected_images, inspections, node_images)
        return NodeImageReferenceProof(identity, docker_config, expected_images, inspections,
                                       node_images, bindings, commitments)
    except NodeImageReferenceError:
        raise
    except (ValueError, TypeError, AttributeError, OverflowError, UnicodeError, RecursionError) as error:
        raise NodeImageReferenceError("malformed node image reference evidence") from error


__all__ = ("ExpectedNodeImage", "NodeImageReferenceBinding", "NodeImageReferenceError",
           "NodeImageReferenceProof", "node_image_inspect_argv", "validate_node_image_references")
