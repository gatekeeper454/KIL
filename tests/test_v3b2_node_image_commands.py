"""Exact read-only CRI inspection grammar; no runtime process is executed."""
from dataclasses import replace
import unittest

from kil.v3b2_journal import Command, JournalError


NODE = "a" * 64
REFERENCES = ("kil.local/kil-v3b2:sha256-" + "b" * 64,
              "docker.io/envoyproxy/envoy@sha256:" + "c" * 64)
ENV = (("DOCKER_CONFIG", "/tmp/kil-private/docker-config"),
       ("DOCKER_HOST", "unix:///tmp/colima/kil-v3-lab/docker.sock"))


def argv(reference=REFERENCES[0]):
    return ("docker", "exec", NODE, "/usr/local/bin/crictl",
            "--runtime-endpoint", "unix:///run/containerd/containerd.sock",
            "--image-endpoint", "unix:///run/containerd/containerd.sock",
            "--timeout", "10s", "inspecti", "--quiet", "--output", "json", reference)


class NodeImageCommandTest(unittest.TestCase):
    def test_accepts_only_exact_scoped_read_only_inspection(self):
        for reference in REFERENCES:
            with self.subTest(reference=reference):
                command = Command(argv(reference), 30, env=ENV)
                self.assertFalse(command.mutating)
                self.assertIsNone(command.stdin)
                self.assertEqual(command.env, ENV)

    def test_rejects_changed_node_program_endpoint_flags_and_reference(self):
        mutations = {2: "kil-v3-lab-control-plane", 3: "/bin/sh",
                     4: "--runtime-endpoint=unix:///run/containerd/containerd.sock",
                     5: "unix:///other.sock", 7: "tcp://127.0.0.1:1234",
                     9: "0", 10: "pull", 11: "--verbose", 13: "yaml",
                     14: "docker.io/foreign/image:latest"}
        for position, value in mutations.items():
            changed = list(argv())
            changed[position] = value
            with self.subTest(position=position), self.assertRaises(JournalError):
                Command(tuple(changed), 30, env=ENV)
        for changed in (argv()[:-1], argv() + (REFERENCES[1],), argv() + ("--quiet",)):
            with self.subTest(argv=changed), self.assertRaises(JournalError):
                Command(changed, 30, env=ENV)

    def test_rejects_mutation_stdin_and_foreign_or_missing_docker_authority(self):
        command = Command(argv(), 30, env=ENV)
        for change in ({"mutating": True}, {"stdin": b"{}"}, {"env": ()},
                       {"env": (("DOCKER_CONFIG", ENV[0][1]),
                                ("DOCKER_HOST", "unix:///tmp/colima/attackswarm/docker.sock"))}):
            with self.subTest(change=change), self.assertRaises(JournalError):
                replace(command, **change)


if __name__ == "__main__":
    unittest.main()
