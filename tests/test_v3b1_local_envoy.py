from hashlib import sha256
import json
from pathlib import Path
import stat
import tempfile
import unittest

from kil.canonical import canonical_json
from kil.live_authz import LiveTrack
from kil.v3b_preflight import V3BProfile
from tools.v3b1_local_envoy import (
    _complete_request_attempt,
    _bind_journal_manifest,
    _prepare_failure_provisional,
    ACTIVE_STATE_PATH,
    authoritative_bundle_attestation,
    CommandResult,
    ControllerError,
    LocalEnvoyController,
    RETRY_CONTROL_HEADERS,
    build_runtime_commands,
    create_run_manifest,
    claim_request_attempt,
    comparison_facts_sha256,
    create_lifecycle_journal,
    collection_commands,
    finalize_teardown_evidence,
    finalize_publication,
    journal_event,
    join_evidence,
    load_bound_active_state,
    load_lifecycle_journal,
    make_parser,
    materialize_run_inputs,
    parse_colima_profiles,
    persist_active_state,
    recovery_plan,
    stage_build_context,
    select_registry_digest,
    teardown_commands,
    validate_container_attestation,
    validate_image_architecture,
    verify_public_checksums,
    validate_colima_profiles,
    validate_dedicated_colima_profile,
    validate_request_journal,
    write_evidence_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE = V3BProfile.load(ROOT / "deploy/kind/v3b-profile.json")
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
PYTHON_DIGEST = f"docker.io/library/python@sha256:{HEX_A}"
ENVOY_DIGEST = f"docker.io/envoyproxy/envoy@sha256:{HEX_B}"
KIL_IMAGE_ID = f"sha256:{HEX_C}"
TOOL_IDENTITIES = {
    name: {
        "archive_sha256": HEX_A,
        "executable_sha256": HEX_B,
        "byte_size": index + 1,
        "version_output": version,
        "checksum_attestation": "upstream_sidecar",
    }
    for index, (name, version) in enumerate(
        (
            ("docker", "Docker version 29.7.2"),
            ("kind", "kind v0.32.0"),
            ("kubectl", "kubectl v1.36.3"),
        )
    )
}
ENGINE_PROVENANCE = {
    "server_version": "29.7.2",
    "api_version": "1.52",
    "git_commit": "abcdef0",
    "go_version": "go1.25.7",
    "os": "linux",
    "architecture": "arm64",
    "kernel_version": "6.12.0",
    "storage_driver": "overlayfs",
    "cgroup_driver": "cgroupfs",
    "cgroup_version": "2",
}


class FakeRunner:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.calls = []

    def run(
        self,
        argv,
        *,
        cwd=None,
        input_text=None,
        env=None,
        timeout_s=30,
    ):
        self.calls.append((list(argv), cwd, input_text, env, timeout_s))
        if self.replies:
            return self.replies.pop(0)
        return CommandResult(0, "", "")


class BuildRunner(FakeRunner):
    def run(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if "build" in argv:
            iid = Path(argv[argv.index("--iidfile") + 1])
            iid.parent.mkdir(parents=True, exist_ok=True)
            iid.write_text(KIL_IMAGE_ID + "\n", encoding="ascii")
            return CommandResult(0, "", "")
        if "inspect" in argv:
            if "{{json .}}" in argv:
                return CommandResult(
                    0, '{"Os":"linux","Architecture":"arm64"}\n', ""
                )
            return CommandResult(0, KIL_IMAGE_ID + "\n", "")
        if "save" in argv:
            archive = Path(argv[argv.index("--output") + 1])
            archive.write_bytes(b"locked-image-archive")
            return CommandResult(0, "", "")
        return CommandResult(1, "", "unexpected command")


def manifest(*, docker_host="unix:///Users/lab/.colima/kil-v3-lab/docker.sock"):
    return create_run_manifest(
        PROFILE,
        profile_sha256=sha256(
            (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
        ).hexdigest(),
        python_image_digest=PYTHON_DIGEST,
        envoy_image_digest=ENVOY_DIGEST,
        kil_image_id=KIL_IMAGE_ID,
        kil_archive_sha256=HEX_A,
        docker_host=docker_host,
    )


def request_record(run_manifest, track, **changes):
    denied = track is LiveTrack.SIGNED_PLUS_LOCAL_REDUCE
    client_digest = (
        "3" * 64
        if denied
        else (
            "1" * 64
            if track is LiveTrack.CREDENTIAL_POLICY_BASELINE
            else "2" * 64
        )
    )
    comparison = {
        "method": "POST",
        "path": "/consequential/admin",
        "authorization_sha256": sha256(
            b"Bearer v3b1-lab-credential"
        ).hexdigest(),
        "adversarial_headers": {
            "x-kil-decision-digest": "f" * 64,
            "x-kil-issuer": "https://attacker.invalid",
            "x-kil-local-evidence": '{"divergence":"0"}',
            "x-kil-mode": "credential_policy_baseline",
            "x-kil-track": "client-selected-track",
            "x-kil-verified-subject": "spiffe://attacker.invalid/workload",
        },
        "retry_control_headers": dict(RETRY_CONTROL_HEADERS),
    }
    value = {
        "schema_version": "kil.v3b1-request.v1",
        "run_id": run_manifest["run_id"],
        "request_id": run_manifest["request_id"],
        "track": track.value,
        "method": "POST",
        "path": "/consequential/admin",
        "attempt_count": 1,
        "retry_observed": False,
        "retry_control_headers": dict(RETRY_CONTROL_HEADERS),
        "authorization_sha256": comparison["authorization_sha256"],
        "q_state_present": track is not LiveTrack.CREDENTIAL_POLICY_BASELINE,
        "q_state_sha256": (
            None
            if track is LiveTrack.CREDENTIAL_POLICY_BASELINE
            else ("4" if track is LiveTrack.SIGNED_STATE_ONLY else "5") * 64
        ),
        "adversarial_headers": comparison["adversarial_headers"],
        "comparison_facts_sha256": comparison_facts_sha256(comparison),
        "send_monotonic_ns": 10,
        "receive_monotonic_ns": 20,
        "client_response_status": 403 if denied else 200,
        "client_decision_digest": client_digest,
    }
    value.update(changes)
    return value


def decision_record(run_manifest, track, *, status, outcome, digest):
    if outcome == "error":
        adapter_reasons = []
        engine_reasons = []
    elif track is LiveTrack.CREDENTIAL_POLICY_BASELINE:
        adapter_reasons = ["baseline_permitted"]
        engine_reasons = []
    elif track is LiveTrack.SIGNED_STATE_ONLY:
        adapter_reasons = []
        engine_reasons = ["permitted"]
    else:
        adapter_reasons = []
        engine_reasons = ["insufficient_charge"]
    return {
        "schema_version": "kil.v3b-authz-record.v1",
        "request_id": run_manifest["request_id"],
        "track": track.value,
        "method": "POST",
        "path": "/consequential/admin",
        "outcome": outcome,
        "http_status": status,
        "decision_digest": digest,
        "adapter_reasons": adapter_reasons,
        "engine_reasons": engine_reasons,
        "untrusted_header_names": [],
        "monotonic_ns": 100,
    }


def envoy_record(run_manifest, track, *, status, upstream, digest):
    return {
        "run_id": run_manifest["run_id"],
        "request_id": run_manifest["request_id"],
        "track": track.value,
        "response_code": str(status),
        "upstream_host": upstream,
        "upstream_service_time": "1" if upstream != "-" else "-",
        "decision_digest": digest,
    }


def target_record(run_manifest, track, digest):
    return {
        "schema_version": "kil.v3b-target-record.v1",
        "run_id": run_manifest["run_id"],
        "request_id": run_manifest["request_id"],
        "track": track.value,
        "path": "/consequential/admin",
        "decision_digest": digest,
        "received_monotonic_ns": 110,
        "response_monotonic_ns": 120,
    }


class ControllerContractTest(unittest.TestCase):
    def test_cli_exposes_only_the_five_approved_subcommands(self):
        parser = make_parser()

        for name in ("preflight", "up", "run", "collect", "down"):
            self.assertEqual(parser.parse_args([name]).command, name)
        with self.assertRaises(SystemExit):
            parser.parse_args(["destroy"])

    def test_colima_and_docker_commands_are_exact_and_context_local(self):
        controller = LocalEnvoyController(
            ROOT,
            FakeRunner(),
            home=Path("/Users/lab"),
            port_probe=lambda port: False,
            tool_verifier=lambda: {},
        )

        self.assertEqual(
            controller.colima_start_command(HEX_A),
            [
                "colima",
                "start",
                "--profile",
                "kil-v3-lab",
                "--runtime",
                "docker",
                "--activate=false",
                "--ssh-config=false",
                "--cpus",
                "4",
                "--memory",
                "8",
                "--disk",
                "60",
                "--vm-type",
                "vz",
                "--kubernetes=false",
                "--arch=aarch64",
                "--save-config=true",
                "--template=false",
                "--binfmt=false",
                "--vz-rosetta=false",
                "--mount-inotify=false",
                "--network-mode=shared",
                "--network-address=false",
                "--network-host-addresses=false",
                "--network-preferred-route=false",
                "--port-forwarder=ssh",
                "--ssh-agent=false",
                "--nested-virtualization=false",
                "--mount",
                str(ROOT / ".tools/v3b1-staging" / HEX_A),
                "--mount-type=virtiofs",
            ],
        )
        encoded_colima = canonical_json(controller.colima_start_command(HEX_A))
        self.assertNotIn("--rosetta=false", encoded_colima)
        self.assertNotIn("--host-addresses=false", encoded_colima)
        docker = controller.docker_command("image", "ls")
        self.assertEqual(
            docker[:5],
            [
                str(ROOT / ".tools/bin/docker"),
                "--config",
                str(ROOT / ".tools/v3b1-docker-config"),
                "--host",
                "unix:///Users/lab/.colima/kil-v3-lab/docker.sock",
            ],
        )
        self.assertNotIn("context", docker)
        for ambient in (
            "DOCKER_CONTEXT",
            "DOCKER_HOST",
            "DOCKER_AUTH_CONFIG",
            "DOCKER_CONFIG",
            "BUILDX_BUILDER",
        ):
            self.assertNotIn(ambient, controller.docker_env)
        self.assertEqual(controller.docker_env["DOCKER_BUILDKIT"], "0")

    def test_preflight_reuses_tool_verifier_and_rejects_other_running_profiles(self):
        verified = []
        runner = FakeRunner(
            [
                CommandResult(0, "colima version 0.10.3\n", ""),
                CommandResult(0, "limactl version 2.2.0\n", ""),
                CommandResult(
                    0,
                    '{"name":"personal","status":"Running","arch":"aarch64",'
                    '"cpus":4,"memory":8589934592,"disk":64424509440,'
                    '"runtime":"docker"}\n',
                    "",
                ),
            ]
        )
        controller = LocalEnvoyController(
            ROOT,
            runner,
            home=Path("/Users/lab"),
            port_probe=lambda port: False,
            tool_verifier=lambda: verified.append(True) or TOOL_IDENTITIES,
        )

        with self.assertRaisesRegex(ControllerError, "non-dedicated"):
            controller.preflight()

        self.assertEqual(verified, [True])
        flattened = [part for call, *_ in runner.calls for part in call]
        self.assertNotIn("start", flattened)

    def test_preflight_profile_parser_is_closed_and_ports_are_fixed(self):
        records = parse_colima_profiles(
            '[{"name":"kil-v3-lab","status":"Stopped","arch":"aarch64",'
            '"cpus":4,"memory":8589934592,"disk":64424509440,'
            '"runtime":"docker"}]'
        )
        validate_colima_profiles(records)
        projected = parse_colima_profiles(
            '{"name":"kil-v3-lab","status":"Stopped","arch":"aarch64",'
            '"cpus":4,"memory":8589934592,"disk":64424509440,"runtime":"docker"}'
        )
        self.assertEqual(projected, records)
        attested = validate_dedicated_colima_profile(
            {
                "name": "kil-v3-lab",
                "status": "Running",
                "arch": "aarch64",
                "cpus": 4,
                "memory": 8589934592,
                "disk": 64424509440,
                "runtime": "docker",
            }
        )
        self.assertEqual(attested["runtime"], "docker")
        self.assertEqual(attested["memory"], 8)
        self.assertEqual(attested["disk"], 60)
        for changed in (
            {"cpus": 2},
            {"memory": 8},
            {"disk": 60},
            {"status": "Stopped"},
            {"runtime": "containerd"},
        ):
            bad = dict(attested)
            bad.update(changed)
            with self.assertRaisesRegex(ControllerError, "dedicated Colima"):
                validate_dedicated_colima_profile(bad)
        with self.assertRaisesRegex(ControllerError, "fields"):
            parse_colima_profiles(
                '[{"name":"kil-v3-lab","status":"Stopped"}]'
            )
        with self.assertRaisesRegex(ControllerError, "non-dedicated"):
            validate_colima_profiles(
                ({"name": "default", "status": "Running"},)
            )
        with self.assertRaisesRegex(ControllerError, "fields"):
            parse_colima_profiles(
                '[{"name":"kil-v3-lab","status":"Stopped","extra":1}]'
            )

        occupied = LocalEnvoyController(
            ROOT,
            FakeRunner(),
            home=Path("/Users/lab"),
            port_probe=lambda port: port == 18081,
            tool_verifier=lambda: {},
        )
        with self.assertRaisesRegex(ControllerError, "18081"):
            occupied.validate_ports()

    def test_post_start_colima_attestation_checks_actual_list_and_saved_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = (Path(directory) / "repo").resolve()
            home = Path(directory) / "home"
            profile = root / "deploy/kind/v3b-profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            saved = home / ".colima/kil-v3-lab/colima.yaml"
            saved.parent.mkdir(parents=True)
            staging = root / ".tools/v3b1-staging" / HEX_A
            staging.mkdir(parents=True)
            (staging / f"ownership-{HEX_A}.json").write_text(
                canonical_json(
                    {
                        "schema_version": "kil.v3b1-colima-ownership.v1",
                        "execution_nonce": HEX_A,
                        "profile": "kil-v3-lab",
                    }
                )
                + "\n"
            )
            saved.write_text(
                "cpu: 4\nmemory: 8\ndisk: 60\narch: aarch64\n"
                "runtime: docker\nvmType: vz\nmountType: virtiofs\n"
                "mountInotify: false\nrosetta: false\nbinfmt: false\n"
                "sshConfig: false\nforwardAgent: false\nnestedVirtualization: false\n"
                "portForwarder: ssh\nkubernetes:\n  enabled: false\n"
                "network:\n  # shell && policy ! are inert full comments\n"
                "  mode: shared\n  dns: []\n  # bounded whole-section parsing\n"
                "  address: false\n  interface: en0\n"
                "  hostAddresses: false\n  preferredRoute: false\nmounts:\n"
                f"  - location: {staging}\n    # mount && ! comment\n    writable: false\n"
            )
            list_record = (
                '{"name":"kil-v3-lab","status":"Running",'
                '"arch":"aarch64","cpus":4,"memory":8589934592,'
                '"disk":64424509440,"runtime":"docker"}\n'
            )
            runner = FakeRunner([CommandResult(0, list_record, "")])
            controller = LocalEnvoyController(
                root,
                runner,
                home=home,
                port_probe=lambda port: False,
                tool_verifier=lambda: {},
            )

            attestation = controller._attest_colima_after_start(HEX_A)

            self.assertEqual(attestation["profile"]["cpus"], 4)
            self.assertEqual(
                attestation["saved_config"]["mount"], str(staging)
            )
            self.assertEqual(len(runner.calls), 1)
            self.assertEqual(runner.calls[0][0], ["colima", "list", "--json"])

            alias = staging.parent / "staging-alias"
            alias.symlink_to(staging, target_is_directory=True)
            saved.write_text(saved.read_text().replace(str(staging), str(alias)))
            runner.replies.append(CommandResult(0, list_record, ""))
            with self.assertRaisesRegex(ControllerError, "staging mount"):
                controller._attest_colima_after_start(HEX_A)

    def test_registry_tags_resolve_to_exact_repository_digests(self):
        output = json.dumps(
            [
                f"docker.io/library/python@sha256:{HEX_A}",
                f"mirror.invalid/python@sha256:{HEX_B}",
            ]
        )
        self.assertEqual(
            select_registry_digest(
                "docker.io/library/python:3.12.13-slim", output
            ),
            PYTHON_DIGEST,
        )
        self.assertEqual(
            select_registry_digest(
                "docker.io/library/python:3.12.13-slim",
                f'["python@sha256:{HEX_A}"]',
            ),
            PYTHON_DIGEST,
        )
        with self.assertRaisesRegex(ControllerError, "registry digest"):
            select_registry_digest(
                "docker.io/library/python:3.12.13-slim",
                '["docker.io/library/python:latest"]',
            )
        with self.assertRaisesRegex(ControllerError, "repository"):
            select_registry_digest(
                "docker.io/library/python:3.12.13-slim",
                f'["mirror.invalid/python@sha256:{HEX_A}"]',
            )

    def test_injected_runner_builds_once_with_digest_platform_and_legacy_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "deploy/kind").mkdir(parents=True)
            (root / "deploy/kind/v3b-profile.json").write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            (root / "deploy/kind/Dockerfile.v3b").write_text(
                "ARG PYTHON_BASE_IMAGE\nFROM ${PYTHON_BASE_IMAGE}\n"
            )
            (root / "deploy/kind/Dockerfile.v3b.dockerignore").write_text(
                "**\n!deploy/kind/Dockerfile.v3b\n"
            )
            for relative in (
                "README.md",
                "pyproject.toml",
                "deploy/kind/requirements-v3b-build.txt",
                "deploy/kind/requirements-v3b-runtime.txt",
                "src/kil/__init__.py",
                "src/kil/canonical.py",
                "src/kil/decay.py",
                "src/kil/domain.py",
                "src/kil/engine.py",
                "src/kil/ext_authz_http.py",
                "src/kil/live_authz.py",
                "src/kil/q_state.py",
                "src/kil/target_http.py",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative + "\n")
            runner = BuildRunner()
            controller = LocalEnvoyController(
                root,
                runner,
                home=Path("/Users/lab"),
                port_probe=lambda port: False,
                tool_verifier=lambda: {},
            )
            controller._prepare_private_roots()

            image_id, archive_sha = controller._build_kil_image(
                PYTHON_DIGEST, build_key=HEX_A
            )

            self.assertEqual(image_id, KIL_IMAGE_ID)
            self.assertEqual(
                archive_sha, sha256(b"locked-image-archive").hexdigest()
            )
            commands = [call[0] for call in runner.calls]
            builds = [command for command in commands if "build" in command]
            self.assertEqual(len(builds), 1)
            build = builds[0]
            self.assertIn("linux/arm64", build)
            self.assertIn("--pull=false", build)
            self.assertIn(f"PYTHON_BASE_IMAGE={PYTHON_DIGEST}", build)
            self.assertNotIn("buildx", canonical_json(commands))
            self.assertTrue(all("--host" in command for command in commands))
            self.assertTrue(all("--config" in command for command in commands))
            context = Path(build[-1])
            self.assertEqual(context.parent.name, HEX_A)
            second_image_id, _ = controller._build_kil_image(
                PYTHON_DIGEST, build_key=HEX_B
            )
            self.assertEqual(second_image_id, KIL_IMAGE_ID)
            second_build = [
                call[0] for call in runner.calls if "build" in call[0]
            ][-1]
            self.assertEqual(Path(second_build[-1]).parent.name, HEX_B)
            self.assertNotEqual(context, Path(second_build[-1]))

    def test_manifest_is_content_addressed_and_refuses_mutable_images(self):
        value = manifest()

        self.assertRegex(value["run_id"], r"^v3b1-[a-f0-9]{64}$")
        self.assertEqual(value["evidence_scope"], "local_envoy_boundary")
        self.assertEqual(value["envoy_image_digest"], ENVOY_DIGEST)
        self.assertEqual(value["kil_image_id"], KIL_IMAGE_ID)
        self.assertEqual(len(value["containers"]), 9)
        different = create_run_manifest(
            PROFILE,
            profile_sha256=HEX_A,
            python_image_digest=PYTHON_DIGEST,
            envoy_image_digest=ENVOY_DIGEST,
            kil_image_id=KIL_IMAGE_ID,
            kil_archive_sha256=HEX_A,
            docker_host="unix:///socket",
            execution_nonce=HEX_B,
        )
        self.assertNotEqual(value["run_id"], different["run_id"])
        with self.assertRaisesRegex(ControllerError, "digest"):
            create_run_manifest(
                PROFILE,
                profile_sha256=HEX_A,
                python_image_digest="docker.io/library/python:3.12.13-slim",
                envoy_image_digest=ENVOY_DIGEST,
                kil_image_id=KIL_IMAGE_ID,
                kil_archive_sha256=HEX_A,
                docker_host="unix:///socket",
            )
        with self.assertRaisesRegex(ControllerError, "image ID"):
            create_run_manifest(
                PROFILE,
                profile_sha256=HEX_A,
                python_image_digest=PYTHON_DIGEST,
                envoy_image_digest=ENVOY_DIGEST,
                kil_image_id="kil-v3b1:latest",
                kil_archive_sha256=HEX_A,
                docker_host="unix:///socket",
            )

    def test_inputs_are_read_only_closed_and_requests_are_central_and_adversarial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = manifest()

            material = materialize_run_inputs(root, value)

            self.assertEqual(tuple(material.requests), tuple(LiveTrack))
            self.assertTrue(
                material.runtime_root.is_relative_to(
                    root / ".tools/v3b1-staging" / ("0" * 64)
                )
            )
            comparable = []
            for track, planned in material.requests.items():
                comparable.append(
                    (
                        planned["method"],
                        planned["path"],
                        planned["authorization"],
                        planned["adversarial_headers"],
                        planned["retry_control_headers"],
                    )
                )
                headers = planned["adversarial_headers"]
                for name in (
                    "x-kil-track",
                    "x-kil-decision-digest",
                    "x-kil-mode",
                    "x-kil-local-evidence",
                    "x-kil-verified-subject",
                    "x-kil-issuer",
                ):
                    self.assertIn(name, headers)
                self.assertEqual(
                    planned["retry_control_headers"], RETRY_CONTROL_HEADERS
                )
                track_root = material.runtime_root / track.value
                for name in ("authz.json", "target.json", "envoy.json"):
                    path = track_root / name
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                authz = json.loads((track_root / "authz.json").read_text())
                target = json.loads((track_root / "target.json").read_text())
                self.assertEqual(authz["track"], track.value)
                self.assertEqual(target["track"], track.value)
                self.assertNotIn("private", canonical_json(authz))
                self.assertEqual(target["run_id"], value["run_id"])
                self.assertIsNone(planned["q_state"])
            self.assertTrue(all(item == comparable[0] for item in comparable))

    def test_runtime_is_three_internal_networks_nine_labeled_containers_and_localhost_gateways(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = manifest(docker_host="unix:///tmp/kil.sock")
            materialize_run_inputs(root, value)

            commands = build_runtime_commands(
                root, value, docker_binary=Path("/locked/docker")
            )

            network_commands = [
                command
                for command in commands
                if "network" in command and "create" in command
            ]
            self.assertEqual(len(network_commands), 3)
            self.assertTrue(all("--internal" in command for command in network_commands))
            self.assertTrue(all("bridge" in command for command in network_commands))
            run_commands = [command for command in commands if "run" in command]
            detached = [command for command in run_commands if "-d" in command]
            validators = [command for command in run_commands if "--rm" in command]
            self.assertEqual(len(detached), 9)
            self.assertEqual(len(validators), 3)
            self.assertTrue(
                all("kil.v3b1.role=validator" in command for command in validators)
            )
            self.assertTrue(
                all("kil.v3b1.managed=true" in command for command in validators)
            )
            for command in detached:
                name = command[command.index("--name") + 1]
                self.assertTrue(name.startswith("kil-v3b1-"))
                self.assertIn("kil.v3b1.managed=true", command)
            kil_services = [
                command
                for command in detached
                if any(role in command for role in ("kil.v3b1.role=authz", "kil.v3b1.role=target"))
            ]
            self.assertEqual(len(kil_services), 6)
            for command in kil_services:
                self.assertIn("--platform", command)
                self.assertIn("linux/arm64", command)
                self.assertIn("--pull=never", command)
                self.assertIn("--read-only", command)
                self.assertIn("no-new-privileges", command)
                self.assertIn("ALL", command)
                self.assertIn("65532:65532", command)
                self.assertIn(KIL_IMAGE_ID, command)
                self.assertNotIn("latest", command)
                self.assertIn("--tmpfs", command)
                self.assertIn("--memory-swap", command)
                self.assertIn("256m", command)
                self.assertIn("--restart=no", command)
                self.assertIn("--stop-timeout", command)
                self.assertIn("--log-driver", command)
                self.assertIn("json-file", command)
                self.assertIn("max-size=1m", command)
                self.assertIn("max-file=1", command)
                self.assertTrue(
                    any(value.startswith("/evidence:rw,") for value in command)
                )
                self.assertFalse(any("dst=/ledger" in value for value in command))
            targets = [
                command
                for command in kil_services
                if "kil.v3b1.role=target" in command
            ]
            self.assertTrue(
                all("/evidence/targets.jsonl" in "".join(command) for command in targets)
            )
            self.assertTrue(all("O_EXCL" in "".join(command) for command in targets))
            gateways = [
                command
                for command in detached
                if "kil.v3b1.role=envoy" in command
            ]
            self.assertEqual(
                sorted(
                    command[command.index("--publish") + 1]
                    for command in gateways
                ),
                [
                    "127.0.0.1:18080:8080/tcp",
                    "127.0.0.1:18081:8080/tcp",
                    "127.0.0.1:18082:8080/tcp",
                ],
            )
            self.assertTrue(all(ENVOY_DIGEST in command for command in gateways))
            self.assertTrue(all("65532:65532" in command for command in gateways))
            self.assertTrue(all("--disable-hot-restart" in command for command in gateways))
            self.assertTrue(all("/usr/local/bin/envoy" in command for command in gateways))
            self.assertTrue(all("--pull=never" in command for command in validators))
            for command in gateways:
                self.assertIn("--memory-swap", command)
                self.assertIn("--restart=no", command)
                self.assertIn("--stop-timeout", command)
                self.assertIn("--log-driver", command)
            run_networks = {
                command[command.index("--name") + 1]: command[
                    command.index("--network") + 1
                ]
                for command in detached
            }
            for track in value["tracks"]:
                self.assertEqual(
                    {
                        run_networks[track["authz_container"]],
                        run_networks[track["target_container"]],
                        run_networks[track["envoy_container"]],
                    },
                    {track["network"]},
                )

            copies = collection_commands(
                root, value, docker_binary=Path("/locked/docker")
            )
            self.assertEqual(len([command for command in copies if "cp" in command]), 6)
            for command in copies:
                self.assertEqual(command[0], "/locked/docker")
                self.assertIn("--config", command)
                self.assertIn("--host", command)
                self.assertIn("unix:///tmp/kil.sock", command)

    def test_active_state_and_manifest_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "artifacts" / "manifest.json"
            state = root / ".tools" / "state" / "v3b1-active.json"
            value = manifest()
            output.parent.mkdir(parents=True)
            output.write_text(canonical_json(value) + "\n", encoding="utf-8")
            persist_active_state(state, output, value)

            loaded = load_bound_active_state(state)
            self.assertEqual(loaded["run_id"], value["run_id"])

            output.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ControllerError, "manifest"):
                load_bound_active_state(state)

            output.write_text(canonical_json(value) + "\n", encoding="utf-8")
            raw = json.loads(state.read_text())
            raw["networks"][0]["name"] = "kil-v3b1-tampered"
            state.write_text(canonical_json(raw) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ControllerError, "state binding"):
                load_bound_active_state(state)

    def test_teardown_is_exact_and_contains_no_discovery_or_broad_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            state_path = root / "active.json"
            value = manifest(docker_host="unix:///tmp/kil.sock")
            manifest_path.write_text(canonical_json(value) + "\n")
            persist_active_state(state_path, manifest_path, value)
            state = load_bound_active_state(state_path)
            self.assertTrue(state["profile_created"])

            commands = teardown_commands(
                state, docker_binary=Path("/locked/docker")
            )

            removed = [command[-1] for command in commands if "rm" in command and "network" not in command]
            expected_order = [
                item["id"]
                for role in ("envoy", "authz", "target")
                for item in state["objects"]
                if item["role"] == role
            ]
            self.assertEqual(removed, expected_order)
            stop_indexes = [
                index
                for index, command in enumerate(commands)
                if command[0] == "/locked/docker" and "stop" in command
            ]
            remove_indexes = [
                index
                for index, command in enumerate(commands)
                if "rm" in command and "network" not in command
            ]
            self.assertLess(max(stop_indexes), min(remove_indexes))
            network_removes = [command for command in commands if "network" in command and "rm" in command]
            self.assertEqual(len(network_removes), 3)
            self.assertEqual(
                {command[-1] for command in network_removes},
                {item["id"] for item in state["network_objects"]},
            )
            self.assertEqual(
                commands[-2:],
                [
                    ["colima", "stop", "--profile", "kil-v3-lab"],
                    [
                        "colima",
                        "delete",
                        "--profile",
                        "kil-v3-lab",
                        "--force",
                        "--data",
                    ],
                ],
            )
            encoded = canonical_json(commands)
            teardown_parts = [part for command in commands for part in command]
            self.assertNotIn("--time", teardown_parts)
            self.assertIn("--timeout", teardown_parts)
            for forbidden in ("*", "prune", "system", "ps", "context", "-aq"):
                self.assertNotIn(forbidden, encoded)

            unowned = dict(state)
            unowned["profile_created"] = False
            unowned.pop("binding_sha256")
            with self.assertRaisesRegex(ControllerError, "profile ownership"):
                teardown_commands(unowned, docker_binary=Path("/locked/docker"))

    def test_default_active_state_is_an_exact_ignored_repository_path(self):
        self.assertEqual(
            ACTIVE_STATE_PATH,
            ROOT / ".tools/state/v3b1-active.json",
        )


class JoinContractTest(unittest.TestCase):
    def all_records(self):
        value = manifest()
        digests = {
            LiveTrack.CREDENTIAL_POLICY_BASELINE: "1" * 64,
            LiveTrack.SIGNED_STATE_ONLY: "2" * 64,
            LiveTrack.SIGNED_PLUS_LOCAL_REDUCE: "3" * 64,
        }
        requests = [request_record(value, track) for track in LiveTrack]
        decisions = []
        envoy = []
        targets = []
        for track in LiveTrack:
            denied = track is LiveTrack.SIGNED_PLUS_LOCAL_REDUCE
            status = 403 if denied else 200
            outcome = "deny" if denied else "permit"
            upstream = "-" if denied else "10.0.0.2:8080"
            decisions.append(
                decision_record(
                    value,
                    track,
                    status=status,
                    outcome=outcome,
                    digest=digests[track],
                )
            )
            envoy.append(
                envoy_record(
                    value,
                    track,
                    status=status,
                    upstream=upstream,
                    digest=digests[track],
                )
            )
            if not denied:
                targets.append(target_record(value, track, digests[track]))
        return value, requests, decisions, envoy, targets

    def test_permit_permit_deny_join_requires_exact_digest_and_marker_counts(self):
        value, requests, decisions, envoy, targets = self.all_records()

        joins = join_evidence(value, requests, decisions, envoy, targets)

        self.assertEqual([item["outcome"] for item in joins], ["permit", "permit", "deny"])
        self.assertEqual([item["target_marker_count"] for item in joins], [1, 1, 0])
        self.assertTrue(all(item["valid"] for item in joins))
        self.assertIsNone(joins[-1]["upstream_host"])
        self.assertEqual(joins[-1]["decision_digest"], "3" * 64)

    def test_envoy_dash_is_absent_and_authz_5xx_does_not_invent_a_digest(self):
        value = manifest()
        track = LiveTrack.SIGNED_STATE_ONLY
        joins = join_evidence(
            value,
            [
                request_record(
                    value,
                    track,
                    client_response_status=503,
                    client_decision_digest=None,
                )
            ],
            [decision_record(value, track, status=503, outcome="error", digest=None)],
            [envoy_record(value, track, status=503, upstream="-", digest="-")],
            [],
            require_all_tracks=False,
        )

        self.assertEqual(joins[0]["outcome"], "error")
        self.assertIsNone(joins[0]["envoy_decision_digest"])
        self.assertIsNone(joins[0]["upstream_host"])
        self.assertEqual(joins[0]["target_marker_count"], 0)
        self.assertTrue(joins[0]["valid"])

        with self.assertRaisesRegex(ControllerError, "5xx.*sentinel"):
            join_evidence(
                value,
                [
                    request_record(
                        value,
                        track,
                        client_response_status=503,
                        client_decision_digest="7" * 64,
                    )
                ],
                [
                    decision_record(
                        value, track, status=503, outcome="error", digest="7" * 64
                    )
                ],
                [
                    envoy_record(
                        value, track, status=503, upstream="-", digest="7" * 64
                    )
                ],
                [],
                require_all_tracks=False,
            )

    def test_spoofed_client_run_id_or_digest_mismatch_is_rejected(self):
        value, requests, decisions, envoy, targets = self.all_records()
        envoy[0]["run_id"] = "client-selected-run"
        with self.assertRaisesRegex(ControllerError, "run_id"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        targets[0]["decision_digest"] = "f" * 64
        with self.assertRaisesRegex(ControllerError, "digest"):
            join_evidence(value, requests, decisions, envoy, targets)

    def test_duplicate_markers_duplicate_records_and_retry_are_invalid(self):
        value, requests, decisions, envoy, targets = self.all_records()
        targets.append(dict(targets[0]))
        with self.assertRaisesRegex(ControllerError, "duplicate target"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        envoy.append(dict(envoy[0]))
        with self.assertRaisesRegex(ControllerError, "duplicate envoy"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        requests.append(dict(requests[0]))
        with self.assertRaisesRegex(ControllerError, "duplicate request"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        decisions.append(dict(decisions[0]))
        with self.assertRaisesRegex(ControllerError, "duplicate decision"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        requests[0]["retry_observed"] = True
        requests[0]["attempt_count"] = 2
        with self.assertRaisesRegex(ControllerError, "retry"):
            join_evidence(value, requests, decisions, envoy, targets)

    def test_policy_deny_requires_no_upstream_and_zero_markers(self):
        value, requests, decisions, envoy, targets = self.all_records()
        envoy[-1]["upstream_host"] = "10.0.0.3:8080"
        with self.assertRaisesRegex(ControllerError, "deny"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        envoy[-1]["decision_digest"] = "-"
        with self.assertRaisesRegex(ControllerError, "403"):
            join_evidence(value, requests, decisions, envoy, targets)

    def test_all_deny_and_client_response_mismatch_are_rejected(self):
        value, requests, decisions, envoy, targets = self.all_records()
        for index in (0, 1):
            decisions[index]["outcome"] = "deny"
            decisions[index]["http_status"] = 403
            envoy[index]["response_code"] = "403"
            envoy[index]["upstream_host"] = "-"
            envoy[index]["upstream_service_time"] = "-"
            requests[index]["client_response_status"] = 403
        targets.clear()
        with self.assertRaisesRegex(ControllerError, "permit / permit / deny"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        requests[0]["client_response_status"] = 403
        with self.assertRaisesRegex(ControllerError, "client response"):
            join_evidence(value, requests, decisions, envoy, targets)

    def test_wrong_target_path_and_bad_upstream_service_time_are_rejected(self):
        value, requests, decisions, envoy, targets = self.all_records()
        targets[0]["path"] = "/benign/read"
        with self.assertRaisesRegex(ControllerError, "target path"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        envoy[0]["upstream_service_time"] = "01"
        with self.assertRaisesRegex(ControllerError, "service time"):
            join_evidence(value, requests, decisions, envoy, targets)

    def test_short_requests_and_unredacted_or_unknown_reasons_are_rejected(self):
        value, requests, decisions, envoy, targets = self.all_records()
        del requests[0]["client_response_status"]
        with self.assertRaisesRegex(ControllerError, "fields"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        decisions[0]["adapter_reasons"] = ["Bearer secret"]
        with self.assertRaisesRegex(ControllerError, "type/value/redaction"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        decisions[-1]["engine_reasons"] = ["permitted"]
        with self.assertRaisesRegex(ControllerError, "causal"):
            join_evidence(value, requests, decisions, envoy, targets)

        value, requests, decisions, envoy, targets = self.all_records()
        decisions[0]["untrusted_header_names"] = ["x-kil-mode"]
        with self.assertRaisesRegex(ControllerError, "header boundary"):
            join_evidence(value, requests, decisions, envoy, targets)


class JournalRecoveryTest(unittest.TestCase):
    def create(self, root: Path) -> Path:
        private_root = root / ".tools/v3b1-private"
        private_root.mkdir(parents=True)
        journal = private_root / "journal.json"
        create_lifecycle_journal(
            journal,
            private_root=private_root,
            repository_root=root,
            docker_host="unix:///Users/lab/.colima/kil-v3-lab/docker.sock",
            source_commit="d" * 40,
            execution_nonce=HEX_A,
            global_context="personal",
        )
        return journal

    def test_private_roots_are_resolved_contained_and_never_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.mkdir()
            linked = root / ".tools/v3b1-private"
            linked.parent.mkdir()
            linked.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ControllerError, "symbolic|contain"):
                create_lifecycle_journal(
                    linked / "journal.json",
                    private_root=linked,
                    repository_root=root,
                    docker_host="unix:///socket",
                    source_commit="d" * 40,
                    execution_nonce=HEX_A,
                    global_context="default",
                )

        for linked_relative in (
            ".tools/state",
            ".tools/v3b1-private/manifests",
            "artifacts/generated",
        ):
            with self.subTest(linked_relative=linked_relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repo"
                profile = root / "deploy/kind/v3b-profile.json"
                profile.parent.mkdir(parents=True)
                profile.write_bytes(
                    (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
                )
                outside = Path(directory) / "outside"
                outside.mkdir()
                linked = root / linked_relative
                linked.parent.mkdir(parents=True, exist_ok=True)
                linked.symlink_to(outside, target_is_directory=True)
                controller = LocalEnvoyController(
                    root,
                    FakeRunner(),
                    home=Path("/Users/lab"),
                    port_probe=lambda port: False,
                    tool_verifier=lambda: {},
                )
                with self.assertRaisesRegex(ControllerError, "symbolic|contained"):
                    controller._prepare_private_roots()
                self.assertEqual(list(outside.iterdir()), [])

    def test_completed_child_symlink_rejects_archive_before_external_move(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile = root / "deploy/kind/v3b-profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            controller = LocalEnvoyController(
                root,
                FakeRunner(
                    [
                        CommandResult(0, "[]\n", ""),
                        CommandResult(0, "personal\n", ""),
                    ]
                ),
                home=Path("/Users/lab"),
                port_probe=lambda port: False,
                tool_verifier=lambda: {},
            )
            controller._prepare_private_roots()
            outside = Path(directory) / "outside-completed"
            outside.mkdir()
            completed = controller.private_root / "completed"
            if completed.exists():
                completed.rmdir()
            completed.symlink_to(outside, target_is_directory=True)
            create_lifecycle_journal(
                controller.journal_path,
                private_root=controller.private_root,
                repository_root=root,
                docker_host=controller.docker_host,
                source_commit="d" * 40,
                execution_nonce=HEX_A,
                global_context="personal",
            )

            with self.assertRaisesRegex(ControllerError, "symbolic|contained"):
                controller.down()

            self.assertTrue(controller.journal_path.exists())
            self.assertEqual(list(outside.iterdir()), [])

    def test_journal_is_hash_bound_and_request_intent_is_never_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = self.create(root)
            intent = claim_request_attempt(
                journal, LiveTrack.SIGNED_STATE_ONLY
            )
            self.assertEqual(intent["status"], "intent_persisted")
            with self.assertRaisesRegex(ControllerError, "already attempted|ambiguous"):
                claim_request_attempt(journal, LiveTrack.SIGNED_STATE_ONLY)
            loaded = load_lifecycle_journal(journal)
            self.assertEqual(
                loaded["requests"][LiveTrack.SIGNED_STATE_ONLY.value]["status"],
                "intent_persisted",
            )
            raw = json.loads(journal.read_text())
            raw["phase"] = "tampered"
            journal.write_text(canonical_json(raw) + "\n")
            with self.assertRaisesRegex(ControllerError, "binding"):
                load_lifecycle_journal(journal)

    def test_ambiguous_colima_start_requires_manual_recovery_and_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "deploy/kind/v3b-profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            runner = FakeRunner(
                [
                    CommandResult(
                        0,
                        '{"name":"kil-v3-lab","status":"Running",'
                        '"arch":"aarch64","cpus":4,"memory":8589934592,'
                        '"disk":64424509440,"runtime":"docker"}\n',
                        "",
                    )
                ]
            )
            controller = LocalEnvoyController(
                root,
                runner,
                home=Path("/Users/lab"),
                port_probe=lambda port: False,
                tool_verifier=lambda: {},
            )
            controller._prepare_private_roots()
            journal = controller.journal_path
            create_lifecycle_journal(
                journal,
                private_root=controller.private_root,
                repository_root=root,
                docker_host=controller.docker_host,
                source_commit="d" * 40,
                execution_nonce=HEX_A,
                global_context="personal",
            )
            journal_event(
                journal,
                "preflight_complete",
                {"dedicated_profile_absent": True},
            )
            journal_event(
                journal,
                "colima_start_intent",
                {"profile": "kil-v3-lab", "command_sha256": HEX_B},
            )

            with self.assertRaisesRegex(ControllerError, "manual recovery"):
                controller.down()

            self.assertFalse(load_lifecycle_journal(journal)["profile_created"])
            flattened = [part for call, *_ in runner.calls for part in call]
            self.assertNotIn("delete", flattened)
            self.assertNotIn("stop", flattened)

    def test_successful_start_without_attestation_is_not_owned_or_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile = root / "deploy/kind/v3b-profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )

            class FailedAttestationController(LocalEnvoyController):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.deleted = False
                    self.commands = []

                def preflight(self):
                    return {
                        "profiles": (),
                        "ports": self.profile.gateway_ports,
                        "tool_identities": TOOL_IDENTITIES,
                    }

                def _clean_source_identity(self):
                    return "d" * 40

                def _capture_global_context(self):
                    return "personal"

                def _execute(self, argv, *, timeout_s, docker=False):
                    self.commands.append(list(argv))
                    if list(argv[:3]) == ["colima", "list", "--json"]:
                        return CommandResult(
                            0,
                            "[]\n"
                            if self.deleted
                            else (
                                '{"name":"kil-v3-lab","status":"Running",'
                                '"arch":"aarch64","cpus":4,'
                                '"memory":8589934592,"disk":64424509440,'
                                '"runtime":"docker"}\n'
                            ),
                            "",
                        )
                    if argv[0:2] == ["colima", "delete"]:
                        self.deleted = True
                    return CommandResult(0, "", "")

                def _attest_colima_after_start(self, execution_nonce=None):
                    raise ControllerError("injected post-start attestation failure")

                def _assert_only_recorded_managed(self, state, *, expect_present):
                    return None

            controller = FailedAttestationController(
                root,
                FakeRunner(),
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
            )

            with self.assertRaisesRegex(ControllerError, "attestation failure"):
                controller.up()

            journal = load_lifecycle_journal(controller.journal_path)
            self.assertFalse(journal["profile_created"])
            self.assertEqual(
                [event["event"] for event in journal["events"]][-3:],
                [
                    "colima_start_returned",
                    "colima_attestation_intent",
                    "colima_attestation_failed",
                ],
            )

            with self.assertRaisesRegex(ControllerError, "manual recovery"):
                controller.down()

            self.assertFalse(controller.deleted)
            flattened = [part for command in controller.commands for part in command]
            self.assertNotIn("delete", flattened)
            self.assertNotIn("stop", flattened)

    def test_each_mutation_phase_leaves_a_recoverable_intent(self):
        phases = (
            "colima_start",
            "image_resolution",
            "image_build",
            "network_create",
            "container_create",
            "request_send",
            "evidence_collect",
            "container_stop",
            "container_remove",
            "network_remove",
            "colima_delete",
            "publication",
        )
        for phase in phases:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                journal = self.create(root)
                journal_event(
                    journal,
                    f"{phase}_intent",
                    {"injected_failure": True},
                )
                plan = recovery_plan(load_lifecycle_journal(journal))
                self.assertEqual(plan["last_event"], f"{phase}_intent")
                self.assertTrue(plan["fail_closed"])

    def test_request_records_are_bound_to_one_successful_journal_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = self.create(root)
            value = manifest()
            track = LiveTrack.CREDENTIAL_POLICY_BASELINE
            record = request_record(value, track)
            claim_request_attempt(journal, track)
            _complete_request_attempt(
                journal,
                track,
                success=True,
                record_sha256=sha256(
                    (canonical_json(record) + "\n").encode("utf-8")
                ).hexdigest(),
            )
            validate_request_journal(
                [record], load_lifecycle_journal(journal), require_all=False
            )

            mutated = dict(record)
            mutated["receive_monotonic_ns"] += 1
            with self.assertRaisesRegex(ControllerError, "request.*SHA"):
                validate_request_journal(
                    [mutated], load_lifecycle_journal(journal), require_all=False
                )

            journal_event(
                journal,
                "request_send_complete",
                {
                    "track": track.value,
                    "record_sha256": sha256(
                        (canonical_json(record) + "\n").encode("utf-8")
                    ).hexdigest(),
                },
            )
            with self.assertRaisesRegex(ControllerError, "exactly one"):
                validate_request_journal(
                    [record], load_lifecycle_journal(journal), require_all=False
                )

        with tempfile.TemporaryDirectory() as directory:
            journal = self.create(Path(directory))
            track = LiveTrack.CREDENTIAL_POLICY_BASELINE
            claim_request_attempt(journal, track)
            with self.assertRaisesRegex(ControllerError, "null|SHA"):
                _complete_request_attempt(
                    journal, track, success=True, record_sha256=None
                )


class TeardownContinuationTest(unittest.TestCase):
    def test_evidence_rejection_never_blocks_exact_owned_profile_deletion(self):
        for failure in ("missing_file", "malformed_json", "wrong_outcome"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "repo"
                profile_path = root / "deploy/kind/v3b-profile.json"
                profile_path.parent.mkdir(parents=True)
                profile_path.write_bytes(
                    (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
                )

                class InjectedDownController(LocalEnvoyController):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.commands = []
                        self.deleted = False
                        self.injected_failure = failure
                        self.bound_state = None
                        self.bound_manifest = None
                        self.request_records = []

                    def _execute(self, argv, *, timeout_s, docker=False):
                        self.commands.append(list(argv))
                        if list(argv[:3]) == ["colima", "list", "--json"]:
                            return CommandResult(
                                0,
                                "[]\n"
                                if self.deleted
                                else (
                                    '{"name":"kil-v3-lab","status":"Running",'
                                    '"arch":"aarch64","cpus":4,'
                                    '"memory":8589934592,"disk":64424509440,'
                                    '"runtime":"docker"}\n'
                                ),
                                "",
                            )
                        if "delete" in argv and argv[0] == "colima":
                            self.deleted = True
                            return CommandResult(0, "", "")
                        if "{{.State.Running}}" in argv:
                            return CommandResult(0, "false\n", "")
                        if "context" in argv and "show" in argv:
                            return CommandResult(0, "personal\n", "")
                        return CommandResult(0, "", "")

                    def _attest_colima_after_start(self, execution_nonce=None):
                        return {"test_attestation": True}

                    def _load_for_down(self):
                        return (
                            self.bound_state,
                            self.bound_manifest,
                            load_lifecycle_journal(self.journal_path),
                        )

                    def _assert_only_recorded_managed(self, state, *, expect_present):
                        return None

                    def _inspect_container(self, identifier, manifest_value, role, track, *, require_running=True):
                        return next(
                            item
                            for item in self.bound_state["objects"]
                            if item["id"] == identifier
                        )

                    def _inspect_network(self, identifier, manifest_value, track, *, require_complete_membership=True):
                        return next(
                            item
                            for item in self.bound_state["network_objects"]
                            if item["id"] == identifier
                        )

                    def _docker_object_exists(self, kind, identifier):
                        return False

                    def _request_records(self, manifest_value):
                        return list(self.request_records)

                    def _copy_sources(self, state, manifest_value, name, *, allow_incomplete=False):
                        if self.injected_failure == "missing_file":
                            raise ControllerError("injected missing evidence file")
                        if self.injected_failure == "malformed_json":
                            raise ControllerError("injected malformed evidence JSON")
                        value, requests, decisions, envoy, targets = (
                            JoinContractTest().all_records()
                        )
                        decisions[0]["outcome"] = "deny"
                        decisions[0]["http_status"] = 403
                        raw = {
                            track: (
                                canonical_json(
                                    next(
                                        item
                                        for item in decisions
                                        if item["track"] == track.value
                                    )
                                )
                                + "\n"
                            ).encode("utf-8")
                            for track in LiveTrack
                        }
                        return raw, envoy, targets

                controller = InjectedDownController(
                    root,
                    FakeRunner(),
                    home=Path(directory) / "home",
                    port_probe=lambda port: False,
                    tool_verifier=lambda: TOOL_IDENTITIES,
                )
                controller._prepare_private_roots()
                value = manifest(docker_host=controller.docker_host)
                private_manifest = controller.private_root / "manifests/run.json"
                private_manifest.parent.mkdir(parents=True, exist_ok=True)
                private_manifest.write_text(canonical_json(value) + "\n")
                create_lifecycle_journal(
                    controller.journal_path,
                    private_root=controller.private_root,
                    repository_root=root,
                    docker_host=controller.docker_host,
                    source_commit="d" * 40,
                    execution_nonce=HEX_A,
                    global_context="personal",
                )
                journal_event(
                    controller.journal_path,
                    "preflight_complete",
                    {"tool_identities": TOOL_IDENTITIES},
                )
                journal_event(
                    controller.journal_path,
                    "colima_attestation_complete",
                    {"profile": "kil-v3-lab", "attestation": {}},
                )
                journal_event(
                    controller.journal_path,
                    "engine_provenance_observed",
                    ENGINE_PROVENANCE,
                )
                _bind_journal_manifest(
                    controller.journal_path, private_manifest, value
                )
                persist_active_state(
                    controller.state_path, private_manifest, value
                )
                controller.bound_state = load_bound_active_state(
                    controller.state_path
                )
                controller.bound_manifest = value
                _, requests, _, _, _ = JoinContractTest().all_records()
                controller.request_records = requests
                for track, record in zip(LiveTrack, requests, strict=True):
                    claim_request_attempt(controller.journal_path, track)
                    _complete_request_attempt(
                        controller.journal_path,
                        track,
                        success=True,
                        record_sha256=sha256(
                            (canonical_json(record) + "\n").encode("utf-8")
                        ).hexdigest(),
                    )

                published = controller.down()

                self.assertTrue(controller.deleted)
                self.assertTrue(
                    any(command[0:2] == ["colima", "delete"] for command in controller.commands)
                )
                public_manifest = json.loads(
                    (published / "manifest.json").read_text()
                )
                self.assertFalse(public_manifest["run_complete"])
                self.assertIn("failure", public_manifest["bundle_class"])

    def test_post_delete_recovery_reconstructs_pending_failure_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )

            class PostDeleteRecoveryController(LocalEnvoyController):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.commands = []

                def _execute(self, argv, *, timeout_s, docker=False):
                    self.commands.append(list(argv))
                    if list(argv[:3]) == ["colima", "list", "--json"]:
                        return CommandResult(0, "[]\n", "")
                    if "context" in argv and "show" in argv:
                        return CommandResult(0, "personal\n", "")
                    raise AssertionError(f"unexpected recovery command: {argv}")

            controller = PostDeleteRecoveryController(
                root,
                FakeRunner(),
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
            )
            controller._prepare_private_roots()
            value, requests, decisions, envoy, targets = (
                JoinContractTest().all_records()
            )
            private_manifest = controller.private_root / "manifests/run.json"
            private_manifest.write_text(canonical_json(value) + "\n")
            create_lifecycle_journal(
                controller.journal_path,
                private_root=controller.private_root,
                repository_root=root,
                docker_host=controller.docker_host,
                source_commit="d" * 40,
                execution_nonce=HEX_A,
                global_context="personal",
            )
            journal_event(
                controller.journal_path,
                "preflight_complete",
                {"tool_identities": TOOL_IDENTITIES},
            )
            journal_event(
                controller.journal_path,
                "colima_attestation_complete",
                {"profile": "kil-v3-lab", "attestation": {}},
            )
            journal_event(
                controller.journal_path,
                "engine_provenance_observed",
                ENGINE_PROVENANCE,
            )
            _bind_journal_manifest(
                controller.journal_path, private_manifest, value
            )
            stale = write_evidence_bundle(
                controller.provisional_root,
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=join_evidence(value, requests, decisions, envoy, targets),
            )
            stale_authority = authoritative_bundle_attestation(stale)
            journal_event(
                controller.journal_path,
                "evidence_collect_complete",
                {
                    "completed": False,
                    "bundle_sha256": sha256(
                        (stale / "SHA256SUMS").read_bytes()
                    ).hexdigest(),
                    "authoritative_attestation": stale_authority,
                },
            )
            journal_event(
                controller.journal_path,
                "colima_delete_intent",
                {"profile": "kil-v3-lab"},
            )
            journal_event(
                controller.journal_path,
                "colima_delete_complete",
                {"profile": "kil-v3-lab", "verified_absent": True},
            )
            intent = journal_event(
                controller.journal_path,
                "post_teardown_failure_bundle_intent",
                {
                    "run_id": value["run_id"],
                    "evidence_rejection": "injected collection rejection",
                    "replacement": "deterministic_empty_failure_v1",
                },
            )
            intent_sequence = len(intent["events"])

            # Crash point: replacement is complete, but its authority was not journaled.
            _prepare_failure_provisional(
                controller.provisional_root, value, reset=True
            )

            published = controller.down()

            public_manifest = json.loads((published / "manifest.json").read_text())
            self.assertFalse(public_manifest["run_complete"])
            self.assertEqual(public_manifest["promotion_status"], "not_promoted")
            self.assertIn("failure", public_manifest["bundle_class"])
            self.assertNotEqual(
                public_manifest["authoritative_bundle_sha256"],
                stale_authority["binding_sha256"],
            )
            self.assertEqual(
                [command for command in controller.commands if "delete" in command],
                [],
            )
            archived = controller.completed_root / f"{value['run_id']}.journal.json"
            recovered = load_lifecycle_journal(archived)
            completions = [
                event
                for event in recovered["events"]
                if event["event"] == "post_teardown_failure_bundle_prepared"
                and event["details"].get("intent_sequence") == intent_sequence
            ]
            self.assertEqual(len(completions), 1)
            recovered_authority = completions[0]["details"][
                "authoritative_attestation"
            ]
            self.assertEqual(
                public_manifest["authoritative_bundle_sha256"],
                recovered_authority["binding_sha256"],
            )
            self.assertEqual(
                list(controller.evidence_root.iterdir()), [published]
            )


class RuntimeAttestationTest(unittest.TestCase):
    def test_minimal_staged_build_context_is_exact_and_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            staging = Path(directory) / "private/context"
            for relative in (
                "README.md",
                "pyproject.toml",
                "deploy/kind/Dockerfile.v3b",
                "deploy/kind/Dockerfile.v3b.dockerignore",
                "deploy/kind/requirements-v3b-build.txt",
                "deploy/kind/requirements-v3b-runtime.txt",
                "src/kil/__init__.py",
                "src/kil/canonical.py",
                "src/kil/decay.py",
                "src/kil/domain.py",
                "src/kil/engine.py",
                "src/kil/ext_authz_http.py",
                "src/kil/live_authz.py",
                "src/kil/q_state.py",
                "src/kil/target_http.py",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative + "\n")
            extra = root / "secret.txt"
            extra.write_text("must not stage\n")

            attestation = stage_build_context(root, staging)

            staged = {
                path.relative_to(staging).as_posix()
                for path in staging.rglob("*")
                if path.is_file()
            }
            self.assertNotIn("secret.txt", staged)
            self.assertEqual(staged, set(attestation["files"]))
            self.assertRegex(attestation["context_sha256"], r"^[a-f0-9]{64}$")

    def test_container_attestation_closes_security_resources_mounts_and_ports(self):
        expected = {
            "name": "kil-v3b1-authz-track",
            "role": "authz",
            "track": LiveTrack.SIGNED_STATE_ONLY.value,
            "image_id": KIL_IMAGE_ID,
            "network": "kil-v3b1-network-track",
            "config_path": "/private/authz.json",
            "config_sha256": HEX_A,
            "gateway_port": None,
        }
        actual = {
            "id": "9" * 64,
            "name": expected["name"],
            "image_id": KIL_IMAGE_ID,
            "user": "65532:65532",
            "readonly_rootfs": True,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges"],
            "nano_cpus": 500_000_000,
            "memory": 268_435_456,
            "memory_swap": 268_435_456,
            "pids_limit": 128,
            "restart_policy": "no",
            "stop_timeout": 10,
            "log_driver": "json-file",
            "log_options": {"max-file": "1", "max-size": "1m"},
            "tmpfs": {
                "/evidence": "rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700",
                "/tmp": "rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700",
            },
            "mounts": [
                {
                    "source": expected["config_path"],
                    "destination": "/config/authz.json",
                    "rw": False,
                }
            ],
            "networks": [expected["network"]],
            "port_bindings": {},
            "platform": "linux/arm64",
            "entrypoint": [],
            "command": [
                "python",
                "-c",
                (
                    "import os,runpy;"
                    "fd=os.open('/evidence/decisions.jsonl',"
                    "os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);"
                    "os.close(fd);"
                    "runpy.run_module('kil.ext_authz_http',run_name='__main__')"
                ),
                "--config",
                "/config/authz.json",
            ],
            "environment": ["PATH=/usr/local/bin"],
        }
        validated = validate_container_attestation(actual, expected)
        self.assertEqual(validated["id"], "9" * 64)
        for mutation, message in (
            (("readonly_rootfs", False), "read-only"),
            (("memory_swap", 536_870_912), "memory"),
            (("networks", ["cross-track"]), "network"),
        ):
            broken = dict(actual)
            broken[mutation[0]] = mutation[1]
            with self.assertRaisesRegex(ControllerError, message):
                validate_container_attestation(broken, expected)

    def test_stopped_envoy_accepts_only_exact_image_and_runtime_label_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            controller = LocalEnvoyController(
                root,
                FakeRunner(),
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
            )
            controller._prepare_private_roots()
            value = manifest()
            track = LiveTrack.CREDENTIAL_POLICY_BASELINE
            track_value = next(
                item for item in value["tracks"] if item["track"] == track.value
            )
            config_path = controller._config_path(value, "envoy", track.value)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text("{}\n")
            config_path.chmod(0o444)
            runtime_labels = {
                "kil.v3b1.managed": "true",
                "kil.v3b1.run-id": value["run_id"],
                "kil.v3b1.role": "envoy",
                "kil.v3b1.track": track.value,
            }
            immutable_labels = {"org.opencontainers.image.version": "22.04"}

            def inspections(
                *,
                image_labels=immutable_labels,
                container_labels=None,
            ):
                merged = {**image_labels, **runtime_labels}
                if container_labels is not None:
                    merged = container_labels
                container = {
                    "Id": "9" * 64,
                    "Name": f"/{track_value['envoy_container']}",
                    "Image": value["envoy_image_id"],
                    "Config": {
                        "Image": value["envoy_image_digest"],
                        "Labels": merged,
                        "User": "65532:65532",
                        "StopTimeout": 10,
                        "Entrypoint": ["/usr/local/bin/envoy"],
                        "Cmd": [
                            "--config-path",
                            "/etc/envoy/envoy.json",
                            "--disable-hot-restart",
                            "--concurrency",
                            "1",
                        ],
                        "Env": ["PATH=/usr/local/bin"],
                    },
                    "HostConfig": {
                        "ReadonlyRootfs": True,
                        "CapDrop": ["ALL"],
                        "SecurityOpt": ["no-new-privileges"],
                        "NanoCpus": 500_000_000,
                        "Memory": 268_435_456,
                        "MemorySwap": 268_435_456,
                        "PidsLimit": 128,
                        "RestartPolicy": {"Name": "no"},
                        "LogConfig": {
                            "Type": "json-file",
                            "Config": {"max-file": "1", "max-size": "1m"},
                        },
                        "Tmpfs": {
                            "/tmp": "rw,noexec,nosuid,nodev,size=16777216,uid=65532,gid=65532,mode=448"
                        },
                        "PortBindings": {
                            "8080/tcp": [
                                {
                                    "HostIp": "127.0.0.1",
                                    "HostPort": str(track_value["gateway_port"]),
                                }
                            ]
                        },
                    },
                    "State": {"Running": False},
                    "NetworkSettings": {
                        "Networks": {track_value["network"]: {}}
                    },
                    "Mounts": [
                        {
                            "Source": str(config_path),
                            "Destination": "/etc/envoy/envoy.json",
                            "RW": False,
                        }
                    ],
                }
                image = {
                    "Os": "linux",
                    "Architecture": "arm64",
                    "Config": {
                        "Env": ["PATH=/usr/local/bin"],
                        "Labels": image_labels,
                    },
                }
                return [
                    CommandResult(0, canonical_json(container) + "\n", ""),
                    CommandResult(0, canonical_json(image) + "\n", ""),
                ]

            controller.runner = FakeRunner(inspections())
            inspected = controller._inspect_container(
                "9" * 64,
                value,
                "envoy",
                track.value,
                require_running=False,
            )
            self.assertEqual(inspected["labels"], runtime_labels)

            conflict_labels = {
                **immutable_labels,
                "kil.v3b1.role": "image-owned-conflict",
            }
            controller.runner = FakeRunner(inspections(image_labels=conflict_labels))
            with self.assertRaisesRegex(ControllerError, "label.*conflict"):
                controller._inspect_container(
                    "9" * 64,
                    value,
                    "envoy",
                    track.value,
                    require_running=False,
                )

            for reserved_labels in (
                {
                    **immutable_labels,
                    "kil.v3b1.role": "envoy",
                },
                {
                    **immutable_labels,
                    "kil.v3b1.future-reserved": "image-owned",
                },
            ):
                with self.subTest(reserved_labels=reserved_labels):
                    controller.runner = FakeRunner(
                        inspections(image_labels=reserved_labels)
                    )
                    with self.assertRaisesRegex(
                        ControllerError, "reserved.*label|label.*namespace"
                    ):
                        controller._inspect_container(
                            "9" * 64,
                            value,
                            "envoy",
                            track.value,
                            require_running=False,
                        )

            controller.runner = FakeRunner(
                inspections(
                    container_labels={
                        **immutable_labels,
                        **runtime_labels,
                        "unexpected.runtime.label": "forbidden",
                    }
                )
            )
            with self.assertRaisesRegex(ControllerError, "labels.*exact|label.*extra"):
                controller._inspect_container(
                    "9" * 64,
                    value,
                    "envoy",
                    track.value,
                    require_running=False,
                )

    def test_stopped_transient_validator_uses_exact_immutable_label_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            value = manifest()
            track = LiveTrack.SIGNED_STATE_ONLY
            runtime_labels = {
                "kil.v3b1.managed": "true",
                "kil.v3b1.run-id": value["run_id"],
                "kil.v3b1.role": "validator",
                "kil.v3b1.track": track.value,
            }
            immutable_labels = {"org.opencontainers.image.version": "22.04"}
            name = (
                f"kil-v3b1-validate-{track.value.replace('_', '-')}-"
                f"{str(value['content_identity_sha256'])[:12]}"
            )
            raw = {
                "Id": "8" * 64,
                "Name": f"/{name}",
                "Image": value["envoy_image_id"],
                "Config": {
                    "Image": value["envoy_image_digest"],
                    "Labels": {**immutable_labels, **runtime_labels},
                    "User": "65532:65532",
                    "Entrypoint": ["/usr/local/bin/envoy"],
                    "Cmd": [
                        "--mode",
                        "validate",
                        "--config-path",
                        "/etc/envoy/envoy.json",
                        "--disable-hot-restart",
                        "--concurrency",
                        "1",
                    ],
                },
                "HostConfig": {
                    "ReadonlyRootfs": True,
                    "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges"],
                    "NetworkMode": "none",
                    "PortBindings": {},
                },
                "State": {"Running": False},
            }
            image = {
                "Os": "linux",
                "Architecture": "arm64",
                "Config": {"Labels": immutable_labels},
            }
            controller = LocalEnvoyController(
                root,
                FakeRunner(
                    [
                        CommandResult(0, canonical_json(raw) + "\n", ""),
                        CommandResult(0, canonical_json(image) + "\n", ""),
                    ]
                ),
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
            )
            controller._prepare_private_roots()

            inspected = controller._inspect_validation_container(
                "8" * 64, value, track
            )

            self.assertEqual(inspected["labels"], runtime_labels)
            self.assertFalse(raw["State"]["Running"])

    def test_network_inspection_uses_one_closed_json_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            profile_path = root / "deploy/kind/v3b-profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_bytes(
                (ROOT / "deploy/kind/v3b-profile.json").read_bytes()
            )
            value = manifest()
            track = LiveTrack.CREDENTIAL_POLICY_BASELINE
            track_value = next(
                item for item in value["tracks"] if item["track"] == track.value
            )
            labels = {
                "kil.v3b1.managed": "true",
                "kil.v3b1.run-id": value["run_id"],
                "kil.v3b1.track": track.value,
            }
            member_names = [
                track_value["authz_container"],
                track_value["target_container"],
                track_value["envoy_container"],
            ]

            def member(name):
                return {
                    "Name": name,
                    "EndpointID": "e" * 64,
                    "MacAddress": "02:42:ac:12:00:02",
                    "IPv4Address": "172.18.0.2/16",
                    "IPv6Address": "",
                }

            network = {
                "Id": "a" * 64,
                "Name": track_value["network"],
                "Driver": "bridge",
                "Internal": True,
                "Labels": labels,
                "Containers": {
                    f"{index}" * 64: member(name)
                    for index, name in enumerate(member_names, start=1)
                },
                "Created": "2026-08-30T00:00:00Z",
                "Scope": "local",
            }
            observed_literal = (
                f"{network['Id']}\\n{network['Name']}\\nbridge\\ntrue\\n"
                f"{canonical_json(labels)}\n"
            )

            class NetworkRunner(FakeRunner):
                def __init__(self, payload):
                    super().__init__()
                    self.payload = payload

                def run(self, argv, **kwargs):
                    self.calls.append((list(argv), kwargs))
                    template = argv[argv.index("--format") + 1]
                    if template == "{{json .}}":
                        return CommandResult(
                            0, canonical_json(self.payload) + "\n", ""
                        )
                    return CommandResult(0, observed_literal, "")

            runner = NetworkRunner(network)
            controller = LocalEnvoyController(
                root,
                runner,
                home=Path(directory) / "home",
                port_probe=lambda port: False,
                tool_verifier=lambda: TOOL_IDENTITIES,
            )
            controller._prepare_private_roots()

            inspected = controller._inspect_network(
                "a" * 64, value, track.value
            )

            self.assertEqual(inspected["name"], track_value["network"])
            self.assertEqual(len(runner.calls), 1)
            self.assertIn("{{json .}}", runner.calls[0][0])

            partial = {**network, "Containers": {
                "1" * 64: member(member_names[0])
            }}
            controller.runner = NetworkRunner(partial)
            controller._inspect_network(
                "a" * 64,
                value,
                track.value,
                require_complete_membership=False,
            )

            malformed = {**network, "Internal": "true"}
            duplicate = {
                **network,
                "Containers": {
                    **network["Containers"],
                    "f" * 64: member(member_names[0]),
                },
            }
            unknown = {
                **network,
                "Containers": {
                    "f" * 64: member("kil-v3b1-attacker")
                },
            }
            extra_label = {
                **network,
                "Labels": {**labels, "kil.v3b1.role": "network"},
            }
            for rejected, message in (
                (malformed, "network.*type|shape"),
                (duplicate, "duplicate.*membership|membership"),
                (unknown, "cross-track|membership"),
                (extra_label, "label"),
            ):
                with self.subTest(message=message):
                    controller.runner = NetworkRunner(rejected)
                    with self.assertRaisesRegex(ControllerError, message):
                        controller._inspect_network(
                            "a" * 64,
                            value,
                            track.value,
                            require_complete_membership=False,
                        )

    def test_image_architecture_is_exact_linux_arm64(self):
        validate_image_architecture({"Os": "linux", "Architecture": "arm64"})
        with self.assertRaisesRegex(ControllerError, "architecture"):
            validate_image_architecture({"Os": "linux", "Architecture": "amd64"})

class EvidenceBundleTest(unittest.TestCase):
    def test_bundle_is_canonical_complete_checksummed_and_claim_bounded(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            output = write_evidence_bundle(
                root,
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )

            self.assertEqual(output.name, value["run_id"])
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {
                    "requests.jsonl",
                    "decisions.jsonl",
                    "envoy.jsonl",
                    "targets.jsonl",
                    "joins.jsonl",
                    "manifest.json",
                    "summary.md",
                    "SHA256SUMS",
                    "raw",
                },
            )
            for name in (
                "requests.jsonl",
                "decisions.jsonl",
                "envoy.jsonl",
                "targets.jsonl",
                "joins.jsonl",
            ):
                for line in (output / name).read_text().splitlines():
                    self.assertEqual(line, canonical_json(json.loads(line)))
            normalized = [
                json.loads(line)
                for line in (output / "decisions.jsonl").read_text().splitlines()
            ]
            self.assertTrue(
                all(
                    item["schema_version"]
                    == "kil.v3b1-collected-decision.v1"
                    and item["source_schema_version"]
                    == "kil.v3b-authz-record.v1"
                    and item["run_id_provenance"]
                    == "manifest_attested_enrichment"
                    for item in normalized
                )
            )
            with self.assertRaisesRegex(ControllerError, "attested resume"):
                write_evidence_bundle(
                    root,
                    value,
                    requests=requests,
                    decisions=decisions,
                    envoy=envoy,
                    targets=targets,
                    joins=joins,
                )
            manifest_line = (output / "manifest.json").read_text().strip()
            self.assertEqual(manifest_line, canonical_json(json.loads(manifest_line)))
            summary = (output / "summary.md").read_text().lower()
            self.assertIn("local_envoy_boundary", summary)
            self.assertIn("teardown: pending", summary)
            self.assertNotIn("teardown: complete", summary)
            for forbidden in (
                "kind_cluster_validated",
                "historical prevention",
                "production performance",
            ):
                self.assertNotIn(forbidden, summary)
            sums = (output / "SHA256SUMS").read_text().splitlines()
            self.assertEqual(len(sums), 10)
            for line in sums:
                digest, name = line.split("  ", 1)
                self.assertEqual(
                    digest, sha256((output / name).read_bytes()).hexdigest()
                )

            finalize_teardown_evidence(output, value["run_id"])
            finalized = json.loads((output / "manifest.json").read_text())
            self.assertEqual(finalized["teardown"]["status"], "complete")
            self.assertIn(
                "teardown: complete",
                (output / "summary.md").read_text().lower(),
            )
            for line in (output / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(
                    digest, sha256((output / name).read_bytes()).hexdigest()
                )

    def test_publication_is_atomic_sanitized_attested_and_checksum_complete(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provisional_parent = root / "private"
            provisional = write_evidence_bundle(
                provisional_parent,
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )
            authoritative = authoritative_bundle_attestation(provisional)
            public_parent = root / "public"
            def payload(records):
                return b"".join(
                    (canonical_json(record) + "\n").encode("utf-8")
                    for record in records
                )

            source_attestations = [
                {
                    "track": track.value,
                    "container_ids": {
                        "authz": f"{index + 1}" * 64,
                        "target": f"{index + 4}" * 64,
                        "envoy": f"{index + 7}" * 64,
                    },
                    "image_ids": {
                        "authz": KIL_IMAGE_ID,
                        "target": KIL_IMAGE_ID,
                        "envoy": f"sha256:{HEX_B}",
                    },
                    "config_sha256": {
                        "authz": HEX_A,
                        "target": HEX_A,
                        "envoy": HEX_A,
                    },
                    "raw_decisions_sha256": sha256(
                        (
                            provisional
                            / "raw/decisions"
                            / f"{track.value}.jsonl"
                        ).read_bytes()
                    ).hexdigest(),
                    "raw_decision_count": 1,
                    "raw_envoy_sha256": sha256(
                        payload(
                            [
                                record
                                for record in envoy
                                if record["track"] == track.value
                            ]
                        )
                    ).hexdigest(),
                    "raw_envoy_count": 1,
                    "raw_targets_sha256": sha256(
                        payload(
                            [
                                record
                                for record in targets
                                if record["track"] == track.value
                            ]
                        )
                    ).hexdigest(),
                    "raw_target_count": 0 if index == 2 else 1,
                }
                for index, track in enumerate(LiveTrack)
            ]

            extra_raw = provisional / "raw/decisions/extra.jsonl"
            extra_raw.write_text("{}\n")
            with self.assertRaisesRegex(ControllerError, "artifact set"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                )
            extra_raw.unlink()
            wrong_sources = [dict(item) for item in source_attestations]
            wrong_sources[0]["raw_decisions_sha256"] = HEX_A
            with self.assertRaisesRegex(ControllerError, "source bytes"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=wrong_sources,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                )

            missing_tool = dict(TOOL_IDENTITIES)
            missing_tool.pop("kubectl")
            with self.assertRaisesRegex(ControllerError, "tool.*closed|tool.*set"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=missing_tool,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                )
            extra_engine = {**ENGINE_PROVENANCE, "socket": "/Users/lab/docker.sock"}
            with self.assertRaisesRegex(ControllerError, "engine.*closed"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=extra_engine,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                )

            outside_public = root / "outside-public"
            outside_public.mkdir()
            linked_public = root / "linked-public"
            linked_public.symlink_to(outside_public, target_is_directory=True)
            with self.assertRaisesRegex(ControllerError, "symbolic|contained"):
                finalize_publication(
                    provisional,
                    linked_public,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                    repository_root=root,
                )
            linked_public.unlink()
            outside_staging = root / "outside-staging"
            outside_staging.mkdir()
            publication_staging = provisional.parent / ".publication-staging"
            publication_staging.symlink_to(
                outside_staging, target_is_directory=True
            )
            with self.assertRaisesRegex(ControllerError, "symbolic|contained"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                    repository_root=root,
                )
            publication_staging.unlink()

            authoritative_bytes = {
                path.relative_to(provisional).as_posix(): path.read_bytes()
                for path in provisional.rglob("*")
                if path.is_file()
            }

            for authoritative_name in (
                "requests.jsonl",
                "decisions.jsonl",
                "joins.jsonl",
            ):
                with self.subTest(authoritative_name=authoritative_name):
                    authoritative_path = provisional / authoritative_name
                    original = authoritative_path.read_bytes()
                    authoritative_path.chmod(0o600)
                    authoritative_path.write_bytes(original + b"\n")
                    sums_path = provisional / "SHA256SUMS"
                    original_sums = sums_path.read_bytes()
                    sums_path.chmod(0o600)
                    rewritten_sums = []
                    for line in original_sums.decode("ascii").splitlines():
                        _, relative = line.split("  ", 1)
                        digest = (
                            sha256(authoritative_path.read_bytes()).hexdigest()
                            if relative == authoritative_name
                            else line.split("  ", 1)[0]
                        )
                        rewritten_sums.append(f"{digest}  {relative}\n")
                    sums_path.write_text("".join(rewritten_sums), encoding="ascii")
                    sums_path.chmod(0o444)
                    with self.assertRaisesRegex(
                        ControllerError, "authoritative.*binding|authoritative.*changed"
                    ):
                        finalize_publication(
                            provisional,
                            public_parent,
                            value,
                            source_attestations=source_attestations,
                            tool_identities=TOOL_IDENTITIES,
                            engine_provenance=ENGINE_PROVENANCE,
                            global_context_before="personal",
                            global_context_after="personal",
                            completed=True,
                            authoritative_attestation=authoritative,
                        )
                    self.assertFalse((public_parent / value["run_id"]).exists())
                    authoritative_path.write_bytes(original)
                    authoritative_path.chmod(0o444)
                    sums_path.chmod(0o600)
                    sums_path.write_bytes(original_sums)
                    sums_path.chmod(0o444)
                    self.assertEqual(
                        {
                            path.relative_to(provisional).as_posix(): path.read_bytes()
                            for path in provisional.rglob("*")
                            if path.is_file()
                        },
                        authoritative_bytes,
                    )

            def fail_after_manifest(stage, path):
                if stage == "after_public_manifest":
                    raise RuntimeError("injected publication crash")

            with self.assertRaisesRegex(RuntimeError, "injected publication"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                    publication_fault=fail_after_manifest,
                )
            self.assertFalse((public_parent / value["run_id"]).exists())
            self.assertEqual(
                {
                    path.relative_to(provisional).as_posix(): path.read_bytes()
                    for path in provisional.rglob("*")
                    if path.is_file()
                },
                authoritative_bytes,
            )

            def mutate_staged_request(stage, path):
                if stage == "after_public_manifest":
                    request_path = path / "requests.jsonl"
                    request_path.chmod(0o600)
                    request_path.write_bytes(b"{}\n")

            with self.assertRaisesRegex(
                ControllerError, "artifact hash|source attestation|request"
            ):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                    publication_fault=mutate_staged_request,
                )
            self.assertFalse((public_parent / value["run_id"]).exists())
            self.assertEqual(
                {
                    path.relative_to(provisional).as_posix(): path.read_bytes()
                    for path in provisional.rglob("*")
                    if path.is_file()
                },
                authoritative_bytes,
            )

            def mutate_staged_summary(stage, path):
                if stage == "after_public_manifest":
                    summary_path = path / "summary.md"
                    summary_path.chmod(0o600)
                    summary_path.write_text("mutated staged summary\n")

            with self.assertRaisesRegex(ControllerError, "summary"):
                finalize_publication(
                    provisional,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                    publication_fault=mutate_staged_summary,
                )
            self.assertFalse((public_parent / value["run_id"]).exists())
            self.assertEqual(
                {
                    path.relative_to(provisional).as_posix(): path.read_bytes()
                    for path in provisional.rglob("*")
                    if path.is_file()
                },
                authoritative_bytes,
            )

            published = finalize_publication(
                provisional,
                public_parent,
                value,
                source_attestations=source_attestations,
                tool_identities=TOOL_IDENTITIES,
                engine_provenance=ENGINE_PROVENANCE,
                global_context_before="personal",
                global_context_after="personal",
                completed=True,
                authoritative_attestation=authoritative,
            )

            self.assertEqual(published, public_parent / value["run_id"])
            self.assertTrue(provisional.exists())
            self.assertEqual(
                {
                    path.relative_to(provisional).as_posix(): path.read_bytes()
                    for path in provisional.rglob("*")
                    if path.is_file()
                },
                authoritative_bytes,
            )
            public_manifest = json.loads(
                (published / "manifest.json").read_text()
            )
            encoded = canonical_json(public_manifest)
            self.assertNotIn("/Users/", encoded)
            self.assertNotIn("docker_host", public_manifest)
            self.assertEqual(
                public_manifest["bundle_class"],
                "intermediate_provisional_local_boundary",
            )
            self.assertEqual(public_manifest["promotion_status"], "not_promoted")
            self.assertEqual(
                public_manifest["evidence_policy"],
                {"inputs": "modeled", "outputs": "observed"},
            )
            self.assertEqual(
                public_manifest["source_attestations"], source_attestations
            )
            self.assertEqual(
                public_manifest["artifact_hash_rule"],
                "sha256_excludes_manifest_summary_and_SHA256SUMS",
            )
            self.assertEqual(
                public_manifest["authoritative_bundle_sha256"],
                authoritative["binding_sha256"],
            )
            verify_public_checksums(published)
            with self.assertRaisesRegex(ControllerError, "clobber"):
                finalize_publication(
                    published,
                    public_parent,
                    value,
                    source_attestations=source_attestations,
                    tool_identities=TOOL_IDENTITIES,
                    engine_provenance=ENGINE_PROVENANCE,
                    global_context_before="personal",
                    global_context_after="personal",
                    completed=True,
                    authoritative_attestation=authoritative,
                )

            extra = published / "unchecked.txt"
            extra.write_text("unchecked\n")
            with self.assertRaisesRegex(ControllerError, "unchecked|complete"):
                verify_public_checksums(published)
            extra.unlink()
            sums = (published / "SHA256SUMS").read_text().splitlines()
            (published / "SHA256SUMS").chmod(0o600)
            (published / "SHA256SUMS").write_text("\n".join(sums[:-1]) + "\n")
            with self.assertRaisesRegex(ControllerError, "omission|complete"):
                verify_public_checksums(published)

    def test_incomplete_run_publishes_nonpromotable_failure_bundle(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        joins = join_evidence(value, requests, decisions, envoy, targets)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provisional = write_evidence_bundle(
                root / "private",
                value,
                requests=requests,
                decisions=decisions,
                envoy=envoy,
                targets=targets,
                joins=joins,
            )
            authoritative = authoritative_bundle_attestation(provisional)
            published = finalize_publication(
                provisional,
                root / "public",
                value,
                source_attestations=[],
                tool_identities=TOOL_IDENTITIES,
                engine_provenance=ENGINE_PROVENANCE,
                global_context_before="default",
                global_context_after="default",
                completed=False,
                authoritative_attestation=authoritative,
            )
            manifest_value = json.loads((published / "manifest.json").read_text())
            self.assertFalse(manifest_value["run_complete"])
            self.assertEqual(manifest_value["promotion_status"], "not_promoted")
            self.assertIn("failure", manifest_value["bundle_class"])

    def test_incomplete_provisional_preserves_copied_partial_sources(self):
        value, requests, decisions, envoy, targets = JoinContractTest().all_records()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partial_raw = {
                track: (
                    (canonical_json(decisions[0]) + "\n").encode("utf-8")
                    if track is LiveTrack.CREDENTIAL_POLICY_BASELINE
                    else b""
                )
                for track in LiveTrack
            }

            output = _prepare_failure_provisional(
                root,
                value,
                requests=requests[:1],
                raw_decisions=partial_raw,
                envoy=envoy[:1],
                targets=targets[:1],
            )

            self.assertEqual(
                (output / "raw/decisions/credential_policy_baseline.jsonl").read_bytes(),
                partial_raw[LiveTrack.CREDENTIAL_POLICY_BASELINE],
            )
            self.assertEqual(len((output / "requests.jsonl").read_text().splitlines()), 1)
            self.assertEqual(len((output / "decisions.jsonl").read_text().splitlines()), 1)
            self.assertEqual(len((output / "envoy.jsonl").read_text().splitlines()), 1)
            self.assertEqual(len((output / "targets.jsonl").read_text().splitlines()), 1)
            self.assertEqual((output / "joins.jsonl").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
