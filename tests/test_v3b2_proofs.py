from dataclasses import FrozenInstanceError, asdict
import json
import importlib.util
import unittest

from kil import v3b2_journal


class ServiceProofIntegrationTest(unittest.TestCase):
    def setUp(self):
        from tests.test_v3b2_service_bindings import fixture, ROOT
        from kil import v3b2_proofs as proofs
        self.proofs = proofs
        self.profile, self.workload, self.desired, self.observed = fixture()
        self.base = {'run_id': 'a' * 64, 'owned_identity': {'kubeconfig': '/tmp/kubeconfig',
                     'docker_host': 'unix:///tmp/kil-v3-lab/docker.sock'}, 'kind_config_path': '/tmp/kind.json',
                     'profile': json.loads((ROOT / 'deploy/kind/v3b2-profile.json').read_bytes()),
                     'workload': asdict(self.workload), 'application_objects': self.desired,
                     'runtime_contract_complete': False}

    def observations(self, context, observed=None):
        proofs = self.proofs
        payload = proofs.canonical({'apiVersion': 'v1', 'kind': 'List',
                                   'items': self.observed if observed is None else observed})
        # Use the real registry command authority. Extra cluster captures are
        # transport records; this bounded test concerns the application proof.
        return tuple(proofs.RawObservation(request.label,
                     () if request.command is None else request.command.argv,
                     () if request.command is None else request.command.env, 0,
                     payload if request.label == 'applied_objects' else b'{}\n', b'')
                     for request in proofs.OPERATIONS[context.family].requests(context))

    def initial(self):
        from hashlib import sha256
        proofs = self.proofs
        base = proofs.canonical(self.base)
        journal = {'run_id': self.base['run_id'], 'owned_identity': self.base['owned_identity'],
                   'expected_inputs_sha256': sha256(base).hexdigest(), 'profile_start_refused_sequence': None,
                   'teardown_from_sequence': None,
                   'events': [{'sequence': 1, 'event': 'application_apply_intent', 'details': {}}]}
        context = proofs.expected_context(base, journal, lambda *_: self.fail('initial proof read'))
        return base, journal, context

    def completed(self):
        from hashlib import sha256
        proofs = self.proofs
        base, journal, context = self.initial()
        observations = self.observations(context)
        decision = proofs.decide(context, observations)
        self.assertEqual(decision.outcome, 'complete', 'allocated Service proof must complete its bounded apply check')
        bundle = proofs.observation_bundle(context, observations, decision)
        journal['events'].append(proofs.terminal_event(context, decision, sha256(bundle).hexdigest()))
        journal['events'].append({'sequence': 3, 'event': 'readiness_intent', 'details': {}})
        return base, journal, context, decision, bundle

    def test_explicit_service_context_accepts_allocations_and_returns_bindings(self):
        proofs = self.proofs
        try:
            bindings = proofs.validate_applied_objects(self.desired,
                proofs.canonical({'kind': 'List', 'items': self.observed}),
                profile=self.profile, workload=self.workload)
        except TypeError as error:
            self.fail('explicit Service allocation context is missing: ' + str(error))
        self.assertEqual(len(proofs.decode(bindings)), 9)

    def test_expected_service_subset_cannot_be_changed_replaced_or_duplicated(self):
        from copy import deepcopy
        from inspect import signature
        proofs = self.proofs
        self.assertIn('profile', signature(proofs.validate_applied_objects).parameters)
        for mutation in ('selector', 'missing', 'duplicate', 'extra'):
            expected = deepcopy(self.desired)
            if mutation == 'selector':
                expected[0]['spec']['selector'] = {'foreign': 'yes'}
            elif mutation == 'missing':
                expected.pop()
            elif mutation == 'duplicate':
                expected.append(deepcopy(expected[0]))
            else:
                expected.append(deepcopy(expected[0]))
                expected[-1]['metadata']['name'] = 'foreign'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                proofs.validate_applied_objects(expected, proofs.canonical({'kind': 'List', 'items': self.observed}),
                                                profile=self.profile, workload=self.workload)

    def test_partial_or_contextless_allocation_authority_fails_closed(self):
        from inspect import signature
        proofs = self.proofs
        self.assertIn('profile', signature(proofs.validate_applied_objects).parameters)
        payload = proofs.canonical({'kind': 'List', 'items': self.observed})
        for kwargs in ({}, {'profile': self.profile}, {'workload': self.workload},
                       {'prior_service_bindings': []}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                proofs.validate_applied_objects(self.desired, payload, **kwargs)

    def test_calico_does_not_admit_service_allocations_despite_profile_context(self):
        proofs = self.proofs
        context = proofs.ExpectedContext('a' * 64, 1, 'calico_apply', b'{}\n',
                                         proofs.canonical({**self.base, 'applied_objects': self.desired}))
        self.assertEqual(proofs.decide(context, self.observations(context)).outcome, 'unknown')

    def test_service_bindings_do_not_bypass_remaining_application_contracts(self):
        from copy import deepcopy
        from kil.v3b2_manifests import render_objects
        proofs = self.proofs
        self.base['application_objects'] = json.loads(render_objects(self.profile, self.workload))['items']
        _, _, context = self.initial()
        self.assertEqual(proofs.decide(context, self.observations(context)).outcome, 'unknown')
        services = {proofs._object_key(row): row for row in self.observed}
        observed = deepcopy(self.base['application_objects'])
        for index, row in enumerate(observed):
            row['metadata'].update(uid=f'application-uid-{index}', resourceVersion='1')
            if row['kind'] == 'Service':
                row['spec'] = deepcopy(services[proofs._object_key(row)]['spec'])
            elif row['kind'] == 'Pod':
                row['spec']['nodeName'] = 'kil-v3-lab-control-plane'
        self.assertEqual(proofs.decide(context, self.observations(context, observed)).outcome, 'unknown')

    def test_application_proof_bindings_survive_replay_and_readiness_stays_pending(self):
        proofs = self.proofs
        base, journal, context, decision, bundle = self.completed()
        replayed = proofs.expected_context(base, journal, lambda *_: bundle)
        prior = proofs.decode(replayed.inputs)['prior_service_bindings']
        self.assertEqual(prior, proofs.decode(decision.bindings)['service_bindings'])
        self.assertIsNone(proofs.decode(context.inputs)['prior_service_bindings'])
        self.assertIs(proofs.decode(replayed.inputs)['runtime_contract_complete'], False)
        requests = proofs.OPERATIONS['readiness'].requests(replayed)
        observations = tuple(proofs.RawObservation(row.label, () if row.command is None else row.command.argv,
                             () if row.command is None else row.command.env, 0, b'{}\n', b'') for row in requests)
        self.assertEqual(proofs.decide(replayed, observations).category, 'platform_inventory_contract_pending')

    def test_replayed_binding_rejects_replacement_and_allows_resource_version_progress(self):
        from copy import deepcopy
        proofs = self.proofs
        base, journal, _, decision, bundle = self.completed()
        journal['events'][-1]['event'] = 'application_apply_intent'
        context = proofs.expected_context(base, journal, lambda *_: bundle)
        progressed = deepcopy(self.observed)
        for row in progressed:
            row['metadata']['resourceVersion'] = '1000'
        next_decision = proofs.decide(context, self.observations(context, progressed))
        self.assertEqual(next_decision.bindings, decision.bindings)
        self.assertEqual(next_decision.outcome, 'complete')
        for mutation in ('uid', 'clusterIP'):
            changed = deepcopy(progressed)
            if mutation == 'uid':
                changed[0]['metadata']['uid'] = 'replacement'
            else:
                changed[0]['spec'].update(clusterIP='10.96.2.2', clusterIPs=['10.96.2.2'])
            self.assertEqual(proofs.decide(context, self.observations(context, changed)).outcome, 'unknown')

    def test_immutable_base_cannot_claim_prior_service_authority(self):
        self.base['prior_service_bindings'] = []
        with self.assertRaises(ValueError):
            self.initial()

    def test_repaired_proof_context_bindings_or_terminal_tampering_rejects_with_private_modes(self):
        from copy import deepcopy
        from hashlib import sha256
        from pathlib import Path
        from tempfile import TemporaryDirectory
        proofs = self.proofs
        base, original_journal, context, _, bundle = self.completed()
        for mutation in ('context', 'bindings', 'terminal'):
            with self.subTest(mutation=mutation), TemporaryDirectory() as directory:
                private = Path(directory)
                journal = deepcopy(original_journal)
                document = proofs.decode(bundle)
                if mutation == 'context':
                    document['expected_inputs']['prior_service_bindings'] = document['bindings']['service_bindings']
                    forged = proofs.ExpectedContext(context.run_id, context.intent_sequence, context.family,
                                                     context.intent, proofs.canonical(document['expected_inputs']))
                    document['expected_sha256'] = forged.commitment
                elif mutation == 'bindings':
                    document['bindings']['service_bindings'][0]['cluster_ip'] = '10.96.2.2'
                else:
                    journal['events'][1]['details']['service_bindings'] = document['bindings']['service_bindings']
                repaired = proofs.canonical(document)
                digest = sha256(repaired).hexdigest()
                journal['events'][1]['details']['observed_proof_sha256'] = digest
                expected_path = private / 'expected-inputs.json'
                expected_path.write_bytes(base)
                expected_path.chmod(0o600)
                proof_path = private / f'proof-1-{digest}.json'
                proof_path.write_bytes(repaired)
                proof_path.chmod(0o600)
                with self.assertRaisesRegex(proofs.ProofError, 'independently derived|does not revalidate|terminal event'):
                    v3b2_journal.load_expected_context(private / 'journal.json', journal)


class ObservedProofTest(unittest.TestCase):
    def test_calico_expectations_bind_all_pinned_manifest_documents(self):
        from kil import v3b2_proofs as proofs
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        source = (root / "deploy/kind/calico-v3.32.0.yaml").read_bytes()
        projection = (root / "deploy/kind/calico-v3.32.0.objects.json").read_bytes()
        self.assertTrue(hasattr(proofs, "calico_objects"), "pinned Calico expectation decoder is missing")
        items = proofs.calico_objects(source, projection)
        self.assertEqual(len(items), 38)
        for kind, name in (("ServiceAccount", "calico-node"), ("ServiceAccount", "calico-cni-plugin"),
                           ("ServiceAccount", "calico-kube-controllers"), ("ConfigMap", "calico-config")):
            self.assertEqual(sum(item["kind"] == kind and item["metadata"]["name"] == name for item in items), 1)
        with self.assertRaises(proofs.ProofError):
            proofs.calico_objects(source + b"\n", projection)
        with self.assertRaises(proofs.ProofError):
            proofs.calico_objects(source, projection.replace(b"calico-node", b"foreign-node", 1))

    def test_freeze_binds_each_full_source_boundary(self):
        from kil import v3b2_proofs as proofs
        from tests.test_v3b2_evidence import private_evidence
        from hashlib import sha256
        private = private_evidence(request_free=True)
        sources = [{key: value for key, value in row.items() if key != "records"} for row in private["source_attestations"]]
        manifest = proofs.canonical({"run_id": private["run_id"], "sources": sources})
        expected = {"source_images": private["runtime_identities"]["topology_attestation"]["pod_images"]}
        context = proofs.ExpectedContext(private["run_id"].removeprefix("v3b2-"), 1, "evidence_freeze",
            proofs.canonical({"evidence_sha256": sha256(manifest).hexdigest()}), proofs.canonical(expected))
        observations = [proofs.RawObservation("capture_manifest", (), (), 0, manifest, b"")]
        for source in sources:
            payload = b"".join(proofs.canonical(row) for row in source["capture"]["raw_records"])
            observations.append(proofs.RawObservation(source["track"] + ":" + source["kind"], (), (), 0, payload, b""))
        self.assertEqual(proofs.decide(context, tuple(observations)).outcome, "complete")
        self.assertNotEqual(proofs.decide(context, tuple(observations[:-1])).outcome, "complete")

    def test_foreign_comparison_reobserves_full_resources_and_context(self):
        from kil import v3b2_proofs as proofs
        from tests.test_v3b2_colima_inventory import inventory_observations, roster
        row = {"name": "foreign", "status": "Running", "arch": "aarch64", "cpus": 2, "memory": 4, "disk": 20, "runtime": "docker"}
        authority = {'home': '/tmp/home', 'private': '/tmp/private'}
        context = proofs.ExpectedContext("a" * 64, 1, "foreign_snapshot_comparison", b"{}\n",
            proofs.canonical({"foreign_before": [row], "global_context_before": "global", 'profile_paths': authority}))
        observations = (*inventory_observations([row], authority, roster(['colima-foreign'])),
                        proofs.RawObservation("global_context", ("docker", "context", "show"), (), 0, b"global\n", b""))
        decision = proofs.decide(context, observations)
        self.assertEqual(decision.outcome, "complete")
        self.assertTrue(proofs.decode(decision.bindings)["unchanged"])
        row["cpus"] = 4
        changed = (*inventory_observations([row], authority, roster(['colima-foreign'])), observations[-1])
        self.assertFalse(proofs.decode(proofs.decide(context, changed).bindings)["unchanged"])

    def test_publication_rederives_the_complete_tree(self):
        from kil import v3b2_proofs as proofs
        from kil.v3b2_evidence import prepare_publication
        from tests.test_v3b2_evidence import private_evidence
        from pathlib import Path
        prepared = prepare_publication(private_evidence(request_free=True), Path("/tmp/public"))
        intent = {"destination": str(prepared.destination), "public_commitment_sha256": prepared.public_commitment,
                  "tree_commitment_sha256": prepared.tree_commitment}
        expected = {"public_parent": "/tmp/public", "history": [{"event": name + "_complete", "details": {"observed_proof_sha256": "a" * 64}}
                    for name in ("cluster_absence_proof", "profile_absence_proof", "foreign_snapshot_comparison")], "teardown_only": False}
        context = proofs.ExpectedContext(prepared.run_id.removeprefix("v3b2-"), 1, "publication", proofs.canonical(intent), proofs.canonical(expected))
        files = dict(prepared.payloads)
        observation = proofs.RawObservation("publication_tree", (), (), 0, proofs.canonical({key: payload.hex() for key, payload in files.items()}), b"")
        self.assertEqual(proofs.decide(context, (observation,)).outcome, "complete")
        files["summary.md"] = b"changed\n"
        changed = proofs.RawObservation("publication_tree", (), (), 0, proofs.canonical({key: payload.hex() for key, payload in files.items()}), b"")
        self.assertNotEqual(proofs.decide(context, (changed,)).outcome, "complete")

    def test_quiescence_requires_explicit_refusal_and_each_gauge_once(self):
        from kil import v3b2_proofs as proofs
        from kil.v3b2_contracts import TRACK_NAMESPACES
        from kil.v3b2_journal import OwnedIdentity, kubectl_envoy_quiesce_commands
        identity = OwnedIdentity("kil-v3-lab", "unix:///Users/test/.colima/kil-v3-lab/docker.sock", "kil-v3-lab", "/tmp/kubeconfig", "cluster-uid", "a" * 64)
        from dataclasses import asdict
        bindings, observations = [], []
        gauges = ["http.kil_v3b_ingress.downstream_cx_active", "http.kil_v3b_ingress.downstream_rq_active",
                  "cluster.kil-v3b-authz.upstream_rq_active", "cluster.kil-v3b-target.upstream_rq_active"]
        for _track, namespace in TRACK_NAMESPACES:
            binding = {"namespace": namespace, "pod": "envoy-abcde", "uid": namespace + "-uid", "container_id": "containerd://" + "b" * 64,
                       "image": "docker.io/envoyproxy/envoy@sha256:" + "c" * 64}
            bindings.append(binding)
            pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"namespace": namespace, "name": binding["pod"], "uid": binding["uid"], "resourceVersion": "1"},
                   "status": {"conditions": [{"type": "Ready", "status": "True"}], "containerStatuses": [{"name": "envoy", "image": binding["image"],
                   "imageID": "docker://sha256:" + "c" * 64, "containerID": binding["container_id"], "ready": True, "state": {"running": {}}}]}}
            pod_argv = ("kubectl", "--kubeconfig", "/tmp/kubeconfig", "get", "pod", binding["pod"], "--namespace", namespace, "--output", "json")
            for phase in ("before", "after"):
                observations.append(proofs.RawObservation(namespace + ":" + phase, pod_argv, (), 0, proofs.canonical(pod), b""))
            command = kubectl_envoy_quiesce_commands(identity, namespace, binding["pod"])[1]
            observations.append(proofs.RawObservation(namespace + ":stats", command.argv, (), 0,
                proofs.canonical({"listener_refused": True, "stats": [{"name": name, "value": 0} for name in gauges]}), b""))
        context = proofs.ExpectedContext("a" * 64, 1, "envoy_quiesce", b"{}\n", proofs.canonical({"owned_identity": asdict(identity), "envoy_bindings": bindings}))
        self.assertEqual(proofs.decide(context, tuple(observations)).outcome, "complete")
        original = observations[-1]
        for value in ({"stats": [{"name": name, "value": 0} for name in gauges]},
                      {"listener_refused": True, "stats": [{"name": name, "value": 0} for name in (*gauges, gauges[0])]}):
            observations[-1] = proofs.RawObservation(original.label, original.argv, (), 0, proofs.canonical(value), b"")
            self.assertNotEqual(proofs.decide(context, tuple(observations)).outcome, "complete")

    def test_readiness_proof_validates_real_inventory_with_independent_manifests(self):
        from kil import v3b2_proofs as proofs
        from kil.v3b2_manifests import WorkloadIdentity
        from dataclasses import asdict
        from pathlib import Path
        from tests.test_v3b2_controller import raw_runtime_inventory
        from tests.test_v3b2_service_bindings import fixture
        root = Path(__file__).resolve().parents[1]
        value = json.loads(raw_runtime_inventory())
        allocations = {proofs._object_key(row): row['spec'] for row in fixture()[3]}
        prior = []
        for row in value['items']:
            if row['kind'] == 'Service':
                spec = allocations[proofs._object_key(row)]
                for field in ('clusterIP', 'clusterIPs', 'ipFamilyPolicy', 'ipFamilies'):
                    row['spec'][field] = spec[field]
                prior.append({'namespace': row['metadata']['namespace'], 'name': row['metadata']['name'],
                              'uid': row['metadata']['uid'], 'cluster_ip': row['spec']['clusterIP']})
        prior.sort(key=lambda row: (row['namespace'], row['name']))
        raw = proofs.canonical(value)
        inputs = {"owned_identity": {"node_container_id": "a" * 64, "cluster_incarnation_uid": "11111111-1111-4111-8111-111111111111",
                  "docker_host": "unix:///Users/test/.colima/kil-v3-lab/docker.sock", "kubeconfig": "/tmp/kubeconfig"},
                  "profile": json.loads((root / "deploy/kind/v3b2-profile.json").read_bytes()),
                  "workload": asdict(WorkloadIdentity("v3b2-" + "1" * 64,
                    "sha256:45a167d79b92f352af05a3e9cb8a9df8e972e38ab23d04ca692053e2eaf63649",
                    "docker.io/envoyproxy/envoy@sha256:57e14a549d7bd43c8d3f6d03e8cfa653e037d4b38e133acd9b54f38c524401b4")),
                  'prior_service_bindings': prior}
        context = proofs.ExpectedContext("a" * 64, 1, "readiness", b"{}\n", proofs.canonical(inputs))
        argv = ("kubectl", "--kubeconfig", "/tmp/kubeconfig", "get",
                "namespaces,pods,services,endpoints,endpointslices,serviceaccounts,configmaps,deployments,daemonsets,networkpolicies", "--all-namespaces", "--output", "json")
        observation = proofs.RawObservation("runtime_inventory", argv, (), 0, raw, b"")
        self.assertEqual(proofs.decide(context, (observation,)).outcome, "complete")
        missing_prior = {key: value for key, value in inputs.items() if key != 'prior_service_bindings'}
        unallocated = proofs.RawObservation('runtime_inventory', argv, (), 0, raw_runtime_inventory().encode(), b'')
        context_without_prior = proofs.ExpectedContext('a' * 64, 1, 'readiness', b'{}\n', proofs.canonical(missing_prior))
        self.assertEqual(proofs.decide(context_without_prior, (unallocated,)).outcome, 'unknown')
        self.assertEqual(proofs.decide(context_without_prior, (observation,)).outcome, 'unknown')
        value = json.loads(raw)
        next(item for item in value["items"] if item["kind"] == "ConfigMap")["data"] = {"foreign": "configuration"}
        poison = proofs.RawObservation("runtime_inventory", argv, (), 0, proofs.canonical(value), b"")
        self.assertNotEqual(proofs.decide(context, (poison,)).outcome, "complete")

    def test_image_import_binds_archive_bytes_and_realized_config_ids(self):
        from kil import v3b2_proofs as proofs
        from hashlib import sha256
        archive = b"reviewed archive bytes"
        expected = {"owned_identity": {"docker_host": "unix:///Users/test/.colima/kil-v3-lab/docker.sock"},
                    "archive_sha256": sha256(archive).hexdigest(),
                    "images": [{"reference": "kil.local/kil-v3b2:sha256-" + "c" * 64, "manifest_digest": "sha256:" + "c" * 64, "config_digest": "sha256:" + "d" * 64},
                               {"reference": "docker.io/envoyproxy/envoy@sha256:" + "e" * 64, "manifest_digest": "sha256:" + "e" * 64, "config_digest": "sha256:" + "f" * 64}]}
        context = proofs.ExpectedContext("a" * 64, 1, "image_import", b"{}\n", proofs.canonical(expected))
        env = (("DOCKER_CONFIG", "/tmp/config"), ("DOCKER_HOST", expected["owned_identity"]["docker_host"]))
        observations = [proofs.RawObservation("image_archive", (), (), 0, archive, b"")]
        for index, image in enumerate(expected["images"]):
            observations.append(proofs.RawObservation("image_" + str(index), ("docker", "image", "inspect", image["reference"]), env, 0,
                                proofs.canonical([{"Id": image["config_digest"], "RepoTags": [image["reference"]], "RepoDigests": []}]), b""))
        self.assertEqual(proofs.decide(context, tuple(observations)).outcome, "complete")
        observations[0] = proofs.RawObservation("image_archive", (), (), 0, b"changed", b"")
        self.assertNotEqual(proofs.decide(context, tuple(observations)).outcome, "complete")

    def test_cluster_incarnation_requires_fixed_node_labels_config_and_namespace(self):
        from kil import v3b2_proofs as proofs
        config = b"kind: Cluster\n"
        from hashlib import sha256
        identity = {"docker_host": "unix:///Users/test/.colima/kil-v3-lab/docker.sock", "kubeconfig": "/tmp/kubeconfig"}
        expected = {"owned_identity": identity, "kind_node_image": "kindest/node@sha256:" + "c" * 64,
                    "kind_config_sha256": sha256(config).hexdigest()}
        context = proofs.ExpectedContext("a" * 64, 1, "cluster_create", proofs.canonical({"kind_cluster": "kil-v3-lab", "kubeconfig": identity["kubeconfig"]}), proofs.canonical(expected))
        node = {"Id": "b" * 64, "Name": "/kil-v3-lab-control-plane", "Image": "sha256:" + "d" * 64,
                "Config": {"Image": expected["kind_node_image"], "Labels": {"io.x-k8s.kind.cluster": "kil-v3-lab", "io.x-k8s.kind.role": "control-plane"}}}
        env = (("DOCKER_CONFIG", "/tmp/config"), ("DOCKER_HOST", identity["docker_host"]))
        def observations():
            return (proofs.RawObservation("node", ("docker", "inspect", "kil-v3-lab-control-plane"), env, 0, proofs.canonical([node]), b""),
                    proofs.RawObservation("cluster_namespace", ("kubectl", "--kubeconfig", identity["kubeconfig"], "get", "namespace", "kube-system", "--output", "json"), (), 0,
                        proofs.canonical({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "kube-system", "uid": "11111111-1111-4111-8111-111111111111"}}), b""),
                    proofs.RawObservation("kind_configuration", (), (), 0, config, b""))
        self.assertEqual(proofs.decide(context, observations()).outcome, "complete")
        node["Config"]["Labels"]["io.x-k8s.kind.cluster"] = "foreign"
        self.assertEqual(proofs.decide(context, observations()).outcome, "unknown")

    def test_kind_image_store_checks_manifest_content_and_completeness(self):
        from kil import v3b2_proofs as proofs
        expected = {"owned_identity": {"docker_host": "unix:///Users/test/.colima/kil-v3-lab/docker.sock", "node_container_id": "b" * 64},
                    "images": [{"reference": "kil.local/kil-v3b2:sha256-" + "c" * 64, "manifest_digest": "sha256:" + "c" * 64,
                                "config_digest": "sha256:" + "d" * 64},
                               {"reference": "docker.io/envoyproxy/envoy@sha256:" + "e" * 64, "manifest_digest": "sha256:" + "e" * 64,
                                "config_digest": "sha256:" + "f" * 64}]}
        context = proofs.ExpectedContext("a" * 64, 1, "image_load", b"{}\n", proofs.canonical(expected))
        argv = ("docker", "exec", "b" * 64, "/usr/local/bin/ctr", "--address", "/run/containerd/containerd.sock",
                "--namespace", "k8s.io", "images", "check", "--snapshotter", "overlayfs")
        env = (("DOCKER_CONFIG", "/tmp/config"), ("DOCKER_HOST", expected["owned_identity"]["docker_host"]))
        rows = "REF TYPE DIGEST STATUS SIZE UNPACKED\n" + "".join(
            f"{image['reference']} application/vnd.oci.image.manifest.v1+json {image['manifest_digest']} complete (4/4) 12.0 MiB true\n"
            for image in expected["images"])
        observation = proofs.RawObservation("node_images", argv, env, 0, rows.encode(), b"")
        self.assertEqual(proofs.decide(context, (observation,)).outcome, "complete")
        for poison in (rows.replace("complete (4/4)", "incomplete (3/4)"), rows.replace("sha256:" + "c" * 64 + " complete", "sha256:" + "9" * 64 + " complete"), "{}\n"):
            self.assertNotEqual(proofs.decide(context, (proofs.RawObservation("node_images", argv, env, 0, poison.encode(), b""),)).outcome, "complete")

    def test_applied_configuration_is_checked_against_independent_documents(self):
        from kil import v3b2_proofs as proofs
        desired = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"namespace": "kube-system", "name": "calico-config"}, "data": {"backend": "bird"}}
        observed = json.loads(json.dumps(desired))
        observed["metadata"].update(uid="observed-uid", resourceVersion="1", creationTimestamp="2026-09-07T00:00:00Z")
        for family in ("calico_apply", "application_apply"):
            expected = {"applied_objects": [desired], "owned_identity": {"kubeconfig": "/tmp/kubeconfig"}}
            context = proofs.ExpectedContext("a" * 64, 1, family, b"{}\n", proofs.canonical(expected))
            argv = ("kubectl", "--kubeconfig", "/tmp/kubeconfig", "get", "--filename", "-", "--output", "json")
            observation = proofs.RawObservation("applied_objects", argv, (), 0, proofs.canonical({"apiVersion": "v1", "kind": "List", "items": [observed]}), b"")
            self.assertEqual(proofs.decide(context, (observation,)).outcome, "complete")
            observed["data"]["backend"] = "foreign"
            poison = proofs.RawObservation("applied_objects", argv, (), 0, proofs.canonical({"apiVersion": "v1", "kind": "List", "items": [observed]}), b"")
            self.assertNotEqual(proofs.decide(context, (poison,)).outcome, "complete")
            observed["data"]["backend"] = "bird"

    def test_driver_proofs_use_same_bound_incarnation_and_real_readiness(self):
        from kil import v3b2_proofs as proofs
        from kil.v3b1_request_driver import readiness_record
        namespace = "kil-v3-baseline"
        image = "kil.local/kil-v3b2:sha256-" + "c" * 64
        binding = {"namespace": namespace, "pod": "driver", "uid": "pod-uid", "container_id": "containerd://" + "d" * 64, "image": image}
        pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "driver", "namespace": namespace,
               "uid": "pod-uid", "resourceVersion": "3"}, "status": {"conditions": [{"type": "Ready", "status": "True"}],
               "containerStatuses": [{"name": "driver", "image": image, "imageID": "docker://sha256:" + "c" * 64,
                                      "containerID": binding["container_id"], "ready": True, "state": {"running": {}}}]}}
        identity = {"kubeconfig": "/tmp/kubeconfig", "node_container_id": "e" * 64, "cluster_incarnation_uid": "cluster-uid"}
        argv = ("kubectl", "--kubeconfig", "/tmp/kubeconfig", "get", "pod", "driver", "--namespace", namespace, "--output", "json")
        before = proofs.RawObservation("driver_pod_before", argv, (), 0, proofs.canonical(pod), b"")
        logs_argv = ("kubectl", "--kubeconfig", "/tmp/kubeconfig", "logs", "pod/driver", "--namespace", namespace, "--limit-bytes=1048576")
        logs = proofs.RawObservation("driver_logs", logs_argv, (), 0, proofs.canonical(readiness_record("credential_policy_baseline", 1, 2)), b"")
        intent = {key: binding[key] for key in ("namespace", "pod", "uid")}
        for family in ("driver_start", "driver_cancel"):
            context = proofs.ExpectedContext("a" * 64, 1, family, proofs.canonical(intent),
                proofs.canonical({"owned_identity": identity, "driver_binding": binding}))
            if family == "driver_cancel":
                pod["status"]["containerStatuses"][0]["state"] = {"terminated": {"exitCode": 0}}
            after = proofs.RawObservation("driver_pod_after", argv, (), 0, proofs.canonical(pod), b"")
            self.assertEqual(proofs.decide(context, (before, logs, after)).outcome, "complete")
            bad = json.loads(proofs.canonical(pod))
            bad["status"]["containerStatuses"][0]["containerID"] = "containerd://" + "f" * 64
            changed = proofs.RawObservation("driver_pod_after", argv, (), 0, proofs.canonical(bad), b"")
            self.assertEqual(proofs.decide(context, (before, logs, changed)).outcome, "unknown")
        pod["status"]["containerStatuses"][0]["state"] = {"terminated": {"exitCode": 7}}
        after = proofs.RawObservation("driver_pod_after", argv, (), 0, proofs.canonical(pod), b"")
        self.assertEqual(proofs.decide(context, (before, after)).outcome, "teardown_only")

    def test_profile_operations_use_observed_closed_inventory(self):
        from kil import v3b2_proofs as proofs
        from kil.v3b2_profile_state import ProfilePaths, capture, creation_binding
        from tests.test_v3b2_profile_state import create_profile
        from tests.test_v3b2_colima_inventory import inventory_observations
        from kil.v3b2_colima_inventory import capture_roster
        from pathlib import Path
        import tempfile
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        paths = ProfilePaths(root / 'home', root / 'private')
        create_profile(paths)
        state = capture(paths)
        binding = creation_binding(paths.document(), state)
        config = {"name": "kil-v3-lab", "status": "Running", "arch": "aarch64", "cpus": 2,
                  "memory": 2147483648, "disk": 107374182400, "runtime": "docker"}
        for family, rows in (("profile_start", [config]), ("profile_stop", [{**config, "status": "Stopped"}]),
                             ("profile_delete", []), ("profile_absence_proof", [])):
            with self.subTest(family=family):
                expected = {"profile_configuration": {key: value for key, value in config.items() if key != "status"},
                            "active_paths": ["/tmp/kubeconfig"], 'profile_paths': paths.document(), 'profile_binding': binding}
                context = proofs.ExpectedContext("a" * 64, 1, family, b"{}\n", proofs.canonical(expected))
                observations = inventory_observations(rows, paths.document(), capture_roster(paths) if rows else None)
                absent = proofs.RawObservation("active_paths", (), (), 0, proofs.canonical({"/tmp/kubeconfig": None}), b"")
                observed_state = state if rows else {key: None for key in state}
                filesystem = proofs.RawObservation('profile_state', (), (), 0, proofs.canonical(observed_state), b'')
                self.assertEqual(proofs.decide(context, (*observations, filesystem, absent)).outcome, "complete")
                self.assertNotEqual(proofs.decide(context, (proofs.RawObservation("profile_inventory", proofs.PROFILE_INVENTORY_ARGV, (), 1, b"", b"absent"), absent)).outcome, "complete")

    def test_every_closed_family_rejects_unrelated_success(self):
        self.assertIsNotNone(importlib.util.find_spec("kil.v3b2_proofs"), "shared proof boundary is missing")
        from kil import v3b2_proofs as proofs
        families = frozenset(v3b2_journal._PAIR_DETAILS)
        self.assertEqual(frozenset(proofs.OPERATIONS), families)
        for family in families:
            with self.subTest(family=family):
                context = proofs.ExpectedContext("a" * 64, 1, family, b"{}\n", b"{}\n")
                for payload in (b"{}\n", b"[]\n", b"", b"not json", b'{"ready":true}\n'):
                    observation = proofs.RawObservation("unrelated", (), (), 0, payload, b"")
                    self.assertNotEqual(proofs.decide(context, (observation,)).outcome, "complete")
                with self.assertRaises(FrozenInstanceError):
                    context.family = "request"

    def test_absence_requires_successful_closed_inventory(self):
        self.assertIsNotNone(importlib.util.find_spec("kil.v3b2_proofs"), "shared proof boundary is missing")
        from kil import v3b2_proofs as proofs
        expected = {"owned_identity": {"node_container_id": "b" * 64,
                    "docker_host": "unix:///Users/test/.colima/kil-v3-lab/docker.sock"}}
        context = proofs.ExpectedContext("a" * 64, 1, "cluster_absence_proof", b"{}\n",
                                         (json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n").encode())
        env = (("DOCKER_CONFIG", "/tmp/config"), ("DOCKER_HOST", expected["owned_identity"]["docker_host"]))
        argv = ("docker", "container", "ls", "--all", "--no-trunc", "--format", "{{json .}}")
        for stderr in (b"permission denied", b"daemon unavailable", b"timeout", b"no such object"):
            observation = proofs.RawObservation("cluster_inventory", argv, env, 1, b"", stderr)
            self.assertEqual(proofs.decide(context, (observation,)).outcome, "unknown")
        absent = proofs.RawObservation("cluster_inventory", argv, env, 0, b"", b"")
        self.assertEqual(proofs.decide(context, (absent,)).outcome, "complete")


if __name__ == "__main__":
    unittest.main()
