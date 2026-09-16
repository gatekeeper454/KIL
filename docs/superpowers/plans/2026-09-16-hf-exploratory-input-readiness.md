# Exploratory HF input readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify and retain the existing accepted application archive and tool bytes without any runtime mutation or platform-image admission.

**Architecture:** This is the first independently testable unit of the approved exploratory design. A pure input factory reads the checksum-pinned accepted manifest, the fixed target profile, the three accepted tool executables, and the accepted KIL archive. Subsequent lifecycle and evidence units consume its retained bytes and commitments; this unit cannot launch a lab or establish readiness.

**Tech Stack:** Python 3.12 standard library, existing V3B2 profile/manifest/image contracts, unittest.

---

Approved scope: docs/superpowers/specs/2026-09-16-hf-exploratory-kind-calico-design.md, approved by "approved proceed". User has already authorized the future run when ready; do not ask again between safe in-scope implementation units. The platform-image audit stays stopped. No strict controller, profile, verifier or lifecycle deferral changes.

Repository: /Users/mistorm/.codex/worktrees/6a01/Kinetic Infrastructure Layer - KIL (existing host-managed detached linked worktree; do not create another).

Interpreter: /Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python.

## Task 1: Retained input factory

Files:

- Create src/kil/hf_exploratory_inputs.py: bounded immutable input verification only.
- Create tests/test_hf_exploratory_inputs.py: test-owned byte checks and native accepted-manifest rejection tests.
- Preserve all existing source files.

- [ ] Write these failing tests before implementation:

```python
from hashlib import sha256
import importlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


class ExploratoryInputsTest(unittest.TestCase):
    def setUp(self):
        name = 'kil.hf_exploratory_inputs'
        self.assertIsNotNone(importlib.util.find_spec(name), 'exploratory inputs missing')
        self.module = importlib.import_module(name)

    def test_read_retains_exact_bytes_and_enforces_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'blob'
            path.write_bytes(b'abc')
            self.assertEqual(self.module.read_regular(path, 3), b'abc')
            with self.assertRaises(ValueError):
                self.module.read_regular(path, 2)

    def test_read_rejects_symlink_and_relative_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'blob'
            path.write_bytes(b'abc')
            link = path.with_name('link')
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                self.module.read_regular(link, 3)
        with self.assertRaises(ValueError):
            self.module.read_regular(Path('relative'), 3)

    def test_content_verification_rejects_same_size_substitution(self):
        expected = sha256(b'abc').hexdigest()
        self.assertEqual(self.module.verify_bytes(b'abc', expected, 3), expected)
        for payload, size in ((b'abd', 3), (b'abc', 2)):
            with self.subTest(payload=payload, size=size), self.assertRaises(ValueError):
                self.module.verify_bytes(payload, expected, size)

    def test_size_and_digest_types_are_exact(self):
        for size in (True, 3.0, '3', -1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                self.module.verify_bytes(b'abc', sha256(b'abc').hexdigest(), size)
        with self.assertRaises(ValueError):
            self.module.verify_bytes(b'abc', 'A' * 64, 3)

    def test_missing_native_inputs_fail_without_commands(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve()
            with self.assertRaises(ValueError):
                self.module.verify_inputs(root, path, path / 'missing.tar', 'a' * 64)


if __name__ == '__main__':
    unittest.main()
```

- [ ] Run RED:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -m unittest tests.test_hf_exploratory_inputs -v
```

Expected: five assertion failures for the absent module, no live command.

- [ ] Implement this complete module. Further tests discovered during review must precede any corresponding correction.

```python
"""Retained accepted inputs for the explicitly nonpromotable HF experiment."""
from dataclasses import dataclass
from hashlib import sha256
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
    'docker': ('--version',), 'kind': ('version',),
    'kubectl': ('version', '--client', '-o', 'json'),
}


