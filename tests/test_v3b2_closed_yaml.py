"""Independent contract tests for the bounded closed-YAML decoder."""

import unittest
from decimal import Decimal
from unittest.mock import patch

from kil import v3b2_closed_yaml as closed_yaml_module
from kil.v3b2_closed_yaml import ClosedYAMLError, decode_closed_yaml


class StringSubclass(str):
    pass


class ClosedYAMLTest(unittest.TestCase):
    def assertInvalid(self, value):
        with self.assertRaises(ClosedYAMLError):
            decode_closed_yaml(value)

    def test_representative_kubeadm_document(self):
        text = """apiVersion: kubeadm.k8s.io/v1beta4
kind: ClusterConfiguration
kubernetesVersion: v1.36.1
networking:
  dnsDomain: cluster.local
  podSubnet: 192.168.0.0/16
  serviceSubnet: 10.96.0.0/12
apiServer:
  certSANs:
  - 10.0.0.1
  - kil-v3-lab-control-plane
  extraArgs:
  - name: authorization-mode
    value: Node,RBAC
controllerManager:
  extraArgs: []
featureGates: {}
"""
        self.assertEqual(
            decode_closed_yaml(text),
            {
                "apiVersion": "kubeadm.k8s.io/v1beta4",
                "kind": "ClusterConfiguration",
                "kubernetesVersion": "v1.36.1",
                "networking": {
                    "dnsDomain": "cluster.local",
                    "podSubnet": "192.168.0.0/16",
                    "serviceSubnet": "10.96.0.0/12",
                },
                "apiServer": {
                    "certSANs": ["10.0.0.1", "kil-v3-lab-control-plane"],
                    "extraArgs": [{"name": "authorization-mode", "value": "Node,RBAC"}],
                },
                "controllerManager": {"extraArgs": []},
                "featureGates": {},
            },
        )

    def test_representative_kubelet_and_scalar_types(self):
        text = """kind: KubeletConfiguration
apiVersion: kubelet.config.k8s.io/v1beta1
clusterDNS:
- 10.96.0.10
clusterDomain: cluster.local
rotateCertificates: true
failSwapOn: false
shutdownGracePeriod: 0s
imageMaximumGCAge: 2m0s
maxPods: 110
oomScoreAdj: -999
reservedSystemCPUs: null
staticPodPath: /etc/kubernetes/manifests
"""
        value = decode_closed_yaml(text)
        self.assertEqual(value["clusterDNS"], ["10.96.0.10"])
        self.assertIs(value["rotateCertificates"], True)
        self.assertIs(value["failSwapOn"], False)
        self.assertEqual(value["maxPods"], 110)
        self.assertEqual(value["oomScoreAdj"], -999)
        self.assertIsNone(value["reservedSystemCPUs"])
        self.assertEqual(value["shutdownGracePeriod"], "0s")

    def test_representative_kube_proxy_and_kubeconfig_shapes(self):
        text = """apiVersion: kubeproxy.config.k8s.io/v1alpha1
kind: KubeProxyConfiguration
mode: iptables
clusterCIDR: 192.168.0.0/16
clientConnection:
  kubeconfig: /var/lib/kube-proxy/kubeconfig.conf
  qps: 0
iptables:
  masqueradeAll: false
clusters:
- cluster:
    certificate-authority-data: Y2EtYnl0ZXM=
    server: https://[::1]:6443/api/v1
  name: ''
contexts: []
users: null
current-context: ""
preferences: {}
"""
        value = decode_closed_yaml(text)
        self.assertEqual(value["clusters"][0]["name"], "")
        self.assertEqual(value["clusters"][0]["cluster"]["server"],
                         "https://[::1]:6443/api/v1")
        self.assertEqual(value["users"], None)

    def test_nested_sequences_maps_and_sequence_scalars(self):
        text = """root:
  matrix:
  -
    - one
    - two
  records:
    - name: first
      values:
        - 1
        - 2
    - name: second
      values: []
"""
        self.assertEqual(
            decode_closed_yaml(text),
            {"root": {"matrix": [["one", "two"]], "records": [
                {"name": "first", "values": [1, 2]},
                {"name": "second", "values": []},
            ]}},
        )

    def test_bare_dash_sequence_mapping_uses_one_canonical_indent_step(self):
        self.assertEqual(
            decode_closed_yaml("root:\n  -\n    key: value\n"),
            {"root": [{"key": "value"}]},
        )
        self.assertInvalid("root:\n  -\n      key: value\n")

    def test_quotes_and_reordered_mappings_are_semantic(self):
        first = decode_closed_yaml(
            "a: 'can''t'\nb: \"quote: \\\"yes\\\"\"\nc: null\npath: 'C:\\path'\n")
        second = decode_closed_yaml(
            "path: 'C:\\path'\nc: null\nb: \"quote: \\\"yes\\\"\"\na: 'can''t'\n")
        self.assertEqual(first, second)
        self.assertEqual(first, {"a": "can't", "b": 'quote: "yes"', "c": None,
                                 "path": "C:\\path"})

    def test_empty_input_or_non_mapping_root_is_rejected(self):
        self.assertEqual(decode_closed_yaml("{}\n"), {})
        self.assertIs(type(decode_closed_yaml("{}\n")), dict)
        for value in ("", "\n", "- item\n", "[]\n", "null\n"):
            with self.subTest(value=value):
                self.assertInvalid(value)

    def test_duplicate_keys_fail_at_root_and_nested_depths(self):
        for value in (
            "a: one\na: two\n",
            "a:\n  b: one\n  b: two\n",
            "a:\n- name: one\n  name: two\n",
        ):
            with self.subTest(value=value):
                self.assertInvalid(value)

    def test_non_string_key_forms_are_rejected(self):
        for key in ("1", "true", "null", "[name]", "{name}", "'name'", '"name"'):
            with self.subTest(key=key):
                self.assertInvalid(f"{key}: value\n")

    def test_transport_and_line_hazards_are_rejected(self):
        for value in (
            "a: b\r\n", "a:\tb\n", "\ufeffa: b\n", "a: b \n",
            "a: b\n\n", "a: \x00\n", "a: \x1f\n", "a: \ud800\n",
        ):
            with self.subTest(value=repr(value)):
                self.assertInvalid(value)

    def test_directives_markers_comments_and_multiple_roots_are_rejected(self):
        for value in (
            "%YAML 1.2\na: b\n", "---\na: b\n", "a: b\n...\n",
            "# comment\na: b\n", "a: b # comment\n", "a: b\norphan\n",
        ):
            with self.subTest(value=value):
                self.assertInvalid(value)

    def test_yaml_graph_and_typed_syntax_is_rejected(self):
        for scalar in (
            "!str value", "&anchor value", "*anchor", "value &anchor",
            "value *anchor", "!!binary YQ==", "|", ">", "|-", ">+",
        ):
            with self.subTest(scalar=scalar):
                self.assertInvalid(f"a: {scalar}\n")
        self.assertInvalid("base: &base\n  x: y\ncopy:\n  <<: *base\n")

    def test_nonempty_flow_collections_are_rejected(self):
        for scalar in ("[one]", "[one, two]", "{a: b}", "{a: b, c: d}"):
            with self.subTest(scalar=scalar):
                self.assertInvalid(f"a: {scalar}\n")

    def test_yaml_1_1_ambiguous_scalars_are_rejected_unless_quoted(self):
        ambiguous = (
            "y", "Y", "n", "N", "yes", "Yes", "YES", "no", "NO", "on", "Off",
            "TRUE", "False",
            "Null", "NULL", "~", "01", "-01", "+1", "0x10", "0o10", "0123",
            "1.0", "1e3", "-2.5", ".5", "-.5", ".inf", "-.Inf", ".NaN",
            "12:34", "12:34:56", "12:34.5", "1:02:03.004", "1:20.",
            "1:02:03.",
            "2026-09-07", "2026-09-07T12:00:00Z",
        )
        for scalar in ambiguous:
            with self.subTest(scalar=scalar):
                self.assertInvalid(f"a: {scalar}\n")
                self.assertEqual(decode_closed_yaml(f'a: "{scalar}"\n'), {"a": scalar})

    def test_malformed_quotes_and_escapes_are_rejected(self):
        for scalar in ('"unterminated', '"bad\\q"', '"bad\x01"', "'unterminated",
                       "'bad'quote'"):
            with self.subTest(scalar=repr(scalar)):
                self.assertInvalid(f"a: {scalar}\n")

    def test_escaped_control_and_surrogate_text_is_rejected(self):
        for scalar in ('"bad\\u0000"', '"bad\\u001f"', '"bad\\u007f"',
                       '"bad\\ud800"'):
            with self.subTest(scalar=scalar):
                self.assertInvalid(f"a: {scalar}\n")

    def test_hash_and_yaml_indicators_are_safe_when_quoted(self):
        self.assertEqual(
            decode_closed_yaml('a: "# ! & * | > [x] {y}"\n'),
            {"a": "# ! & * | > [x] {y}"},
        )

    def test_plain_indicator_tokens_are_rejected(self):
        for scalar in ("-", "?", ":", "value:", "- value", "? value", "]value",
                       ",value"):
            with self.subTest(scalar=scalar):
                self.assertInvalid(f"a: {scalar}\n")

    def test_indentation_must_be_consistent(self):
        for value in (
            "a:\n b: c\n", "a:\n    b: c\n", "a:\n  b: c\n c: d\n",
            "a:\n  - one\n   - two\n", "a: b\n  c: d\n",
            "a:\n- one\n  - two\n",
        ):
            with self.subTest(value=value):
                self.assertInvalid(value)

    def test_scalar_and_key_utf8_bounds(self):
        permitted = "x" * (256 * 1024)
        self.assertEqual(decode_closed_yaml(f"a: {permitted}\n")["a"], permitted)
        self.assertEqual(decode_closed_yaml(f'a: "{permitted}"\n')["a"], permitted)
        self.assertInvalid(f"a: {'x' * (256 * 1024 + 1)}\n")
        self.assertInvalid(f"{'k' * (256 * 1024 + 1)}: value\n")

    def test_canonical_integer_is_limited_by_scalar_bytes_not_runtime_defaults(self):
        digits = "9" * 5_000
        for sign in ("", "-"):
            with self.subTest(sign=sign):
                value = decode_closed_yaml(f"large: {sign}{digits}\n")["large"]
                self.assertIs(type(value), int)
                self.assertEqual(value, int(Decimal(sign + digits)))

    def test_integer_work_cap_rejects_before_decimal_conversion(self):
        for sign in ("", "-"):
            with self.subTest(sign=sign), patch.object(
                    closed_yaml_module, "Decimal",
                    side_effect=AssertionError("conversion must not be reached")) as conversion:
                self.assertInvalid(f"large: {sign}{'9' * 5_001}\n")
                conversion.assert_not_called()

    def test_raw_and_json_escaped_bom_are_equally_rejected(self):
        for value in ('a: "\ufeff"\n', 'a: "\\ufeff"\n'):
            with self.subTest(value=repr(value)):
                self.assertInvalid(value)

    def test_single_quote_bound_counts_decoded_apostrophes_before_join(self):
        encoded_boundary = "''" * (256 * 1024)
        decoded = decode_closed_yaml(f"a: '{encoded_boundary}'\n")["a"]
        self.assertEqual(len(decoded), 256 * 1024)
        self.assertEqual(decoded[:2], "''")
        self.assertEqual(decoded[-2:], "''")

        adversarial = "''" * (256 * 1024 + 1)
        with patch.object(closed_yaml_module, "_text_bytes",
                          wraps=closed_yaml_module._text_bytes) as byte_validation:
            self.assertInvalid(f"a: '{adversarial}'\n")
        self.assertNotIn("quoted scalar",
                         [observed.args[0] for observed in byte_validation.call_args_list])

    def test_input_bytes_node_line_and_depth_bounds(self):
        self.assertInvalid("a" * (1024 * 1024 + 1))
        self.assertInvalid("\n" * 65_536)
        wide = "root:\n" + "".join(f"  k{i}: v\n" for i in range(32_768))
        self.assertInvalid(wide)
        deep = "root:\n" + "".join("  " * depth + f"k{depth}:\n"
                                    for depth in range(1, 65)) + "  " * 65 + "leaf: x\n"
        self.assertInvalid(deep)

    def test_hostile_width_fails_without_scheduling_unbounded_state(self):
        # An indentless sequence can otherwise append an arbitrary pending frontier.
        value = "root:\n" + "".join("- x\n" for _ in range(32_769))
        self.assertInvalid(value)

    def test_mapping_keys_count_toward_the_exact_semantic_node_bound(self):
        boundary = "items:\n- value\n" + "".join(
            f"k{i}: value\n" for i in range(16_382)
        )
        result = decode_closed_yaml(boundary)
        self.assertEqual(len(result), 16_383)
        self.assertEqual(result["items"], ["value"])

        over = "".join(f"k{i}: value\n" for i in range(16_384))
        self.assertInvalid(over)

    def test_constructor_and_result_types_are_exact(self):
        for value in (b"a: b\n", StringSubclass("a: b\n"), None, {"a": "b"}):
            with self.subTest(type=type(value)):
                self.assertInvalid(value)
        result = decode_closed_yaml("a:\n- b\n- c: 1\n  d: false\n")
        self.assertIs(type(result), dict)
        self.assertIs(type(result["a"]), list)
        self.assertIs(type(result["a"][0]), str)
        self.assertIs(type(result["a"][1]), dict)
        self.assertIs(type(result["a"][1]["c"]), int)
        self.assertIs(type(result["a"][1]["d"]), bool)

    def test_export_surface_is_an_immutable_exact_tuple(self):
        self.assertIs(type(closed_yaml_module.__all__), tuple)
        self.assertEqual(closed_yaml_module.__all__,
                         ("ClosedYAMLError", "decode_closed_yaml"))


if __name__ == "__main__":
    unittest.main()
