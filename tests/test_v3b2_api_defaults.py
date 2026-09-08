"""Independent API response examples for the pinned Kubernetes defaults."""
from copy import deepcopy
import unittest

from kil import v3b2_proofs as proofs


def object_for(kind="Pod", api="v1"):
    return {"apiVersion": api, "kind": kind,
            "metadata": {"name": "sample", "namespace": "kil-v3-baseline"},
            "spec": {}}


def response(desired):
    result = deepcopy(desired)
    result["metadata"].update(uid="11111111-1111-4111-8111-111111111111",
                              resourceVersion="42", creationTimestamp="2026-09-07T00:00:00Z")
    return result


def pod_spec():
    return {"serviceAccountName": "driver", "restartPolicy": "Never",
            "automountServiceAccountToken": False, "enableServiceLinks": False,
            "containers": [{"name": "driver", "image": "kil:reviewed", "imagePullPolicy": "Never",
                            "tty": False, "securityContext": {"allowPrivilegeEscalation": False},
                            "ports": [{"containerPort": 8080}],
                            "volumeMounts": [{"name": "config", "mountPath": "/config", "readOnly": False}],
                            "env": [{"name": "NODE", "valueFrom": {"fieldRef": {"fieldPath": "spec.nodeName"}}}],
                            "readinessProbe": {"exec": {"command": ["true"]}}}],
            "initContainers": [{"name": "init", "image": "calico:reviewed", "imagePullPolicy": "IfNotPresent"}],
            "volumes": [{"name": "config", "configMap": {"name": "config"}},
                        {"name": "host", "hostPath": {"path": "/var/lib/calico"}}]}


def api_pod_defaults(spec):
    # Deliberately assembled independently of the production normalizer.
    spec.update(dnsPolicy="ClusterFirst", schedulerName="default-scheduler",
                terminationGracePeriodSeconds=30, securityContext={}, serviceAccount="driver")
    for container in spec["containers"] + spec["initContainers"]:
        container.update(terminationMessagePath="/dev/termination-log", terminationMessagePolicy="File", resources={})
    container = spec["containers"][0]
    container.pop("tty")
    container["ports"][0]["protocol"] = "TCP"
    container["volumeMounts"][0].pop("readOnly")
    container["env"][0]["valueFrom"]["fieldRef"]["apiVersion"] = "v1"
    container["readinessProbe"].update(timeoutSeconds=1, periodSeconds=10, successThreshold=1, failureThreshold=3)
    spec["volumes"][0]["configMap"]["defaultMode"] = 420
    spec["volumes"][1]["hostPath"]["type"] = ""


