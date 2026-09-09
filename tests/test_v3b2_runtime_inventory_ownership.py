"""Runtime command and same-payload ownership integration; no runtime startup."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from kil.v3b2_inventory import InventoryError, parse_runtime_inventory
from kil.v3b2_journal import Command, JournalError
from kil.v3b2_manifests import WorkloadIdentity, render_objects
from kil.v3b2_proofs import RUNTIME_RESOURCES
from tests.test_v3b2_controller import raw_runtime_inventory, KIL_MANIFEST_DIGEST, ENVOY_MANIFEST_DIGEST
from tests.test_v3b2_runtime_endpoints import fixture as endpoints_fixture
from tests.test_v3b2_runtime_ownership import encode

TOKEN = "namespaces,pods,services,endpoints,endpointslices,serviceaccounts,configmaps,deployments,daemonsets,networkpolicies,nodes,replicasets"


def fixture():
    args = endpoints_fixture()
    workload = WorkloadIdentity("v3b2-" + "1" * 64, "sha256:" + KIL_MANIFEST_DIGEST,
                                "docker.io/envoyproxy/envoy@sha256:" + ENVOY_MANIFEST_DIGEST)
    args.update(workload=workload, rendered_objects=render_objects(args["profile"], workload))
    document = json.loads(args["runtime_objects"])
    rows = document["items"]
    key = lambda row: (row["apiVersion"], row["kind"], row["metadata"].get("namespace", ""), row["metadata"]["name"])
    by_key = {key(row): row for row in rows}
    for index, row in enumerate(json.loads(args["rendered_objects"])["items"]):
        if key(row) not in by_key:
            row["metadata"].update(uid=f"rendered-{index}", resourceVersion="900")
            rows.append(row); by_key[key(row)] = row
        elif row["kind"] == "Deployment": by_key[key(row)]["spec"] = deepcopy(row["spec"])
    legacy = json.loads(raw_runtime_inventory())["items"]
    for index, row in enumerate(legacy):
        if row["kind"] in {"ServiceAccount", "ConfigMap", "Namespace"} and key(row) not in by_key:
            row["metadata"].update(uid=f"platform-extra-{index}", resourceVersion="901")
            rows.append(row); by_key[key(row)] = row
    # Ownership/endpoint API paths share actual UIDs. KIL runtime identities
    # below intentionally differ from requested manifest/index references; the
    # old image projection remains an explicit independent parser blocker.
    for row in rows:
        if row["kind"] != "Pod": continue
        namespace, name = row["metadata"]["namespace"], row["metadata"]["name"]
        role = "driver" if name == "driver" else next((role for role in
            ("calico-kube-controllers", "calico-node", "authz", "envoy", "target") if name.startswith(role + "-")), None)
        if role is not None:
            candidate = next(item for item in legacy if item["kind"] == "Pod"
                and item["metadata"].get("namespace") == namespace
                and any(status["name"] == role for status in item.get("status", {}).get("containerStatuses", [])))
            row.setdefault("status", {}).update(deepcopy(candidate["status"]))
            if namespace.startswith("kil-"):
                for status in row["status"]["containerStatuses"]:
                    if status["name"] == "envoy":
                        status["image"] = "sha256:ef846ec85aabf01a2ff7176a185260e476ca43d20478f57281d88f7a66d5671f"
                        status["imageID"] = "docker.io/envoyproxy/envoy@sha256:" + ENVOY_MANIFEST_DIGEST
                    else:
                        status["imageID"] = "sha256:f21285be21c8f691b9b60b7e38bb309564a5cc238512c7455eb7759f4d922ddb"
    for row in rows:
        if row["kind"] == "DaemonSet" and row["metadata"]["name"] == "calico-node": row["status"].update(numberReady=1)
        if row["kind"] == "Deployment" and row["metadata"]["name"] == "calico-kube-controllers": row["status"].update(replicas=1, readyReplicas=1)
    for row in list(rows):
        if row["kind"] == "EndpointSlice" and row["metadata"]["namespace"].startswith("kil-"):
            service = row["metadata"]["labels"]["kubernetes.io/service-name"]
            rows.append({"apiVersion": "v1", "kind": "Endpoints", "metadata": {
                "namespace": row["metadata"]["namespace"], "name": service,
                "uid": "legacy-" + row["metadata"]["uid"], "resourceVersion": "902"},
                "subsets": [{"addresses": [{"ip": row["endpoints"][0]["addresses"][0]}], "ports": deepcopy(row["ports"])}]})
    args["runtime_objects"] = encode(document)
    return args


class RuntimeInventoryOwnershipTest(unittest.TestCase):
    def parse(self, args):
        return parse_runtime_inventory(args["runtime_objects"], profile=args["profile"], workload=args["workload"],
            node_container_id=args["owned_identity"].node_container_id, docker_host=args["owned_identity"].docker_host,
            owned_identity=args["owned_identity"])

    def test_exact_runtime_token_and_closed_command_grammar(self):
        self.assertEqual(RUNTIME_RESOURCES, TOKEN)
        argv = ("kubectl", "--kubeconfig", "/tmp/owned/kubeconfig", "get", TOKEN, "--all-namespaces", "--output", "json")
        Command(argv, 60)
        for changed in (argv[:4] + (TOKEN.rsplit(",", 2)[0],) + argv[5:],
                        argv[:4] + (TOKEN.replace("nodes,replicasets", "replicasets,nodes"),) + argv[5:],
                        (*argv, "--watch"), (*argv, "--selector=app=foreign")):
            with self.assertRaises(JournalError): Command(changed, 60)
        from kil.v3b2_journal import _evidence_freeze_commands
        self.assertEqual(_evidence_freeze_commands(fixture()["owned_identity"], ())[-1].argv[4], TOKEN)

    def test_owned_full_source_passes_ownership_but_keeps_distinct_image_identity_gate_closed(self):
        from kil.v3b2_runtime_ownership import validate_runtime_ownership
        args = fixture()
        ownership = validate_runtime_ownership(**args)
        self.assertEqual(len(ownership.deployment_ownership.bindings), 12)
        with self.assertRaisesRegex(InventoryError, "runtime same-source KIL image proof is invalid or missing"):
            self.parse(args)

    def test_missing_extra_node_or_orphan_replica_set_fails(self):
        for kind in ("Node", "ReplicaSet"):
            for mode in ("missing", "extra", "owner"):
                args = fixture(); document = json.loads(args["runtime_objects"])
                index = next(i for i, row in enumerate(document["items"]) if row["kind"] == kind)
                if mode == "missing": document["items"].pop(index)
                elif mode == "extra":
                    extra = deepcopy(document["items"][index]); extra["metadata"].update(name="foreign", uid="foreign")
                    document["items"].append(extra)
                elif kind == "ReplicaSet": document["items"][index]["metadata"]["ownerReferences"][0]["uid"] = "foreign"
                else: document["items"][index]["metadata"]["name"] = "foreign"
                args["runtime_objects"] = encode(document)
                with self.subTest(kind=kind, mode=mode), self.assertRaises(InventoryError): self.parse(args)

    def test_bound_node_endpoint_and_uid_authority_cannot_be_replaced(self):
        args = fixture()
        with self.assertRaises(InventoryError):
            parse_runtime_inventory(args["runtime_objects"], profile=args["profile"], workload=args["workload"],
                node_container_id="f" * 64, docker_host=args["owned_identity"].docker_host, owned_identity=args["owned_identity"])
        document = json.loads(args["runtime_objects"])
        document["items"][0]["metadata"]["uid"] = document["items"][-1]["metadata"]["uid"]
        args["runtime_objects"] = encode(document)
        with self.assertRaises(InventoryError): self.parse(args)

    def test_fake_runtime_source_is_bound_to_exact_token_argv_and_environment(self):
        from tests.test_v3b2_controller import FakeRunner
        from types import SimpleNamespace
        args = fixture(); runner = FakeRunner()
        runner.bound_kubeconfig = args["owned_identity"].kubeconfig
        runner.runtime_inventory_payload = args["runtime_objects"].decode()
        argv = ("kubectl", "--kubeconfig", runner.bound_kubeconfig, "get", TOKEN,
                "--all-namespaces", "--output", "json")
        self.assertEqual(runner.run(Command(argv, 60)).stdout, runner.runtime_inventory_payload)
        for changed, env in ((argv[:4] + (TOKEN + ",secrets",) + argv[5:], ()),
                             (argv, (("KUBECONFIG", "/tmp/foreign"),))):
            result = runner.run(SimpleNamespace(argv=changed, env=env, stdin=None, mutating=False))
            self.assertNotEqual(result.stdout, runner.runtime_inventory_payload)

    def test_readiness_without_prior_image_source_cannot_reach_runtime_parser(self):
        from kil import v3b2_proofs as proofs
        args = fixture()
        inputs = {"profile": json.loads((Path(__file__).resolve().parents[1] / "deploy/kind/v3b2-profile.json").read_bytes()),
                  "workload": asdict(args["workload"]), "owned_identity": asdict(args["owned_identity"]),
                  "prior_service_bindings": [], "runtime_contract_complete": True}
        context = proofs.ExpectedContext("1" * 64, 1, "readiness", b"{}\n", proofs.canonical(inputs))
        argv = ("kubectl", "--kubeconfig", args["owned_identity"].kubeconfig, "get", TOKEN,
                "--all-namespaces", "--output", "json")
        observed = proofs.RawObservation("runtime_inventory", argv, (), 0, args["runtime_objects"], b"")
        with patch("kil.v3b2_inventory.parse_runtime_inventory", wraps=parse_runtime_inventory) as parser:
            self.assertEqual(proofs.decide(context, (observed,)).outcome, "unknown")
            parser.assert_not_called()


if __name__ == "__main__": unittest.main()
