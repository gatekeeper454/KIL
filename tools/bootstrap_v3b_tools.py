#!/usr/bin/env python3
"""Install and verify the closed V3B toolchain under the repository root."""

from argparse import ArgumentParser
from dataclasses import asdict, dataclass, fields
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import tempfile
from typing import Callable, Mapping
from urllib.parse import urlsplit
from urllib.request import urlopen

from kil.v3b_preflight import V3BProfile


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "deploy/kind/v3b-profile.json"
TOOLS_ROOT = ROOT / ".tools"
LOCK_SCHEMA_VERSION = "kil.v3b-tools-lock.v1"
DOCKER_ARCHIVE_LIMIT = 64 * 1024 * 1024
DIRECT_BINARY_LIMIT = 128 * 1024 * 1024
CHECKSUM_LIMIT = 128 * 1024 * 1024
DOCKER_BINARY_LIMIT = 128 * 1024 * 1024
VERSION_OUTPUT_LIMIT = 16 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 30.0
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_CHECKSUM_LINE = re.compile(r"^([a-f0-9]{64})(?:[ \t]+\*?([^\s]+))?$")
_REDIRECT_HOSTS = frozenset(
    {
        "cdn.dl.k8s.io",
        "dl.k8s.io",
        "download.docker.com",
        "github.com",
        "github-releases.githubusercontent.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "storage.googleapis.com",
    }
)
_TOOL_URL_FIELDS = {
    "docker": "docker_cli_url",
    "kind": "kind_url",
    "kubectl": "kubectl_url",
}
_VERSION_ARGUMENTS = {
    "docker": ("--version",),
    "kind": ("version",),
    "kubectl": ("version", "--client", "-o", "json"),
}
_VERSION_MARKERS = {
    "docker": "29.7.2",
    "kind": "v0.32.0",
    "kubectl": "v1.36.3",
}


class ToolBootstrapError(RuntimeError):
    """Raised when a tool cannot be installed or verified safely."""


@dataclass(frozen=True, slots=True)
class ToolMaterial:
    archive_sha256: str
    executable_sha256: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class ToolRecord:
    source_url: str
    archive_sha256: str
    executable_sha256: str
    byte_size: int
    version_output: str
    checksum_attestation: str

    def __post_init__(self) -> None:
        if type(self.source_url) is not str or not self.source_url:
            raise ToolBootstrapError("source_url must be a nonblank string")
        for name in ("archive_sha256", "executable_sha256"):
            if type(getattr(self, name)) is not str or not _DIGEST.fullmatch(
                getattr(self, name)
            ):
                raise ToolBootstrapError(f"{name} must be a SHA-256 digest")
        if type(self.byte_size) is not int or self.byte_size <= 0:
            raise ToolBootstrapError("byte_size must be a positive integer")
        if type(self.version_output) is not str or not self.version_output.strip():
            raise ToolBootstrapError("version_output must be a nonblank string")
        if self.checksum_attestation not in {
            "locally_observed",
            "upstream_sidecar",
        }:
            raise ToolBootstrapError("invalid checksum_attestation")


def _profile_urls(profile: V3BProfile) -> frozenset[str]:
    return frozenset(
        {
            profile.docker_cli_url,
            profile.kind_url,
            profile.kind_checksum_url,
            profile.kubectl_url,
            profile.kubectl_checksum_url,
            profile.calico_manifest_url,
        }
    )


def validate_download_url(
    url: str,
    profile: V3BProfile | None = None,
) -> str:
    """Require an exact URL from the tracked, closed V3B profile."""
    if type(url) is not str:
        raise ToolBootstrapError("download URL must be a string")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise ToolBootstrapError("download URL is not allowlisted") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ToolBootstrapError("download URL is not allowlisted")
    selected = profile if profile is not None else V3BProfile.load(PROFILE_PATH)
    if url not in _profile_urls(selected):
        if parsed.hostname not in {
            "download.docker.com",
            "github.com",
            "dl.k8s.io",
            "raw.githubusercontent.com",
        }:
            raise ToolBootstrapError("download host is not allowlisted")
        raise ToolBootstrapError("download URL is not present in the V3B profile")
    return url


def _validate_redirect(requested_url: str, final_url: str) -> None:
    if final_url == requested_url:
        return
    try:
        parsed = urlsplit(final_url)
        port = parsed.port
    except ValueError as error:
        raise ToolBootstrapError("download redirect is not approved") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _REDIRECT_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
    ):
        raise ToolBootstrapError("download redirect is not approved")


