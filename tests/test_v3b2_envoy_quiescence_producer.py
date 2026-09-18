"""Run the actual command script with only its network I/O leaves replaced.

Refusal diagnostics below are independently specified grammar fixtures, not
observations of the pinned Envoy image. Only AF_UNIX socket pairs are used;
there is no network listener or container runtime.
"""
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import tempfile
import threading
import unittest

from kil.v3b2_journal import OwnedIdentity, kubectl_envoy_quiesce_commands


REFUSED = (b"kil-v3b2-probe: connect: Connection refused\n"
           b"kil-v3b2-probe: line 1: /dev/tcp/127.0.0.1/8080: Connection refused\n")
GAUGES = ("http.kil_v3b_ingress.downstream_cx_active",
          "http.kil_v3b_ingress.downstream_rq_active",
          "cluster.kil-v3b-authz.upstream_rq_active",
          "cluster.kil-v3b-target.upstream_rq_active")
BODY = json.dumps({"stats": [{"name": name, "value": 0} for name in GAUGES]}, indent=2).encode()


def response(body=BODY, *, headers=b"", status=b"HTTP/1.1 200 OK", length=None):
    size = len(body) if length is None else length
    return status + b"\r\ncontent-length: " + str(size).encode() + b"\r\n" + headers + b"\r\n" + body


