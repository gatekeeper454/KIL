from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest

from kil.v3b_preflight import V3BProfile
from tools.bootstrap_v3b_tools import (
    ToolBootstrapError,
    ToolRecord,
    download_bounded,
    extract_docker_cli,
    install_direct_binary,
    parse_upstream_checksum,
    validate_download_url,
    verify_content_lock,
    write_content_lock,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "deploy/kind/v3b-profile.json"


class FakeResponse(BytesIO):
    def __init__(self, payload: bytes, final_url: str):
        super().__init__(payload)
        self._final_url = final_url

    def geturl(self) -> str:
        return self._final_url


def tar_archive(
    members: list[tuple[str, bytes, bytes | None]],
) -> bytes:
    """Build test archives from (name, payload, link_target) entries."""
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, payload, link_target in members:
            info = tarfile.TarInfo(name)
            if link_target is not None:
                info.type = tarfile.SYMTYPE
                info.linkname = link_target.decode("utf-8")
                archive.addfile(info)
            else:
                info.size = len(payload)
                info.mode = 0o777
                archive.addfile(info, BytesIO(payload))
    return output.getvalue()


class V3BToolBootstrapTest(unittest.TestCase):
    def setUp(self):
        self.profile = V3BProfile.load(PROFILE_PATH)

    def test_rejects_a_non_allowlisted_download_host(self):
        with self.assertRaisesRegex(ToolBootstrapError, "allowlisted"):
            validate_download_url("https://example.invalid/docker.tgz")

    def test_accepts_only_an_exact_url_from_the_profile(self):
        self.assertEqual(
            validate_download_url(self.profile.kind_url),
            self.profile.kind_url,
        )
        with self.assertRaisesRegex(ToolBootstrapError, "profile"):
            validate_download_url(
                "https://github.com/example/example/releases/download/tool"
            )

    def test_bounded_download_rejects_oversize_content(self):
        payload = b"x" * 9

        def opener(url: str, timeout: float):
            return FakeResponse(payload, url)

        with self.assertRaisesRegex(ToolBootstrapError, "size limit"):
            download_bounded(self.profile.kind_url, 8, opener=opener)

    def test_bounded_download_rejects_unapproved_redirects(self):
        def opener(url: str, timeout: float):
            return FakeResponse(b"binary", "https://example.invalid/binary")

        with self.assertRaisesRegex(ToolBootstrapError, "redirect"):
            download_bounded(self.profile.kind_url, 64, opener=opener)

    def test_checksum_mismatch_never_replaces_existing_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "bin/kind"
            destination.parent.mkdir()
            destination.write_bytes(b"known-good")

            with self.assertRaisesRegex(ToolBootstrapError, "checksum"):
                install_direct_binary(
                    b"tampered",
                    "0" * 64,
                    destination,
                    temp_directory=root / "tmp",
                )

            self.assertEqual(destination.read_bytes(), b"known-good")

    def test_verified_direct_binary_is_atomic_and_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "bin/kubectl"
            payload = b"verified-binary"

            material = install_direct_binary(
                payload,
                sha256(payload).hexdigest(),
                destination,
                temp_directory=root / "tmp",
            )

            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o755)
            self.assertEqual(material.executable_sha256, sha256(payload).hexdigest())
            self.assertEqual(material.byte_size, len(payload))

    def test_docker_archive_rejects_traversal_members(self):
        archive = tar_archive(
            [("../escape", b"bad", None), ("docker/docker", b"good", None)]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ToolBootstrapError, "archive member"):
                extract_docker_cli(
                    archive,
                    root / "bin/docker",
                    temp_directory=root / "tmp",
                )

    def test_docker_archive_rejects_links(self):
        archive = tar_archive(
            [("docker/docker", b"", b"../../outside")]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ToolBootstrapError, "archive member"):
                extract_docker_cli(
                    archive,
                    root / "bin/docker",
                    temp_directory=root / "tmp",
                )

    def test_docker_archive_extracts_only_the_literal_docker_binary(self):
        archive = tar_archive(
            [
                ("docker/docker", b"docker-cli", None),
                ("docker/dockerd", b"daemon", None),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "bin/docker"

            material = extract_docker_cli(
                archive,
                destination,
                temp_directory=root / "tmp",
            )

            self.assertEqual(destination.read_bytes(), b"docker-cli")
            self.assertFalse((root / "bin/dockerd").exists())
            self.assertEqual(material.archive_sha256, sha256(archive).hexdigest())

    def test_docker_archive_rejects_duplicate_target_members(self):
        archive = tar_archive(
            [
                ("docker/docker", b"first", None),
                ("docker/docker", b"second", None),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ToolBootstrapError, "exactly one"):
                extract_docker_cli(
                    archive,
                    root / "bin/docker",
                    temp_directory=root / "tmp",
                )

    def test_parses_release_specific_checksum_formats(self):
        digest = "a" * 64
        self.assertEqual(
            parse_upstream_checksum(
                f"{digest}  kind-darwin-arm64\n".encode(),
                "kind-darwin-arm64",
            ),
            digest,
        )
        self.assertEqual(
            parse_upstream_checksum(f"{digest}\n".encode(), "kubectl"),
            digest,
        )

    def test_rejects_a_checksum_for_another_asset(self):
        with self.assertRaisesRegex(ToolBootstrapError, "filename"):
            parse_upstream_checksum(
                (("a" * 64) + "  kind-linux-amd64\n").encode(),
                "kind-darwin-arm64",
            )

    def test_lock_is_canonical_and_detects_binary_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools_root = root / ".tools"
            binary = tools_root / "bin/docker"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"docker")
            os.chmod(binary, 0o755)
            digest = sha256(b"docker").hexdigest()
            record = ToolRecord(
                source_url=self.profile.docker_cli_url,
                archive_sha256="b" * 64,
                executable_sha256=digest,
                byte_size=6,
                version_output="Docker version 29.7.2",
                checksum_attestation="locally_observed",
            )
            profile_copy = root / "v3b-profile.json"
            profile_copy.write_bytes(PROFILE_PATH.read_bytes())
            lock_path = tools_root / "locks/v3b-tools.json"

            write_content_lock(
                lock_path,
                profile_copy,
                {"docker": record},
            )

            encoded = lock_path.read_bytes()
            self.assertTrue(encoded.endswith(b"\n"))
            self.assertEqual(
                encoded,
                json.dumps(
                    json.loads(encoded),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                + b"\n",
            )
            binary.write_bytes(b"tampered")
            with self.assertRaisesRegex(ToolBootstrapError, "docker.*hash"):
                verify_content_lock(
                    lock_path,
                    profile_copy,
                    tools_root,
                    version_runner=lambda name, path: "Docker version 29.7.2",
                )

    def test_repository_contract_keeps_tools_local_and_command_scoped(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

        self.assertIn(".tools/", ignore.splitlines())
        self.assertIn("v3b-tools:", makefile)
        self.assertIn("v3b-preflight:", makefile)
        self.assertIn('PATH="$(CURDIR)/.tools/bin:$$PATH"', makefile)
        self.assertNotIn("docker context use", makefile)
        self.assertNotIn(".zshrc", makefile)


if __name__ == "__main__":
    unittest.main()
