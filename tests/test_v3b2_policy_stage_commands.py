"""Exact non-filtered reads for the pre-workload policy checkpoint."""
from dataclasses import replace
import unittest

from kil.v3b2_contracts import TRACK_NAMESPACES
from kil.v3b2_journal import Command, JournalError


def argv(namespace):
    return ("kubectl", "--kubeconfig", "/tmp/kil-v3-lab/kubeconfig", "get",
            "pods,deployments,replicasets", "--namespace", namespace, "--output", "json")


class PolicyStageCommandTest(unittest.TestCase):
    def test_accepts_exact_read_for_each_reviewed_namespace(self):
        for _, namespace in TRACK_NAMESPACES:
            try:
                command = Command(argv(namespace), 60)
            except JournalError as error:
                self.fail(f"policy-stage observation grammar missing: {error}")
            self.assertFalse(command.mutating)
            self.assertIsNone(command.stdin)

    def test_rejects_altered_scope_selectors_output_and_mutation(self):
        baseline = argv(TRACK_NAMESPACES[0][1])
        for position, value in ((3, "delete"), (4, "pods"), (5, "--all-namespaces"),
                                (6, "kube-system"), (8, "name")):
            changed = list(baseline)
            changed[position] = value
            with self.subTest(position=position), self.assertRaises(JournalError):
                Command(tuple(changed), 60)
        for tail in (("--selector", "app=driver"), ("--field-selector", "status.phase=Running"),
                     ("--watch",)):
            with self.subTest(tail=tail), self.assertRaises(JournalError):
                Command(baseline + tail, 60)
        for change in ({"stdin": b"{}\n"}, {"mutating": True}):
            with self.subTest(change=change), self.assertRaises(JournalError):
                replace(Command(baseline, 60), **change)


if __name__ == "__main__":
    unittest.main()
