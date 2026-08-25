import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = ROOT / "research/source-material/claude-origin-conversation.json"
MANIFEST_PATH = ROOT / "research/source-material/TRANSITION-MANIFEST.json"
CONVERSATION_UUID = "9a53e1b5-61c4-4f86-ae36-049675efe6ba"


class TransitionRecordTest(unittest.TestCase):
    def load_record(self):
        self.assertTrue(RECORD_PATH.is_file(), "the public-safe Claude record must exist")
        return json.loads(RECORD_PATH.read_text(encoding="utf-8"))

    def test_record_contains_the_complete_visible_conversation(self):
        record = self.load_record()
        self.assertEqual(record["conversation"]["uuid"], CONVERSATION_UUID)
        messages = record["conversation"]["messages"]
        self.assertEqual(len(messages), 16)
        self.assertEqual(sum(m["sender"] == "human" for m in messages), 8)
        self.assertEqual(sum(m["sender"] == "assistant" for m in messages), 8)
        self.assertIn("cybersecurity and AI", messages[0]["text"])
        self.assertIn("agent-intrusion-technical-timeline", messages[8]["text"])

    def test_public_record_excludes_private_export_material(self):
        record = self.load_record()
        keys = set()

        def collect_keys(value):
            if isinstance(value, dict):
                keys.update(value)
                for nested in value.values():
                    collect_keys(nested)
            elif isinstance(value, list):
                for nested in value:
                    collect_keys(nested)

        collect_keys(record)
        for forbidden in ("account", "thinking", "tool_use", "tool_result",
                          "signature", "export_url"):
            self.assertNotIn(forbidden, keys)

    def test_transition_manifest_documents_the_extraction(self):
        self.assertTrue(MANIFEST_PATH.is_file(), "the transition manifest must exist")
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["conversation_uuid"], CONVERSATION_UUID)
        self.assertEqual(manifest["visible_message_count"], 16)
        self.assertEqual(manifest["excluded_content_types"],
                         ["thinking", "tool_use", "tool_result"])

    def test_private_export_directory_is_ignored(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("research/private/", gitignore.splitlines())


if __name__ == "__main__":
    unittest.main()
