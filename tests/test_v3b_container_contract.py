from hashlib import sha256
from pathlib import Path
import shlex
import tempfile
import unittest

from tools.v3b1_local_envoy import (
    _BUILD_CONTEXT_FILES,
    driver_bootstrap_sha256,
    stage_build_context,
)


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "deploy/kind/Dockerfile.v3b"
DOCKERIGNORE = ROOT / "deploy/kind/Dockerfile.v3b.dockerignore"
BUILD_LOCK = ROOT / "deploy/kind/requirements-v3b-build.txt"
RUNTIME_LOCK = ROOT / "deploy/kind/requirements-v3b-runtime.txt"

EXPECTED_CONTEXT_INPUTS = {
    "README.md",
    "deploy/kind/requirements-v3b-build.txt",
    "deploy/kind/requirements-v3b-runtime.txt",
    "pyproject.toml",
    "src/kil/__init__.py",
    "src/kil/canonical.py",
    "src/kil/decay.py",
    "src/kil/domain.py",
    "src/kil/engine.py",
    "src/kil/ext_authz_http.py",
    "src/kil/live_authz.py",
    "src/kil/q_state.py",
    "src/kil/target_http.py",
    "src/kil/v3b1_driver_protocol.py",
    "src/kil/v3b1_request_driver.py",
}

EXPECTED_DOCKERIGNORE_LINES = [
    "**",
    "!README.md",
    "!pyproject.toml",
    "!src/",
    "!src/kil/",
    "!src/kil/__init__.py",
    "!src/kil/canonical.py",
    "!src/kil/decay.py",
    "!src/kil/domain.py",
    "!src/kil/engine.py",
    "!src/kil/ext_authz_http.py",
    "!src/kil/live_authz.py",
    "!src/kil/q_state.py",
    "!src/kil/target_http.py",
    "!src/kil/v3b1_driver_protocol.py",
    "!src/kil/v3b1_request_driver.py",
    "!deploy/",
    "!deploy/kind/",
    "!deploy/kind/Dockerfile.v3b",
    "!deploy/kind/Dockerfile.v3b.dockerignore",
    "!deploy/kind/requirements-v3b-build.txt",
    "!deploy/kind/requirements-v3b-runtime.txt",
]

EXPECTED_BUILD_LOCK_LINES = [
    "setuptools==82.0.0 \\",
    "    --hash=sha256:70b18734b607bd1da571d097d236cfcfacaf01de45717d59e6e04b96877532e0",
]

EXPECTED_RUNTIME_LOCK_LINES = [
    "cffi==2.1.1 \\",
    "    --hash=sha256:68e62fe11f30d5ca8289242866f0a5291402d8529ca2178ab8afc5c9694ae890",
    "cryptography==50.0.0 \\",
    "    --hash=sha256:fd9192b7b70c573d7f214eb1ae35e00d359f6f5e4b27c7e21e30de1fc6204645 \\",
    "    --hash=sha256:a1b30560f2acc95aa8b2e06e716a13dbfc97314747b80d9707e307f77b40d6b3 \\",
    "    --hash=sha256:07949c449a1abcf60d1ee6e88956d89404c7df3c8258f46589e912988e551987",
    "pycparser==3.0 \\",
    "    --hash=sha256:b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992",
]


def logical_instructions(text: str) -> list[str]:
    instructions: list[str] = []
    pending = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pending = f"{pending} {stripped}".strip()
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        instructions.append(pending)
        pending = ""
    if pending:
        instructions.append(pending)
    return instructions


def context_copy_sources(instructions: list[str]) -> set[str]:
    sources: set[str] = set()
    for instruction in instructions:
        tokens = shlex.split(instruction)
        if not tokens or tokens[0].upper() != "COPY":
            continue
        arguments = tokens[1:]
        if any(argument.startswith("--from=") for argument in arguments):
            continue
        while arguments and arguments[0].startswith("--"):
            arguments.pop(0)
        if len(arguments) < 2:
            raise AssertionError(f"invalid COPY instruction: {instruction}")
        sources.update(arguments[:-1])
    return sources