class EnvoyQuiescenceProducerTest(unittest.TestCase):
    def commands(self):
        return kubectl_envoy_quiesce_commands(
            OwnedIdentity(colima_profile="kil-v3-lab", kind_cluster="kil-v3-lab",
                          kubeconfig="/tmp/kil-v3-lab/kubeconfig",
                          cluster_incarnation_uid="11111111-1111-4111-8111-111111111111",
                          node_container_id="a" * 64,
                          docker_host="unix:///tmp/kil-v3-lab/docker.sock"),
            "kil-v3-baseline", "envoy-abc12")

    def run_producer(self, *, drain=False, stderr=REFUSED, stdout=b"", code=1,
                     reply=None, env=None, expired_deadline=False, stall_admin=False):
        command = self.commands()[0 if drain else 1]
        script = command.argv[-1]
        self.assertIn("\nmain\n", script, "producer needs a separately testable network boundary")
        left, right = socket.socketpair()
        request_bytes = []
        release_server = threading.Event()
        wire = response(b"OK\n") if drain else response()
        if reply is not None:
            wire = reply

        def serve():
            try:
                right.settimeout(3)
                request = b""
                while b"\r\n\r\n" not in request:
                    chunk = right.recv(4096)
                    if not chunk:
                        return
                    request += chunk
                request_bytes.append(request)
                if stall_admin:
                    release_server.wait(15)
                    return
                right.sendall(wire)
                right.shutdown(socket.SHUT_WR)
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                pass
            finally:
                right.close()

        thread = threading.Thread(target=serve)
        thread.start()
        # Replace only socket-open and child-exec leaves. The actual returned
        # command's producer, classification and HTTP parser run unmodified.
        # Bash printf %b can generate NUL/invalid bytes without command injection.
        escaped = lambda data: "".join("\\%03o" % byte for byte in data)
        overrides = ("\nprobe_child() { printf '%b' " + shlex.quote(escaped(stdout))
                     + "; printf '%b' " + shlex.quote(escaped(stderr)) + " >&2; return " + str(code) + "; }\n"
                     + "admin_open() { " + ("deadline=$SECONDS; " if expired_deadline else "")
                     + "exec 3<&" + str(left.fileno()) + "; }\n")
        script = script.removesuffix("\nmain\n") + overrides + "\nmain\n"
        try:
            result = subprocess.run(command.argv[-3:-1] + (script,),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    pass_fds=(left.fileno(),), timeout=15,
                                    env={**os.environ, **(env or {})})
        finally:
            left.close()
            release_server.set()
            thread.join(4)
        self.assertFalse(thread.is_alive())
        return result, request_bytes

    def test_startup_environment_is_suppressed(self):
        for command in self.commands():
            self.assertIn("p", command.argv[-2], "BASH_ENV runs before the current script can unset it")
        with tempfile.TemporaryDirectory() as temporary:
            startup = Path(temporary) / "startup.sh"
            startup.write_text("printf 'startup-ran' >&2; exit 99\n")
            result, _ = self.run_producer(env={"BASH_ENV": str(startup), "ENV": str(startup)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b"startup-ran", result.stderr)

    def test_exact_refusal_preserves_stats_body_and_issues_plain_http(self):
        result, requests = self.run_producer()
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertIs(value.pop("listener_refused"), True)
        self.assertEqual(value, json.loads(BODY))
        self.assertIn(BODY[1:], result.stdout)
        self.assertEqual(len(requests), 1)
        self.assertTrue(requests[0].startswith(b"GET /stats?format=json HTTP/1."))
        self.assertIn(b"Connection: close\r\n", requests[0])

    def test_drain_preserves_exact_success_protocol(self):
        result, requests = self.run_producer(drain=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'{"drain_requested":true}\n')
        self.assertTrue(requests[0].startswith(b"POST /drain_listeners HTTP/1."))
        self.assertIn(b"Content-Length: 0\r\n", requests[0])

    def test_admin_requests_use_supported_http11(self):
        for drain in (False, True):
            result, requests = self.run_producer(drain=drain)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b' HTTP/1.1\r\n', requests[0])
            self.assertNotIn(b'HTTP/1.0', requests[0])

    def test_chunked_admin_body_preserves_exact_decoded_bytes(self):
        header = b'HTTP/1.1 200 OK\r\ntransfer-encoding: chunked\r\nconnection: close\r\n\r\n'
        for drain, body in ((False, BODY), (True, b'OK\n')):
            parts = [body[:1], body[1:17], body[17:]]
            wire = header + b''.join(format(len(x), 'x').encode() + b'\r\n' + x + b'\r\n'
                                     for x in parts if x) + b'0\r\n\r\n'
            result, _ = self.run_producer(drain=drain, reply=wire)
            self.assertEqual(result.returncode, 0, result.stderr)
            if drain:
                self.assertEqual(result.stdout, b'{"drain_requested":true}\n')
            else:
                self.assertIn(BODY[1:], result.stdout)
                self.assertEqual(json.loads(result.stdout)['stats'], json.loads(BODY)['stats'])

    def test_malformed_or_ambiguous_chunked_responses_refuse(self):
        header = b'HTTP/1.1 200 OK\r\ntransfer-encoding: chunked\r\n\r\n'
        payloads = (b'g\r\n', b'100001\r\n', b'1;foo=bar\r\nx\r\n0\r\n\r\n',
                    b'1\r\n', b'2\r\nx\r\n0\r\n\r\n', b'1\r\nxXX0\r\n\r\n',
                    b'1\r\n\0\r\n0\r\n\r\n', b'0\r\ntrailer: x\r\n\r\n',
                    b'0\r\n\r\nextra')
        wires = [header + x for x in payloads]
        wires += [b'HTTP/1.1 200 OK\r\ntransfer-encoding: gzip\r\n\r\n0\r\n\r\n',
                  b'HTTP/1.1 200 OK\r\ntransfer-encoding: chunked\r\ntransfer-encoding: chunked\r\n\r\n0\r\n\r\n']
        for wire in wires:
            with self.subTest(wire=wire[:100]):
                result, _ = self.run_producer(reply=wire)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b'')

    def test_refusal_requires_complete_exact_diagnostic_and_exit(self):
        fixtures = [dict(code=0), dict(code=2), dict(code=124), dict(code=143),
                    dict(stderr=b""), dict(stderr=REFUSED[:-1]),
                    dict(stderr=REFUSED + b"extra\n"), dict(stderr=b"extra\n" + REFUSED),
                    dict(stderr=REFUSED.replace(b"8080", b"9901")),
                    dict(stderr=REFUSED.replace(b"line 1", b"line 2")),
                    dict(stderr=REFUSED + b"x" * 2048), dict(stderr=REFUSED + b"\0"),
                    dict(stdout=b"x"), dict(stdout=b"\0"),
                    dict(stdout=REFUSED, stderr=b"")]
        for text in (b"Permission denied", b"Network is unreachable", b"No route to host",
                     b"Connection reset by peer", b"Connection timed out", b"Connexion refusee"):
            fixtures.append(dict(stderr=REFUSED.replace(b"Connection refused", text)))
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                result, requests = self.run_producer(**fixture)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(requests, [])

    def test_http_framing_failures_never_emit_success(self):
        replies = [response(status=b"HTTP/1.1 503 Service Unavailable"),
                   response(length=len(BODY) + 1), response(length=len(BODY) - 1),
                   response(headers=b"content-length: 1\r\n"),
                   response(headers=b"transfer-encoding: chunked\r\n"),
                   response(headers=b"x-extra: " + b"x" * 8193 + b"\r\n"),
                   response(length=1048577), response(body=b"x" * 1048577),
                   b"HTTP/1.1 200 OK\n\n" + BODY, b"HTTP/1.1 200 OK\r\n",
                   response(headers=b"bad header\r\n"), response(body=BODY + b"\0")]
        for reply in replies:
            with self.subTest(reply=reply[:120]):
                result, _ = self.run_producer(reply=reply)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")

    def test_gauges_remain_unmodified_for_authoritative_proof_validator(self):
        for rows in ([{"name": GAUGES[0], "value": 1}], [],
                     [{"name": GAUGES[0], "value": 0}] * 2):
            body = json.dumps({"stats": rows}).encode()
            result, _ = self.run_producer(reply=response(body))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["stats"], rows)

    def test_expired_deadline_never_emits_success(self):
        result, _ = self.run_producer(expired_deadline=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"timeout", result.stderr)

    def test_stalled_admin_read_is_bounded_inside_producer(self):
        result, _ = self.run_producer(stall_admin=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"http_line_incomplete", result.stderr)

    def test_incomplete_probe_retains_bounded_diagnostic_prefix(self):
        result, _ = self.run_producer(stderr=REFUSED + b"x" * 2048)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertTrue(result.stderr.startswith(REFUSED), result.stderr)
        self.assertIn(b"probe_incomplete", result.stderr)
        self.assertLess(len(result.stderr), 1200)

    def proof_decision(self, result):
        from dataclasses import asdict
        from kil import v3b2_proofs as proofs
        from kil.v3b2_contracts import TRACK_NAMESPACES
        identity = OwnedIdentity("kil-v3-lab", "unix:///tmp/kil-v3-lab/docker.sock", "kil-v3-lab",
                                 "/tmp/kil-v3-lab/kubeconfig", "cluster-uid", "a" * 64)
        bindings, observations = [], []
        image = "docker.io/envoyproxy/envoy@sha256:" + "e" * 64
        for _, namespace in TRACK_NAMESPACES:
            binding = {"namespace": namespace, "pod": "envoy-abc12", "uid": namespace + "-uid",
                       "container_id": "containerd://" + "b" * 64, "image": image}
            bindings.append(binding)
            pod = {"apiVersion": "v1", "kind": "Pod",
                   "metadata": {"name": binding["pod"], "namespace": namespace,
                                "uid": binding["uid"], "resourceVersion": "1"},
                   "status": {"conditions": [{"type": "Ready", "status": "True"}],
                              "containerStatuses": [{"name": "envoy", "image": image,
                                  "imageID": "docker-pullable://" + image, "containerID": binding["container_id"],
                                  "ready": True, "state": {"running": {}}}]}}
            argv = ("kubectl", "--kubeconfig", identity.kubeconfig, "get", "pod", binding["pod"],
                    "--namespace", namespace, "--output", "json")
            for phase in ("before", "after"):
                observations.append(proofs.RawObservation(namespace + ":" + phase, argv, (), 0,
                                                         proofs.canonical(pod), b""))
            command = kubectl_envoy_quiesce_commands(identity, namespace, binding["pod"])[1]
            observations.append(proofs.RawObservation(namespace + ":stats", command.argv, (), result.returncode,
                                                     result.stdout, result.stderr))
        context = proofs.ExpectedContext("a" * 64, 1, "envoy_quiesce", b"{}\n",
                                         proofs.canonical({"owned_identity": asdict(identity),
                                                           "envoy_bindings": bindings}))
        return proofs.decide(context, tuple(observations))

    def test_producer_output_and_shared_validator_agree(self):
        result, _ = self.run_producer()
        self.assertEqual(self.proof_decision(result).outcome, "complete")
        malformed = [b'{"stats": [}', b'{"stats": []}{"stats": []}',
                     b'{"stats": [], "listener_refused": false}',
                     b'{"stats": [], "stats": []}', b'{"stats": [], "extra": true}',
                     b'[]', b'{"stats": []}garbage']
        bad_gauges = [[], [{"name": name, "value": 0} for name in GAUGES[:-1]],
                      [{"name": name, "value": 0} for name in (*GAUGES, GAUGES[0])],
                      [{"name": name, "value": 1} for name in GAUGES],
                      [{"name": name, "value": False} for name in GAUGES]]
        for body in malformed + [json.dumps({"stats": rows}).encode() for rows in bad_gauges]:
            with self.subTest(body=body):
                result, _ = self.run_producer(reply=response(body))
                self.assertEqual(self.proof_decision(result).outcome, "unknown")


if __name__ == "__main__":
    unittest.main()