class APIDefaultTest(unittest.TestCase):
    def assert_matches(self, desired, observed):
        self.assertTrue(proofs._matches_applied(desired, observed))
        proofs.validate_applied_objects([desired], proofs.canonical(observed))

    def test_direct_pod_and_workload_template_defaults_and_serialization(self):
        for kind, api in (("Pod", "v1"), ("Deployment", "apps/v1"), ("DaemonSet", "apps/v1")):
            with self.subTest(kind=kind):
                desired = object_for(kind, api)
                if kind == "Pod":
                    desired["spec"] = pod_spec()
                    select = lambda obj: obj["spec"]
                else:
                    desired["spec"] = {"template": {"metadata": {"labels": {"app": "sample"}}, "spec": pod_spec()}}
                    select = lambda obj: obj["spec"]["template"]["spec"]
                observed = response(desired)
                api_pod_defaults(select(observed))
                if kind != "Pod":
                    observed["spec"]["template"]["metadata"]["creationTimestamp"] = None
                self.assert_matches(desired, observed)
                for key, value in (("restartPolicy", "Always"), ("automountServiceAccountToken", True),
                                   ("terminationGracePeriodSeconds", 0), ("dnsPolicy", "Default"),
                                   ("serviceAccount", "foreign"), ("securityContext", {"runAsUser": 0})):
                    poisoned = deepcopy(observed)
                    select(poisoned)[key] = value
                    self.assertFalse(proofs._matches_applied(desired, poisoned), key)

    def test_every_container_default_rejects_a_changed_value(self):
        desired = object_for()
        desired["spec"] = pod_spec()
        observed = response(desired)
        api_pod_defaults(observed["spec"])
        paths = ((('terminationMessagePath',), '/foreign'), (('terminationMessagePolicy',), 'FallbackToLogsOnError'),
                 (('resources',), {'requests': {'cpu': '1'}}), (('ports', 0, 'protocol'), 'UDP'),
                 (('env', 0, 'valueFrom', 'fieldRef', 'apiVersion'), 'v2'),
                 (('readinessProbe', 'timeoutSeconds'), 2), (('readinessProbe', 'periodSeconds'), 11),
                 (('readinessProbe', 'successThreshold'), 2), (('readinessProbe', 'failureThreshold'), 4),
                 (('imagePullPolicy',), 'IfNotPresent'), (('tty',), True),
                 (('volumeMounts', 0, 'readOnly'), True))
        for path, value in paths:
            with self.subTest(path=path):
                poisoned = deepcopy(observed)
                cursor = poisoned['spec']['containers'][0]
                for part in path[:-1]:
                    cursor = cursor[part]
                cursor[path[-1]] = value
                self.assertFalse(proofs._matches_applied(desired, poisoned))

    def test_pod_defaults_do_not_apply_to_arbitrary_spec_or_wrong_api_version(self):
        for kind, api in (("ConfigMap", "v1"), ("Service", "v1"), ("Pod", "example/v1"), ("Deployment", "apps/v2")):
            desired = object_for(kind, api)
            observed = response(desired)
            observed["spec"]["dnsPolicy"] = "ClusterFirst"
            self.assertFalse(proofs._matches_applied(desired, observed), (kind, api))
        desired = object_for()
        desired['spec'] = pod_spec()
        for location in (('securityContext',), ('containers', 0, 'securityContext')):
            observed = response(desired)
            cursor = observed['spec']
            for part in location[:-1]:
                cursor = cursor[part]
            cursor.setdefault(location[-1], {})['dnsPolicy'] = 'ClusterFirst'
            self.assertFalse(proofs._matches_applied(desired, observed))

    def test_deployment_and_daemonset_exact_strategy_defaults(self):
        for kind, strategy, additions in (
                ('Deployment', {'strategy': {'type': 'Recreate'}}, {'revisionHistoryLimit': 10, 'progressDeadlineSeconds': 600}),
                ('DaemonSet', {'updateStrategy': {'type': 'RollingUpdate', 'rollingUpdate': {'maxUnavailable': 1}}}, {'revisionHistoryLimit': 10})):
            desired = object_for(kind, 'apps/v1')
            desired['spec'] = strategy
            observed = response(desired)
            observed['spec'].update(additions)
            if kind == 'DaemonSet':
                observed['spec']['updateStrategy']['rollingUpdate']['maxSurge'] = 0
            else:
                observed['metadata']['annotations'] = {'deployment.kubernetes.io/revision': '1'}
            self.assert_matches(desired, observed)
            for key, value in additions.items():
                poison = deepcopy(observed)
                poison['spec'][key] = value + 1
                self.assertFalse(proofs._matches_applied(desired, poison))
            if kind == 'Deployment':
                observed['spec']['strategy']['rollingUpdate'] = {'maxSurge': '25%', 'maxUnavailable': '25%'}
            else:
                observed['spec']['updateStrategy']['rollingUpdate']['maxSurge'] = 1
            self.assertFalse(proofs._matches_applied(desired, observed))

    def test_namespace_defaults_are_exact_and_cluster_scope_has_no_namespace(self):
        desired = object_for('Namespace')
        desired.pop('spec')
        desired['metadata'].pop('namespace')
        observed = response(desired)
        observed['metadata']['labels'] = {'kubernetes.io/metadata.name': 'sample'}
        observed['spec'] = {'finalizers': ['kubernetes']}
        observed['status'] = {'phase': 'Active'}
        self.assert_matches(desired, observed)
        for mutate in (lambda obj: obj['metadata']['labels'].update({'kubernetes.io/metadata.name': 'foreign'}),
                       lambda obj: obj['spec'].update(finalizers=['foreign']),
                       lambda obj: obj['metadata'].update(namespace='default')):
            poison = deepcopy(observed)
            mutate(poison)
            self.assertFalse(proofs._matches_applied(desired, poison))

    def test_crd_serialization_conversion_and_top_level_status(self):
        desired = object_for('CustomResourceDefinition', 'apiextensions.k8s.io/v1')
        desired['metadata'].pop('namespace')
        desired['spec'] = {'preserveUnknownFields': False, 'versions': [{'name': 'v1', 'schema': {'openAPIV3Schema': {
            'type': 'object', 'properties': {'spec': {'type': 'object', 'properties': {'dnsPolicy': {'type': 'string'}}}}}}}]}
        desired['status'] = {'acceptedNames': {'kind': '', 'plural': ''}, 'conditions': [], 'storedVersions': []}
        observed = response(desired)
        observed['spec'].pop('preserveUnknownFields')
        observed['spec']['conversion'] = {'strategy': 'None'}
        observed['status'] = {'acceptedNames': {'kind': 'Sample', 'plural': 'samples'}, 'storedVersions': ['v1']}
        self.assert_matches(desired, observed)
        for mutate in (lambda obj: obj['spec'].update(preserveUnknownFields=True),
                       lambda obj: obj['spec']['conversion'].update(webhook={}),
                       lambda obj: obj['spec']['versions'][0]['schema']['openAPIV3Schema']['properties']['spec']['properties'].update(restartPolicy='Always'),
                       lambda obj: obj['metadata'].update(finalizers=['customresourcecleanup.apiextensions.k8s.io'])):
            poison = deepcopy(observed)
            mutate(poison)
            self.assertFalse(proofs._matches_applied(desired, poison))

    def test_static_service_defaults_and_dynamic_allocation_fail_closed(self):
        desired = object_for('Service')
        desired['spec'] = {'type': 'ClusterIP', 'ports': [{'port': 8080, 'targetPort': 8080, 'protocol': 'TCP'}]}
        observed = response(desired)
        observed['spec'].update(sessionAffinity='None', internalTrafficPolicy='Cluster')
        self.assert_matches(desired, observed)
        for key, value in (('sessionAffinity', 'ClientIP'), ('internalTrafficPolicy', 'Local'), ('ipFamilyPolicy', 'PreferDualStack'),
                           ('ipFamilies', ['IPv6']), ('clusterIP', '10.96.0.10'), ('clusterIP', 'None'),
                           ('externalIPs', ['1.2.3.4']), ('type', 'NodePort'), ('type', 'LoadBalancer')):
            poison = deepcopy(observed)
            poison['spec'][key] = value
            self.assertFalse(proofs._matches_applied(desired, poison), key)

    def test_service_family_additions_require_independent_allocation_authority(self):
        desired = object_for('Service')
        desired['spec'] = {'type': 'ClusterIP', 'ports': [{'port': 8080, 'targetPort': 8080, 'protocol': 'TCP'}]}
        additions = ({'ipFamilyPolicy': 'SingleStack'}, {'ipFamilies': ['IPv4']},
                     {'ipFamilyPolicy': 'SingleStack', 'ipFamilies': ['IPv4']})
        for fields in additions:
            with self.subTest(fields=fields):
                observed = response(desired)
                observed['spec'].update(fields)
                with self.subTest(boundary='comparator'):
                    self.assertFalse(proofs._matches_applied(desired, observed))
                with self.subTest(boundary='applied-proof'):
                    with self.assertRaises(proofs.ProofError):
                        proofs.validate_applied_objects([desired], proofs.canonical(observed))

    def test_explicit_service_family_configuration_compares_exactly(self):
        for fields in ({'ipFamilyPolicy': 'SingleStack'}, {'ipFamilies': ['IPv4']},
                       {'ipFamilyPolicy': 'SingleStack', 'ipFamilies': ['IPv4']}):
            desired = object_for('Service')
            desired['spec'] = {'type': 'ClusterIP', **fields}
            self.assert_matches(desired, response(desired))
            for key in fields:
                for change in ('omit', 'change'):
                    with self.subTest(fields=fields, key=key, change=change):
                        observed = response(desired)
                        if change == 'omit':
                            observed['spec'].pop(key)
                        else:
                            observed['spec'][key] = 'PreferDualStack' if key == 'ipFamilyPolicy' else ['IPv6']
                        with self.subTest(boundary='comparator'):
                            self.assertFalse(proofs._matches_applied(desired, observed))
                        with self.subTest(boundary='applied-proof'):
                            with self.assertRaises(proofs.ProofError):
                                proofs.validate_applied_objects([desired], proofs.canonical(observed))

    def test_dynamic_pod_fields_and_generated_admission_fail_closed(self):
        for kind, api in (('Pod', 'v1'), ('Deployment', 'apps/v1'), ('DaemonSet', 'apps/v1')):
            desired = object_for(kind, api)
            desired['spec'] = pod_spec() if kind == 'Pod' else {'template': {'metadata': {}, 'spec': pod_spec()}}
            for key, value in (('priority', 0), ('preemptionPolicy', 'PreemptLowerPriority'), ('nodeName', 'kil-v3-lab-control-plane'),
                               ('tolerations', [{'key': 'node.kubernetes.io/not-ready', 'operator': 'Exists', 'effect': 'NoExecute', 'tolerationSeconds': 300}]),
                               ('imagePullSecrets', [{'name': 'foreign'}])):
                observed = response(desired)
                spec = observed['spec'] if kind == 'Pod' else observed['spec']['template']['spec']
                spec[key] = value
                self.assertFalse(proofs._matches_applied(desired, observed), (kind, key))
        observed = response(desired)
        observed['metadata']['annotations'] = {'cni.projectcalico.org/podIP': '10.244.0.1/32'}
        self.assertFalse(proofs._matches_applied(desired, observed))

    def test_root_metadata_is_validated_and_template_metadata_is_not_identity(self):
        desired = object_for('Deployment', 'apps/v1')
        desired['spec'] = {'template': {'metadata': {}, 'spec': {}}}
        observed = response(desired)
        observed['metadata'].update(generation=1, managedFields=[{'manager': 'kubectl-client-side-apply', 'operation': 'Update',
            'apiVersion': 'apps/v1', 'time': '2026-09-07T00:00:00Z', 'fieldsType': 'FieldsV1', 'fieldsV1': {'f:spec': {}}}])
        observed['metadata']['annotations'] = {'kubectl.kubernetes.io/last-applied-configuration': '{"untrusted":"ignored"}',
                                              'deployment.kubernetes.io/revision': '1'}
        self.assert_matches(desired, observed)
        for key, value in (('uid', ''), ('uid', []), ('resourceVersion', '0'), ('resourceVersion', 'abc'), ('generation', True),
                           ('creationTimestamp', 'not-a-date'), ('creationTimestamp', None), ('managedFields', {'anything': True}),
                           ('deletionTimestamp', None), ('deletionTimestamp', '2026-09-07T00:00:00Z')):
            poison = deepcopy(observed)
            poison['metadata'][key] = value
            self.assertFalse(proofs._matches_applied(desired, poison), key)
        for key, value in (('uid', 'foreign'), ('resourceVersion', '1'), ('generation', 1), ('managedFields', []),
                           ('creationTimestamp', '2026-09-07T00:00:00Z'),
                           ('annotations', {'kubectl.kubernetes.io/last-applied-configuration': '{}'})):
            poison = deepcopy(observed)
            poison['spec']['template']['metadata'][key] = value
            self.assertFalse(proofs._matches_applied(desired, poison), key)
        for revision in ('0', '2', '01', '-1', '9' * 100, 1):
            poison = deepcopy(observed)
            poison['metadata']['annotations']['deployment.kubernetes.io/revision'] = revision
            self.assertFalse(proofs._matches_applied(desired, poison))

    def test_false_zero_empty_and_null_are_not_globally_equivalent(self):
        desired = object_for()
        desired['spec'] = pod_spec()
        for path in (('automountServiceAccountToken',), ('enableServiceLinks',), ('containers', 0, 'securityContext', 'allowPrivilegeEscalation')):
            observed = response(desired)
            cursor = observed['spec']
            for key in path[:-1]:
                cursor = cursor[key]
            cursor.pop(path[-1])
            self.assertFalse(proofs._matches_applied(desired, observed), path)
        observed = response(desired)
        observed['spec']['containers'][0]['readinessProbe']['exec']['command'] = ['false']
        self.assertFalse(proofs._matches_applied(desired, observed))

    def test_pdb_has_no_unhealthy_eviction_default(self):
        desired = object_for('PodDisruptionBudget', 'policy/v1')
        observed = response(desired)
        observed['spec']['unhealthyPodEvictionPolicy'] = 'IfHealthyBudget'
        self.assertFalse(proofs._matches_applied(desired, observed))

    def test_omitted_namespaced_namespace_is_default_in_applied_identity(self):
        desired = object_for('ConfigMap')
        desired.pop('spec')
        desired['metadata'].pop('namespace')
        observed = response(desired)
        observed['metadata']['namespace'] = 'default'
        self.assert_matches(desired, observed)

    def test_service_links_default_is_direct_pod_only(self):
        for kind, api in (('Pod', 'v1'), ('Deployment', 'apps/v1'), ('DaemonSet', 'apps/v1')):
            desired = object_for(kind, api)
            if kind != 'Pod':
                desired['spec'] = {'template': {'metadata': {}, 'spec': {}}}
            observed = response(desired)
            spec = observed['spec'] if kind == 'Pod' else observed['spec']['template']['spec']
            spec['enableServiceLinks'] = True
            self.assertEqual(proofs._matches_applied(desired, observed), kind == 'Pod')

    def test_explicit_calico_grace_zero_and_configmap_mode_are_preserved(self):
        desired = object_for('DaemonSet', 'apps/v1')
        spec = pod_spec()
        spec.update(terminationGracePeriodSeconds=0)
        spec['volumes'][0]['configMap']['defaultMode'] = 292
        desired['spec'] = {'template': {'metadata': {}, 'spec': spec}}
        observed = response(desired)
        self.assert_matches(desired, observed)
        for mutate in (lambda obj: obj['spec']['template']['spec'].update(terminationGracePeriodSeconds=30),
                       lambda obj: obj['spec']['template']['spec']['volumes'][0]['configMap'].update(defaultMode=420),
                       lambda obj: obj['spec']['template']['spec']['volumes'][1]['hostPath'].update(type='Directory')):
            poison = deepcopy(observed)
            mutate(poison)
            self.assertFalse(proofs._matches_applied(desired, poison))

    def test_last_applied_annotation_cannot_prove_configuration(self):
        desired = object_for('ConfigMap')
        desired['data'] = {'key': 'reviewed'}
        observed = response(desired)
        observed['metadata']['annotations'] = {'kubectl.kubernetes.io/last-applied-configuration': proofs.canonical(desired).decode()}
        observed['data']['key'] = 'changed'
        with self.assertRaises(proofs.ProofError):
            proofs.validate_applied_objects([desired], proofs.canonical(observed))

    def test_managed_fields_are_bounded_structural_metadata(self):
        desired = object_for('ConfigMap')
        good = {'manager': 'kubectl', 'operation': 'Update', 'apiVersion': 'v1', 'fieldsType': 'FieldsV1', 'fieldsV1': {'f:data': {}}}
        observed = response(desired)
        observed['metadata']['managedFields'] = [good]
        self.assert_matches(desired, observed)
        for value in ([good] * 65, [{**good, 'fieldsV1': {'f:data': 1}}], [{**good, 'fieldsV1': {'bad': {}}}],
                      [{**good, 'operation': 'Delete'}], [{**good, 'time': '2026-02-30T00:00:00Z'}],
                      [{**good, 'manager': 'x' * 129}], [{**good, 'fieldsType': 'FieldsV2'}], [{**good, 'extra': True}]):
            poison = deepcopy(observed)
            poison['metadata']['managedFields'] = value
            self.assertFalse(proofs._matches_applied(desired, poison))

    def test_unknown_fields_are_rejected_at_all_crd_schema_paths(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        desired_objects = proofs.calico_objects((root / 'deploy/kind/calico-v3.32.0.yaml').read_bytes(),
                                                (root / 'deploy/kind/calico-v3.32.0.objects.json').read_bytes())
        for desired in desired_objects:
            if desired['kind'] != 'CustomResourceDefinition':
                continue
            observed = response(desired)
            observed['spec'].pop('preserveUnknownFields', None)
            observed['spec']['conversion'] = {'strategy': 'None'}
            observed['status'] = {'acceptedNames': deepcopy(desired['spec']['names']), 'storedVersions': ['v1']}
            self.assert_matches(desired, observed)
            for key, value in (('dnsPolicy', 'ClusterFirst'), ('restartPolicy', 'Always'), ('metadata', {'uid': 'foreign'}),
                               ('containers', [{'imagePullPolicy': 'IfNotPresent'}]), ('default', False)):
                poison = deepcopy(observed)
                poison['spec']['versions'][0]['schema']['openAPIV3Schema']['properties']['spec'][key] = value
                self.assertFalse(proofs._matches_applied(desired, poison), (desired['metadata']['name'], key))

    def test_defaults_have_exact_scalar_types_and_do_not_mutate_inputs(self):
        desired = object_for()
        desired['spec'] = pod_spec()
        observed = response(desired)
        api_pod_defaults(observed['spec'])
        originals = deepcopy((desired, observed))
        self.assert_matches(desired, observed)
        self.assertEqual((desired, observed), originals)
        for path, value in ((('securityContext',), None), (('terminationGracePeriodSeconds',), 30.0),
                            (('containers', 0, 'readinessProbe', 'timeoutSeconds'), True),
                            (('containers', 0, 'tty'), 0), (('containers', 0, 'volumeMounts', 0, 'readOnly'), 0),
                            (('volumes', 0, 'configMap', 'defaultMode'), 420.0)):
            poison = deepcopy(observed)
            cursor = poison['spec']
            for part in path[:-1]:
                cursor = cursor[part]
            cursor[path[-1]] = value
            self.assertFalse(proofs._matches_applied(desired, poison), path)

    def test_all_default_names_reject_wrong_kind_and_wrong_structural_path(self):
        values = {'dnsPolicy': 'ClusterFirst', 'restartPolicy': 'Always', 'schedulerName': 'default-scheduler',
                  'terminationGracePeriodSeconds': 30, 'securityContext': {}, 'enableServiceLinks': True,
                  'serviceAccount': 'driver', 'terminationMessagePath': '/dev/termination-log',
                  'terminationMessagePolicy': 'File', 'resources': {}, 'protocol': 'TCP', 'apiVersion': 'v1',
                  'timeoutSeconds': 1, 'periodSeconds': 10, 'successThreshold': 1, 'failureThreshold': 3,
                  'type': '', 'defaultMode': 420, 'revisionHistoryLimit': 10, 'progressDeadlineSeconds': 600,
                  'sessionAffinity': 'None', 'internalTrafficPolicy': 'Cluster', 'ipFamilyPolicy': 'SingleStack',
                  'ipFamilies': ['IPv4'], 'maxSurge': 0, 'preserveUnknownFields': False, 'conversion': {'strategy': 'None'}}
        for key, value in values.items():
            with self.subTest(key=key):
                desired = object_for('ConfigMap')
                observed = response(desired)
                observed['spec'][key] = value
                self.assertFalse(proofs._matches_applied(desired, observed))
                desired = object_for()
                desired['spec'] = {'securityContext': {}}
                observed = response(desired)
                observed['spec']['securityContext'][key] = value
                self.assertFalse(proofs._matches_applied(desired, observed))

    def test_runtime_metadata_and_serialization_do_not_expand_cluster_scope(self):
        for kind, api in (('Namespace', 'v1'), ('CustomResourceDefinition', 'apiextensions.k8s.io/v1'),
                          ('ClusterRole', 'rbac.authorization.k8s.io/v1'), ('ClusterRoleBinding', 'rbac.authorization.k8s.io/v1')):
            desired = object_for(kind, api)
            desired['metadata'].pop('namespace')
            observed = response(desired)
            observed['metadata']['namespace'] = 'default'
            self.assertFalse(proofs._matches_applied(desired, observed), kind)
        for key, value in (('preserveUnknownFields', False), ('tty', False), ('readOnly', False)):
            desired = object_for()
            desired['spec'][key] = value
            observed = response(desired)
            observed['spec'].pop(key)
            self.assertFalse(proofs._matches_applied(desired, observed), key)

    def test_empty_root_annotations_are_not_a_general_serialization_omission(self):
        desired = object_for('ConfigMap')
        observed = response(desired)
        observed['metadata']['annotations'] = {}
        self.assertFalse(proofs._matches_applied(desired, observed))


if __name__ == '__main__':
    unittest.main()