class V3BContainerContractTest(unittest.TestCase):
    def artifact_text(self, path: Path) -> str:
        self.assertTrue(
            path.is_file(), f"required container artifact is missing: {path}"
        )
        text = path.read_text(encoding="utf-8")
        self.assertTrue(
            text.endswith("\n"), f"container artifact needs final newline: {path}"
        )
        return text

    def dockerfile(self) -> tuple[str, list[str]]:
        text = self.artifact_text(DOCKERFILE)
        return text, logical_instructions(text)

    def test_base_is_only_the_externally_supplied_digest_pinned_argument(self):
        _, instructions = self.dockerfile()

        self.assertEqual(instructions[:2], [
            "ARG PYTHON_BASE_IMAGE",
            "FROM ${PYTHON_BASE_IMAGE}",
        ])
        self.assertEqual(
            [line for line in instructions if line.startswith("FROM ")],
            ["FROM ${PYTHON_BASE_IMAGE}", "FROM ${PYTHON_BASE_IMAGE}"],
        )

    def test_context_copy_is_an_exact_runtime_dependency_allowlist(self):
        _, instructions = self.dockerfile()

        sources = context_copy_sources(instructions)

        self.assertEqual(sources, EXPECTED_CONTEXT_INPUTS)
        self.assertFalse(any(line.startswith("ADD ") for line in instructions))
        self.assertFalse(
            any(source in {".", "./", "..", "../"} for source in sources)
        )
        self.assertFalse(
            any("*" in source or "?" in source for source in sources)
        )
        for forbidden in (
            ".git",
            ".tools",
            "artifact",
            "config",
            "credential",
            "evidence",
            "ledger",
            "private",
            "transition",
        ):
            self.assertFalse(
                any(forbidden in source.lower() for source in sources),
                f"build context COPY must exclude {forbidden}",
            )

    def test_staged_context_attests_exact_driver_module_bytes_as_bootstrap(self):
        expected_files = tuple(sorted(EXPECTED_CONTEXT_INPUTS | {
            "deploy/kind/Dockerfile.v3b",
            "deploy/kind/Dockerfile.v3b.dockerignore",
        }))
        self.assertEqual(tuple(sorted(_BUILD_CONTEXT_FILES)), expected_files)
        with tempfile.TemporaryDirectory() as directory:
            attestation = stage_build_context(ROOT, Path(directory) / "context")

        expected = sha256(
            (ROOT / "src/kil/v3b1_request_driver.py").read_bytes()
        ).hexdigest()
        self.assertEqual(driver_bootstrap_sha256(attestation), expected)
        self.assertEqual(
            attestation["file_sha256"]["src/kil/v3b1_request_driver.py"],
            expected,
        )

    def test_dockerfile_specific_ignore_is_a_closed_root_context_allowlist(self):
        lines = self.artifact_text(DOCKERIGNORE).splitlines()

        self.assertEqual(lines, EXPECTED_DOCKERIGNORE_LINES)
        self.assertEqual(lines[0], "**")

    def test_external_build_and_runtime_packages_are_exactly_hash_locked(self):
        build_lines = self.artifact_text(BUILD_LOCK).splitlines()
        runtime_lines = self.artifact_text(RUNTIME_LOCK).splitlines()

        self.assertEqual(build_lines, EXPECTED_BUILD_LOCK_LINES)
        self.assertEqual(runtime_lines, EXPECTED_RUNTIME_LOCK_LINES)

    def test_locked_binary_dependencies_precede_isolated_project_install(self):
        text, instructions = self.dockerfile()

        installs = [
            line
            for line in instructions
            if line.startswith("RUN ") and " pip install " in f" {line} "
        ]
        self.assertEqual(len(installs), 3)
        for install in installs:
            self.assertIn("python -m pip install", install)
            self.assertIn("--no-cache-dir", install)
            self.assertIn("--no-compile", install)

        build_installs = [
            line for line in installs if "requirements-v3b-build.txt" in line
        ]
        runtime_installs = [
            line for line in installs if "requirements-v3b-runtime.txt" in line
        ]
        project_installs = [line for line in installs if ".[lab]" in line]
        self.assertEqual(len(build_installs), 1)
        self.assertEqual(len(runtime_installs), 1)
        self.assertEqual(len(project_installs), 1)
        build_install = build_installs[0]
        runtime_install = runtime_installs[0]
        project_install = project_installs[0]

        for locked_install in (build_install, runtime_install):
            self.assertIn("--require-hashes", locked_install)
            self.assertIn("--only-binary=:all:", locked_install)
        self.assertNotIn("--prefix=/install", build_install)
        self.assertIn("--prefix=/install", runtime_install)
        self.assertIn("--prefix=/install", project_install)
        self.assertIn("--no-deps", project_install)
        self.assertIn("--no-build-isolation", project_install)
        self.assertNotIn("--require-hashes", project_install)
        self.assertNotIn("--only-binary", project_install)
        self.assertLess(
            instructions.index(build_install), instructions.index(project_install)
        )
        self.assertLess(
            instructions.index(runtime_install), instructions.index(project_install)
        )
        self.assertNotIn("requirements-lab.txt", text)
        for forbidden in (" apt ", " apt-get ", " apk ", " dnf ", " yum "):
            self.assertNotIn(forbidden, f" {text.lower()} ")

    def test_build_tools_and_sources_do_not_survive_into_the_runtime_stage(self):
        _, instructions = self.dockerfile()

        second_from = [
            index for index, line in enumerate(instructions) if line.startswith("FROM ")
        ][1]
        runtime = "\n".join(instructions[second_from:])

        self.assertIn("COPY --from=0 /install/ /usr/local/", runtime)
        for forbidden in (
            " apt ",
            " apt-get ",
            " apk ",
            " dnf ",
            " gcc",
            " make ",
            " pip install ",
            " yum ",
        ):
            self.assertNotIn(forbidden, f" {runtime.lower()} ")

    def test_numeric_non_root_identity_is_created_and_selected(self):
        text, instructions = self.dockerfile()

        self.assertIn("groupadd --gid 65532 kil", text)
        self.assertIn(
            "useradd --uid 65532 --gid 65532 --no-create-home "
            "--home-dir /nonexistent --shell /usr/sbin/nologin kil",
            text,
        )
        self.assertEqual(
            [line for line in instructions if line.startswith("USER ")],
            ["USER 65532:65532"],
        )

    def test_runtime_is_compatible_with_a_read_only_root_filesystem(self):
        text, instructions = self.dockerfile()

        self.assertIn("PYTHONDONTWRITEBYTECODE=1", text)
        self.assertIn("PIP_NO_CACHE_DIR=1", text)
        self.assertNotIn("VOLUME ", text)
        self.assertFalse(
            any(
                line.startswith("RUN ")
                for line in instructions[
                    max(
                        index
                        for index, line in enumerate(instructions)
                        if line.startswith("USER ")
                    )
                    + 1 :
                ]
            )
        )

    def test_only_the_service_port_is_exposed(self):
        _, instructions = self.dockerfile()

        self.assertEqual(
            [line for line in instructions if line.startswith("EXPOSE ")],
            ["EXPOSE 8080"],
        )

    def test_healthcheck_uses_python_stdlib_for_either_health_endpoint(self):
        text, instructions = self.dockerfile()

        healthchecks = [
            line for line in instructions if line.startswith("HEALTHCHECK ")
        ]
        self.assertEqual(len(healthchecks), 1)
        healthcheck = healthchecks[0]
        self.assertIn("http.client", healthcheck)
        self.assertIn("127.0.0.1", healthcheck)
        self.assertIn("8080", healthcheck)
        self.assertIn("/healthz", healthcheck)
        self.assertIn("response.status != 200", healthcheck)
        self.assertNotIn("curl", text.lower())
        self.assertNotIn("wget", text.lower())

    def test_controller_must_supply_either_module_command_and_mounted_config(self):
        text, instructions = self.dockerfile()

        self.assertFalse(any(line.startswith("CMD ") for line in instructions))
        self.assertFalse(any(line.startswith("ENTRYPOINT ") for line in instructions))
        self.assertNotIn("kil.ext_authz_http", text)
        self.assertNotIn("kil.target_http", text)
        for private_material in ("--config", ".pem", ".key", "private_key"):
            self.assertNotIn(private_material, text.lower())


if __name__ == "__main__":
    unittest.main()