def download_bounded(
    url: str,
    maximum_bytes: int,
    *,
    opener: Callable[..., object] = urlopen,
) -> bytes:
    """Download an exact profile asset without reading beyond its size cap."""
    validated = validate_download_url(url)
    if type(maximum_bytes) is not int or maximum_bytes <= 0:
        raise ToolBootstrapError("download size limit must be positive")
    try:
        with opener(validated, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            geturl = getattr(response, "geturl", None)
            final_url = geturl() if callable(geturl) else validated
            _validate_redirect(validated, final_url)
            payload = response.read(maximum_bytes + 1)
    except ToolBootstrapError:
        raise
    except Exception as error:
        raise ToolBootstrapError(f"download failed for {validated}") from error
    if type(payload) is not bytes:
        raise ToolBootstrapError("download did not return bytes")
    if len(payload) > maximum_bytes:
        raise ToolBootstrapError("download exceeds configured size limit")
    if not payload:
        raise ToolBootstrapError("download returned an empty asset")
    return payload


def _sha256(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _write_executable_atomically(
    payload: bytes,
    destination: Path,
    temp_directory: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_directory.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=temp_directory,
            prefix=f".{destination.name}.",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o755)
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def install_direct_binary(
    payload: bytes,
    expected_sha256: str,
    destination: Path,
    *,
    temp_directory: Path | None = None,
) -> ToolMaterial:
    """Verify a publisher checksum before atomically replacing a binary."""
    if type(payload) is not bytes or not payload:
        raise ToolBootstrapError("direct binary must be nonempty bytes")
    if len(payload) > DIRECT_BINARY_LIMIT:
        raise ToolBootstrapError("direct binary exceeds configured size limit")
    if type(expected_sha256) is not str or not _DIGEST.fullmatch(expected_sha256):
        raise ToolBootstrapError("expected checksum must be a SHA-256 digest")
    actual = _sha256(payload)
    if actual != expected_sha256:
        raise ToolBootstrapError("checksum mismatch; existing binary preserved")
    selected_temp = (
        temp_directory
        if temp_directory is not None
        else destination.parent / ".tmp"
    )
    _write_executable_atomically(payload, destination, selected_temp)
    return ToolMaterial(actual, actual, len(payload))


def _safe_archive_member(member: tarfile.TarInfo) -> bool:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts:
        return False
    if member.issym() or member.islnk():
        return False
    return member.isdir() or member.isreg()


def extract_docker_cli(
    archive_payload: bytes,
    destination: Path,
    *,
    temp_directory: Path | None = None,
) -> ToolMaterial:
    """Extract only ``docker/docker`` after validating every tar member."""
    if type(archive_payload) is not bytes or not archive_payload:
        raise ToolBootstrapError("Docker archive must be nonempty bytes")
    if len(archive_payload) > DOCKER_ARCHIVE_LIMIT:
        raise ToolBootstrapError("Docker archive exceeds configured size limit")
    try:
        with tarfile.open(fileobj=BytesIO(archive_payload), mode="r:gz") as archive:
            members = archive.getmembers()
            if any(not _safe_archive_member(member) for member in members):
                raise ToolBootstrapError("unsafe Docker archive member")
            targets = [
                member
                for member in members
                if member.name == "docker/docker" and member.isreg()
            ]
            if len(targets) != 1:
                raise ToolBootstrapError(
                    "Docker archive must contain exactly one docker/docker file"
                )
            target = targets[0]
            if target.size <= 0 or target.size > DOCKER_BINARY_LIMIT:
                raise ToolBootstrapError("Docker binary exceeds configured size limit")
            extracted = archive.extractfile(target)
            if extracted is None:
                raise ToolBootstrapError("cannot read Docker archive member")
            executable = extracted.read(DOCKER_BINARY_LIMIT + 1)
    except ToolBootstrapError:
        raise
    except (tarfile.TarError, OSError, EOFError) as error:
        raise ToolBootstrapError("invalid Docker archive") from error
    if len(executable) != target.size or len(executable) > DOCKER_BINARY_LIMIT:
        raise ToolBootstrapError("Docker binary size does not match archive")
    selected_temp = (
        temp_directory
        if temp_directory is not None
        else destination.parent / ".tmp"
    )
    _write_executable_atomically(executable, destination, selected_temp)
    return ToolMaterial(
        archive_sha256=_sha256(archive_payload),
        executable_sha256=_sha256(executable),
        byte_size=len(executable),
    )


def parse_upstream_checksum(payload: bytes, expected_filename: str) -> str:
    """Parse a one-line SHA-256 sidecar bound to the expected asset name."""
    if type(payload) is not bytes or len(payload) > CHECKSUM_LIMIT:
        raise ToolBootstrapError("invalid checksum payload")
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise ToolBootstrapError("checksum must be ASCII") from error
    lines = text.splitlines()
    if len(lines) != 1:
        raise ToolBootstrapError("checksum must contain exactly one line")
    match = _CHECKSUM_LINE.fullmatch(lines[0])
    if match is None:
        raise ToolBootstrapError("checksum line is malformed")
    filename = match.group(2)
    if filename is not None and filename != expected_filename:
        raise ToolBootstrapError("checksum filename does not match asset")
    return match.group(1)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def write_content_lock(
    lock_path: Path,
    profile_path: Path,
    records: Mapping[str, ToolRecord],
) -> None:
    """Atomically write a canonical local content lock."""
    if not records or any(name not in _TOOL_URL_FIELDS for name in records):
        raise ToolBootstrapError("content lock contains an unknown tool")
    document = {
        "schema_version": LOCK_SCHEMA_VERSION,
        "profile_sha256": _sha256(profile_path.read_bytes()),
        "tools": {
            name: asdict(record) for name, record in sorted(records.items())
        },
    }
    payload = _canonical_json(document) + b"\n"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=lock_path.parent,
            prefix=f".{lock_path.name}.",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, lock_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _load_lock(lock_path: Path) -> tuple[str, dict[str, ToolRecord]]:
    try:
        raw = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ToolBootstrapError("cannot read V3B content lock") from error
    if type(raw) is not dict or set(raw) != {
        "schema_version",
        "profile_sha256",
        "tools",
    }:
        raise ToolBootstrapError("content lock has an invalid schema")
    if raw["schema_version"] != LOCK_SCHEMA_VERSION:
        raise ToolBootstrapError("content lock has an invalid schema version")
    if type(raw["profile_sha256"]) is not str or not _DIGEST.fullmatch(
        raw["profile_sha256"]
    ):
        raise ToolBootstrapError("content lock profile hash is invalid")
    raw_tools = raw["tools"]
    if type(raw_tools) is not dict or not raw_tools:
        raise ToolBootstrapError("content lock must contain tools")
    expected_fields = {field.name for field in fields(ToolRecord)}
    records: dict[str, ToolRecord] = {}
    for name, value in raw_tools.items():
        if name not in _TOOL_URL_FIELDS or type(value) is not dict:
            raise ToolBootstrapError("content lock contains an unknown tool")
        if set(value) != expected_fields:
            raise ToolBootstrapError(f"{name} content lock fields are invalid")
        records[name] = ToolRecord(**value)
    return raw["profile_sha256"], records


VersionRunner = Callable[[str, Path], str]


def capture_version(name: str, binary_path: Path) -> str:
    if name not in _VERSION_ARGUMENTS:
        raise ToolBootstrapError("cannot capture version for unknown tool")
    try:
        completed = subprocess.run(
            [str(binary_path), *_VERSION_ARGUMENTS[name]],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env={"LANG": "C", "LC_ALL": "C", "PATH": os.defpath},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ToolBootstrapError(f"{name} version command failed") from error
    output = (completed.stdout + completed.stderr).strip()
    if not output or len(output.encode("utf-8")) > VERSION_OUTPUT_LIMIT:
        raise ToolBootstrapError(f"{name} version output is invalid")
    if _VERSION_MARKERS[name] not in output:
        raise ToolBootstrapError(f"{name} version does not match V3B profile")
    return output


def verify_content_lock(
    lock_path: Path,
    profile_path: Path,
    tools_root: Path,
    *,
    version_runner: VersionRunner = capture_version,
    require_complete: bool = False,
) -> dict[str, ToolRecord]:
    """Verify profile, bytes, modes, and live version output against the lock."""
    profile = V3BProfile.load(profile_path)
    locked_profile_hash, records = _load_lock(lock_path)
    if locked_profile_hash != _sha256(profile_path.read_bytes()):
        raise ToolBootstrapError("content lock profile hash does not match")
    if require_complete and set(records) != set(_TOOL_URL_FIELDS):
        raise ToolBootstrapError("content lock is not complete")
    for name, record in sorted(records.items()):
        expected_url = getattr(profile, _TOOL_URL_FIELDS[name])
        if record.source_url != expected_url:
            raise ToolBootstrapError(f"{name} source URL does not match profile")
        binary = tools_root / "bin" / name
        if binary.is_symlink() or not binary.is_file():
            raise ToolBootstrapError(f"{name} binary is missing or unsafe")
        payload = binary.read_bytes()
        if _sha256(payload) != record.executable_sha256:
            raise ToolBootstrapError(f"{name} executable hash does not match lock")
        if len(payload) != record.byte_size:
            raise ToolBootstrapError(f"{name} executable size does not match lock")
        if stat.S_IMODE(binary.stat().st_mode) != 0o755:
            raise ToolBootstrapError(f"{name} executable mode does not match lock")
        current_version = version_runner(name, binary)
        if current_version != record.version_output:
            raise ToolBootstrapError(f"{name} version output does not match lock")
        if _VERSION_MARKERS[name] not in current_version:
            raise ToolBootstrapError(f"{name} version does not match V3B profile")
    return records


def _prepare_tools_root(root: Path) -> tuple[Path, Path, Path]:
    repository = root.resolve()
    tools_root = repository / ".tools"
    if tools_root.exists() and tools_root.is_symlink():
        raise ToolBootstrapError(".tools must not be a symbolic link")
    if tools_root.parent != repository:
        raise ToolBootstrapError(".tools must be under the repository root")
    bin_directory = tools_root / "bin"
    temp_directory = tools_root / "tmp"
    lock_directory = tools_root / "locks"
    for directory in (tools_root, bin_directory, temp_directory, lock_directory):
        if directory.exists() and directory.is_symlink():
            raise ToolBootstrapError(f"{directory.name} must not be a symbolic link")
        directory.mkdir(parents=True, exist_ok=True)
    return tools_root, bin_directory, temp_directory


def bootstrap(root: Path = ROOT) -> Path:
    """Download, verify, install, version-check, and lock the three V3B tools."""
    profile_path = root / "deploy/kind/v3b-profile.json"
    profile = V3BProfile.load(profile_path)
    tools_root, bin_directory, temp_directory = _prepare_tools_root(root)

    docker_archive = download_bounded(
        profile.docker_cli_url,
        DOCKER_ARCHIVE_LIMIT,
    )
    kind_binary = download_bounded(profile.kind_url, DIRECT_BINARY_LIMIT)
    kind_checksum_payload = download_bounded(
        profile.kind_checksum_url,
        CHECKSUM_LIMIT,
    )
    kubectl_binary = download_bounded(profile.kubectl_url, DIRECT_BINARY_LIMIT)
    kubectl_checksum_payload = download_bounded(
        profile.kubectl_checksum_url,
        CHECKSUM_LIMIT,
    )

    kind_checksum = parse_upstream_checksum(
        kind_checksum_payload,
        Path(profile.kind_url).name,
    )
    kubectl_checksum = parse_upstream_checksum(
        kubectl_checksum_payload,
        Path(profile.kubectl_url).name,
    )

    materials = {
        "docker": extract_docker_cli(
            docker_archive,
            bin_directory / "docker",
            temp_directory=temp_directory,
        ),
        "kind": install_direct_binary(
            kind_binary,
            kind_checksum,
            bin_directory / "kind",
            temp_directory=temp_directory,
        ),
        "kubectl": install_direct_binary(
            kubectl_binary,
            kubectl_checksum,
            bin_directory / "kubectl",
            temp_directory=temp_directory,
        ),
    }

    records: dict[str, ToolRecord] = {}
    for name in ("docker", "kind", "kubectl"):
        material = materials[name]
        records[name] = ToolRecord(
            source_url=getattr(profile, _TOOL_URL_FIELDS[name]),
            archive_sha256=material.archive_sha256,
            executable_sha256=material.executable_sha256,
            byte_size=material.byte_size,
            version_output=capture_version(name, bin_directory / name),
            checksum_attestation=(
                "locally_observed" if name == "docker" else "upstream_sidecar"
            ),
        )

    lock_path = tools_root / "locks/v3b-tools.json"
    write_content_lock(lock_path, profile_path, records)
    verify_content_lock(
        lock_path,
        profile_path,
        tools_root,
        require_complete=True,
    )
    return lock_path


def verify(root: Path = ROOT) -> Path:
    tools_root, _, _ = _prepare_tools_root(root)
    profile_path = root / "deploy/kind/v3b-profile.json"
    lock_path = tools_root / "locks/v3b-tools.json"
    verify_content_lock(
        lock_path,
        profile_path,
        tools_root,
        require_complete=True,
    )
    return lock_path


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "verify"))
    args = parser.parse_args()
    try:
        lock_path = bootstrap() if args.command == "install" else verify()
    except ToolBootstrapError as error:
        parser.error(str(error))
    print(lock_path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
