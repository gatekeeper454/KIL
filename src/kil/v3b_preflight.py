"""Closed V3B laboratory profile and preflight validation primitives."""

from dataclasses import dataclass, fields
import json
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


SCHEMA_VERSION = "kil.v3b-profile.v2"
LAB_IDENTITY = "kil-v3-lab"
NODE_IMAGE = (
    "kindest/node:v1.36.1@sha256:"
    "3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5"
)
EVIDENCE_SCOPE = "local_envoy_boundary"

_URL_HOSTS = {
    "docker_cli_url": "download.docker.com",
    "kind_url": "github.com",
    "kind_checksum_url": "github.com",
    "kubectl_url": "dl.k8s.io",
    "kubectl_checksum_url": "dl.k8s.io",
    "calico_manifest_url": "raw.githubusercontent.com",
}


class ProfileError(ValueError):
    """Raised when the V3B profile is not the closed approved profile."""


def _require_string(name: str, value: object) -> str:
    if type(value) is not str or not value.strip():
        raise ProfileError(f"{name} must be a nonblank string")
    return value


def _require_url(name: str, value: object) -> str:
    url = _require_string(name, value)
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise ProfileError(
            f"{name} must be an allowlisted HTTPS release URL"
        ) from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != _URL_HOSTS[name]
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.path.startswith("/")
        or parsed.query
        or parsed.fragment
    ):
        raise ProfileError(f"{name} must be an allowlisted HTTPS release URL")
    return url


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProfileError(f"duplicate profile field: {key}")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class V3BProfile:
    """Immutable identity for the first live Envoy validation increment."""

    schema_version: str
    host_os: str
    host_arch: str
    colima_version: str
    colima_profile: str
    lima_version: str
    docker_cli_version: str
    docker_cli_url: str
    kind_version: str
    kind_url: str
    kind_checksum_url: str
    kubernetes_version: str
    kind_node_image: str
    kubectl_version: str
    kubectl_url: str
    kubectl_checksum_url: str
    envoy_version: str
    envoy_image: str
    calico_version: str
    calico_manifest_url: str
    cluster_name: str
    evidence_scope: str

    @classmethod
    def load(cls, path: Path) -> "V3BProfile":
        try:
            value = json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_closed_json_object,
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProfileError(f"cannot load V3B profile: {error}") from error
        if type(value) is not dict:
            raise ProfileError("V3B profile must be a JSON object")
        return cls.from_mapping(value)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "V3BProfile":
        if type(mapping) is not dict:
            raise ProfileError("V3B profile must be an object")
        if any(type(key) is not str for key in mapping):
            raise ProfileError("V3B profile field names must be strings")

        expected = {field.name for field in fields(cls)}
        actual = set(mapping)
        unknown = actual - expected
        missing = expected - actual
        if unknown:
            raise ProfileError(f"unknown V3B profile fields: {sorted(unknown)}")
        if missing:
            raise ProfileError(f"missing V3B profile fields: {sorted(missing)}")

        values: dict[str, object] = {}
        for name in expected:
            values[name] = _require_string(name, mapping[name])
        for name in _URL_HOSTS:
            values[name] = _require_url(name, mapping[name])

        exact_values = {
            "schema_version": SCHEMA_VERSION,
            "host_os": "darwin",
            "host_arch": "arm64",
            "colima_version": "0.10.3",
            "colima_profile": LAB_IDENTITY,
            "lima_version": "2.2.0",
            "docker_cli_version": "29.7.2",
            "docker_cli_url": "https://download.docker.com/mac/static/stable/aarch64/docker-29.7.2.tgz",
            "kind_version": "0.32.0",
            "kind_url": "https://github.com/kubernetes-sigs/kind/releases/download/v0.32.0/kind-darwin-arm64",
            "kind_checksum_url": "https://github.com/kubernetes-sigs/kind/releases/download/v0.32.0/kind-darwin-arm64.sha256sum",
            "kubernetes_version": "1.36.1",
            "kind_node_image": NODE_IMAGE,
            "kubectl_version": "1.36.3",
            "kubectl_url": "https://dl.k8s.io/release/v1.36.3/bin/darwin/arm64/kubectl",
            "kubectl_checksum_url": "https://dl.k8s.io/release/v1.36.3/bin/darwin/arm64/kubectl.sha256",
            "envoy_version": "1.39.1",
            "envoy_image": "docker.io/envoyproxy/envoy:v1.39.1",
            "calico_version": "3.32.0",
            "calico_manifest_url": "https://raw.githubusercontent.com/projectcalico/calico/v3.32.0/manifests/calico.yaml",
            "cluster_name": LAB_IDENTITY,
            "evidence_scope": EVIDENCE_SCOPE,
        }
        for name, expected_value in exact_values.items():
            if values[name] != expected_value:
                raise ProfileError(f"{name} must be {expected_value}")

        return cls(**values)  # type: ignore[arg-type]
