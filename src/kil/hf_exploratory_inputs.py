"""Pure accepted-input readiness for the separate HF exploratory path.

Retained bytes establish input identity only, never native runtime readiness.
This module does not invoke tools or mutate lifecycle state.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from kil.v3b2_accepted_images import ACCEPTED_IMAGES, ACCEPTED_MANIFEST_SHA256
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_manifests import WorkloadIdentity


ACCEPTED_RUN = 'v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94'
ARCHIVE_SHA256 = '07c12f338c7d764812ef6271ec8942f0535d05019288f4df1e1b54f6cd75e4b6'
IMAGE_CONFIGS = {row.role: row.config_digest for row in ACCEPTED_IMAGES}
TOOL_VERSION_ARGUMENTS = {
    'docker': ('--version',),
    'kind': ('version',),
    'kubectl': ('version', '--client', '-o', 'json'),
}
_DIGEST = re.compile(r'[0-9a-f]{64}')


def read_regular(path: Path, maximum: int) -> bytes:
    """Read a bounded canonical nonsymlink file and reject concurrent changes."""
    if (not isinstance(path, Path) or type(maximum) is not int or maximum <= 0
            or not path.is_absolute() or path.is_symlink()
            or path.resolve(strict=True) != path):
        raise ValueError('unsafe_exploratory_input_path_or_bound')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ValueError('exploratory_input_not_bounded_regular_file')
        with os.fdopen(os.dup(descriptor), 'rb') as stream:
            payload = stream.read(maximum + 1)
        after = os.fstat(descriptor)
        identity = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns)
        if identity(before) != identity(after) or len(payload) != before.st_size:
            raise ValueError('exploratory_input_changed_during_read')
        return payload
    finally:
        os.close(descriptor)


def verify_bytes(payload: bytes, digest: str, byte_size: int) -> str:
    """Verify exact retained bytes against an exact lower-case SHA-256 record."""
    if (type(payload) is not bytes or type(byte_size) is not int or byte_size < 0
            or type(digest) is not str or _DIGEST.fullmatch(digest) is None
            or len(payload) != byte_size or hashlib.sha256(payload).hexdigest() != digest):
        raise ValueError('exploratory_input_bytes_do_not_match')
    return digest


@dataclass(frozen=True)
class ExploratoryInputs:
    profile: V3B2Profile
    profile_bytes: bytes
    workload: WorkloadIdentity
    archive: bytes
    tools: Path
    tool_records: dict
    manifest_bytes: bytes


def verify_inputs(repository: Path, tools: Path, archive_path: Path,
                  run_digest: str) -> ExploratoryInputs:
    """Retain accepted inputs without running any executable or native command."""
    if type(run_digest) is not str or _DIGEST.fullmatch(run_digest) is None:
        raise ValueError('invalid_exploratory_run_digest')
    try:
        profile_bytes = read_regular(repository / 'deploy/kind/v3b2-profile.json', 65536)
        profile = V3B2Profile.from_mapping(json.loads(profile_bytes))
        manifest_bytes = read_regular(
            repository / 'artifacts/generated/v3b1-local-envoy' / ACCEPTED_RUN / 'manifest.json',
            1024 * 1024,
        )
        verify_bytes(manifest_bytes, ACCEPTED_MANIFEST_SHA256, len(manifest_bytes))
        manifest = json.loads(manifest_bytes)
        images = manifest['immutable_images']
        workload = WorkloadIdentity('v3b2-' + run_digest, images['kil_image_id'],
                                    images['envoy_digest'])
        accepted = {row.role: row for row in ACCEPTED_IMAGES}
        if (workload.kil_image_id != accepted['kil'].target_digest
                or workload.envoy_image_digest != accepted['envoy'].requested_image
                or images['kil_archive_sha256'] != ARCHIVE_SHA256):
            raise ValueError('exploratory_images_not_accepted')
        tool_records = manifest['verified_tool_identities']
        if type(tool_records) is not dict or set(tool_records) != set(TOOL_VERSION_ARGUMENTS):
            raise ValueError('exploratory_tool_set_not_accepted')
        for name, record in tool_records.items():
            executable = tools / name
            payload = read_regular(executable, 128 * 1024 * 1024)
            verify_bytes(payload, record['executable_sha256'], record['byte_size'])
            if not executable.stat().st_mode & stat.S_IXUSR:
                raise ValueError('exploratory_tool_not_owner_executable')
        archive = read_regular(archive_path, 1024 * 1024 * 1024)
        verify_bytes(archive, ARCHIVE_SHA256, len(archive))
        return ExploratoryInputs(profile, profile_bytes, workload, archive, tools,
                                 tool_records, manifest_bytes)
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError('exploratory_inputs_unavailable_or_invalid') from error