def read_regular(path, maximum):
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.resolve() != path or type(maximum) is not int or maximum < 1):
        raise ValueError('unsafe_input_path_or_bound')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ValueError('input_not_regular_or_oversized')
        with os.fdopen(os.dup(descriptor), 'rb') as stream:
            payload = stream.read(maximum + 1)
        after = os.fstat(descriptor)
        if (len(payload) != before.st_size or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ValueError('input_changed_during_read')
        return payload
    finally:
        os.close(descriptor)


def verify_bytes(payload, digest, byte_size):
    if (type(payload) is not bytes or type(byte_size) is not int or byte_size < 0
            or type(digest) is not str or re.fullmatch('[0-9a-f]{64}', digest) is None
            or len(payload) != byte_size or sha256(payload).hexdigest() != digest):
        raise ValueError('input_content_mismatch')
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


def verify_inputs(repository, tools, archive_path, run_digest):
    if type(run_digest) is not str or re.fullmatch('[0-9a-f]{64}', run_digest) is None:
        raise ValueError('invalid_exploratory_run_digest')
    try:
        profile_bytes = read_regular(repository / 'deploy/kind/v3b2-profile.json', 65536)
        profile = V3B2Profile.from_mapping(json.loads(profile_bytes))
        manifest_bytes = read_regular(repository / 'artifacts/generated/v3b1-local-envoy'
                                      / ACCEPTED_RUN / 'manifest.json', 1024 * 1024)
        verify_bytes(manifest_bytes, ACCEPTED_MANIFEST_SHA256, len(manifest_bytes))
        manifest = json.loads(manifest_bytes)
        images = manifest['immutable_images']
        workload = WorkloadIdentity('v3b2-' + run_digest,
                                    images['kil_image_id'], images['envoy_digest'])
        accepted = {row.role: row for row in ACCEPTED_IMAGES}
        if (workload.kil_image_id != accepted['kil'].target_digest
                or workload.envoy_image_digest != accepted['envoy'].requested_image
                or images['kil_archive_sha256'] != ARCHIVE_SHA256):
            raise ValueError('accepted_application_identity_mismatch')
        records = manifest['verified_tool_identities']
        if set(records) != set(TOOL_VERSION_ARGUMENTS):
            raise ValueError('accepted_tool_set_mismatch')
        for name, row in records.items():
            binary = tools / name
            payload = read_regular(binary, 128 * 1024 * 1024)
            verify_bytes(payload, row['executable_sha256'], row['byte_size'])
            if not binary.stat().st_mode & stat.S_IXUSR:
                raise ValueError('tool_not_executable')
        archive = read_regular(archive_path, 1024 * 1024 * 1024)
        verify_bytes(archive, ARCHIVE_SHA256, len(archive))
        return ExploratoryInputs(profile, profile_bytes, workload, archive,
                                 tools, records, manifest_bytes)
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError('exploratory_inputs_unavailable_or_invalid') from error
```

- [ ] Run GREEN with the same unittest command. Expected: five tests pass.
- [ ] Independently review specification compliance, then code quality; fix issues through RED/GREEN. No lab command is authorized by this task.
- [ ] Verify the real retained inputs read-only, using the factory after review:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src '/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.venv/bin/python' -c "from pathlib import Path; from kil.hf_exploratory_inputs import verify_inputs; value=verify_inputs(Path.cwd(), Path('/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.tools/bin'), Path('/Users/mistorm/Documents/AI-Projects/Kinetic Infrastructure Layer - KIL/.worktrees/v3b1-central-proof-v3-rerun/.tools/v3b1-staging/build/a259a3868ced74afb101807fc37c4fd05e37ffff92a21b3922e986dafb32fc3b/kil-image.tar'), 'a'*64); print('accepted_application_and_three_tools_verified; runtime_readiness_unestablished')"
```

Expected exact output: accepted_application_and_three_tools_verified; runtime_readiness_unestablished. This retains native bytes but neither invokes the images nor asserts platform provenance.

- [ ] Commit only the new module/tests and required dated lineage entry/readers after fresh tests, reader check and diff hygiene. Suggested message: feat: verify retained exploratory HF application inputs.

## Dependency handoff

The lifecycle plan must consume ExploratoryInputs without caller override of expected hashes. It must attest exact version output at execution, recheck executable commitments before each command, establish clean reviewed source, journal ownership and request intent, and bound command output/time. The evidence plan must join complete frozen sources and refuse success for uncertainty. These are separate dependent units under the already approved design, not work implemented or claimed by this input-only plan. Root proceeds to their concrete plans without reopening the platform-image audit or seeking another routine continuation approval.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
