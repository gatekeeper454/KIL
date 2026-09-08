"""Static configuration comparison for the pinned Kubernetes 1.36.1 API.

Only root-kind-specific structural locations are normalized. This is not an
identity, ownership, readiness, allocation, or admission proof. In particular,
Service allocations and Pod scheduling/CNI/admission additions fail closed;
their independent expected bindings belong to the later resource proof.
"""
from copy import deepcopy
from datetime import datetime
import json
import re


class DefaultError(ValueError):
    pass


_WORKLOADS = {("apps/v1", "Deployment"), ("apps/v1", "DaemonSet")}
_NAMESPACED = {
    ("v1", kind) for kind in ("Pod", "Service", "ServiceAccount", "ConfigMap")
} | _WORKLOADS | {("policy/v1", "PodDisruptionBudget"), ("networking.k8s.io/v1", "NetworkPolicy"),
                  ("rbac.authorization.k8s.io/v1", "Role"), ("rbac.authorization.k8s.io/v1", "RoleBinding")}
_CLUSTER = {("v1", "Namespace"), ("apiextensions.k8s.io/v1", "CustomResourceDefinition"),
            ("rbac.authorization.k8s.io/v1", "ClusterRole"), ("rbac.authorization.k8s.io/v1", "ClusterRoleBinding")}
_LAST_APPLIED = "kubectl.kubernetes.io/last-applied-configuration"
_REVISION = "deployment.kubernetes.io/revision"


def object_key(document):
    """Use the same finite namespace default for apply-set identity joins."""
    root = (document["apiVersion"], document["kind"])
    metadata = document["metadata"]
    namespace = metadata.get("namespace", "default" if root in _NAMESPACED else "")
    return (*root, namespace, metadata["name"])


def _equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(_equal(value, right[key]) for key, value in left.items())
    if type(left) is list:
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    return left == right


def _timestamp(value):
    if type(value) is not str or re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z", value) is None:
        raise DefaultError("invalid API timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DefaultError("invalid API timestamp") from error


def _decimal(value):
    return (type(value) is str and re.fullmatch(r"[1-9][0-9]{0,19}", value) is not None
            and int(value) <= 2**64 - 1)


def _managed_fields(value):
    if type(value) is not list or len(value) > 64:
        raise DefaultError("unbounded managedFields")
    if len(json.dumps(value, allow_nan=False)) > 1024 * 1024:
        raise DefaultError("unbounded managedFields")
    for row in value:
        if (type(row) is not dict or not {"manager", "operation", "apiVersion", "fieldsType", "fieldsV1"} <= row.keys()
                or row.keys() - {"manager", "operation", "apiVersion", "fieldsType", "fieldsV1", "time", "subresource"}
                or row["operation"] not in {"Apply", "Update"} or row["fieldsType"] != "FieldsV1"
                or any(type(row[key]) is not str or not 1 <= len(row[key]) <= 128 for key in ("manager", "apiVersion"))
                or ("subresource" in row and row["subresource"] not in {"", "status", "scale"})):
            raise DefaultError("invalid managedFields entry")
        if "time" in row:
            _timestamp(row["time"])
        pending = [(row["fieldsV1"], 0)]
        count = 0
        while pending:
            member, depth = pending.pop()
            count += 1
            if type(member) is not dict or depth > 64 or count > 32768:
                raise DefaultError("invalid managedFields field tree")
            for key, child in member.items():
                if type(key) is not str or len(key) > 4096 or not (key == "." or key.startswith(("f:", "k:", "v:", "i:"))):
                    raise DefaultError("invalid managedFields field key")
                pending.append((child, depth + 1))


def _metadata(metadata, root):
    if type(metadata) is not dict or "deletionTimestamp" in metadata or "deletionGracePeriodSeconds" in metadata:
        raise DefaultError("invalid or deleting root metadata")
    # API UIDs are opaque here; the resource proof must bind exact incarnation.
    if "uid" in metadata and (type(metadata["uid"]) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", metadata["uid"]) is None):
        raise DefaultError("invalid API UID")
    if "resourceVersion" in metadata and not _decimal(metadata["resourceVersion"]):
        raise DefaultError("invalid API resourceVersion")
    if "generation" in metadata and (type(metadata["generation"]) is not int or not 1 <= metadata["generation"] <= 2**63 - 1):
        raise DefaultError("invalid API generation")
    if "creationTimestamp" in metadata:
        _timestamp(metadata["creationTimestamp"])
    if "managedFields" in metadata:
        _managed_fields(metadata["managedFields"])
    for key in ("uid", "resourceVersion", "generation", "creationTimestamp", "managedFields"):
        metadata.pop(key, None)
    if root in _CLUSTER and "namespace" in metadata:
        raise DefaultError("cluster-scoped object has a namespace")
    if root in _NAMESPACED:
        metadata.setdefault("namespace", "default")
    if "annotations" in metadata:
        annotations = metadata["annotations"]
        if type(annotations) is not dict:
            raise DefaultError("invalid root annotations")
        removed_runtime_annotation = False
        if _LAST_APPLIED in annotations:
            value = annotations.pop(_LAST_APPLIED)
            if type(value) is not str or len(value.encode("utf-8")) > 262144:
                raise DefaultError("unbounded last-applied annotation")
            removed_runtime_annotation = True
        if root == ("apps/v1", "Deployment") and _REVISION in annotations:
            revision = annotations.pop(_REVISION)
            if not _decimal(revision) or revision != "1":
                raise DefaultError("Deployment is not the fresh unchanged revision")
            removed_runtime_annotation = True
        if removed_runtime_annotation and not annotations:
            metadata.pop("annotations")


def _defaults(value, defaults):
    for key, default in defaults.items():
        value.setdefault(key, deepcopy(default))


def _omit_false(value, key):
    if value.get(key) is False:
        value.pop(key)


def _container(container):
    _defaults(container, {"terminationMessagePath": "/dev/termination-log", "terminationMessagePolicy": "File", "resources": {}})
    _omit_false(container, "tty")
    for port in container.get("ports", []):
        port.setdefault("protocol", "TCP")
    for mount in container.get("volumeMounts", []):
        _omit_false(mount, "readOnly")
    for env in container.get("env", []):
        field_ref = env.get("valueFrom", {}).get("fieldRef")
        if field_ref is not None:
            field_ref.setdefault("apiVersion", "v1")
    for key in ("livenessProbe", "readinessProbe", "startupProbe"):
        if key in container:
            probe = container[key]
            if len({"exec", "httpGet", "tcpSocket", "grpc"} & probe.keys()) != 1:
                raise DefaultError("probe has no unique existing action")
            _defaults(probe, {"timeoutSeconds": 1, "periodSeconds": 10, "successThreshold": 1, "failureThreshold": 3})


def _pod_spec(spec, *, direct):
    _defaults(spec, {"dnsPolicy": "ClusterFirst", "restartPolicy": "Always", "securityContext": {},
                     "terminationGracePeriodSeconds": 30, "schedulerName": "default-scheduler"})
    # SetDefaults_Pod, not SetDefaults_PodSpec: templates must not gain this.
    if direct:
        spec.setdefault("enableServiceLinks", True)
    if "serviceAccountName" in spec:
        spec.setdefault("serviceAccount", spec["serviceAccountName"])
    for key in ("containers", "initContainers"):
        for container in spec.get(key, []):
            _container(container)
    for volume in spec.get("volumes", []):
        if "hostPath" in volume:
            volume["hostPath"].setdefault("type", "")
        if "configMap" in volume:
            volume["configMap"].setdefault("defaultMode", 420)


def configuration(document):
    """Return a new static configuration; reject malformed runtime metadata.

    Runtime additions requiring relational authority are deliberately retained,
    so they cannot compare equal to a desired document lacking those fields.
    """
    value = deepcopy(document)
    root = (value["apiVersion"], value["kind"])
    value.pop("status", None)
    _metadata(value["metadata"], root)
    if root == ("v1", "Namespace"):
        value["metadata"].setdefault("labels", {}).setdefault("kubernetes.io/metadata.name", value["metadata"]["name"])
        value.setdefault("spec", {}).setdefault("finalizers", ["kubernetes"])
    spec = value.get("spec")
    if spec is None:
        return value
    if root == ("v1", "Service") and spec.get("type") == "ClusterIP":
        # Family fields are allocator-derived and need independent B.1 authority.
        _defaults(spec, {"sessionAffinity": "None", "internalTrafficPolicy": "Cluster"})
    if root == ("apiextensions.k8s.io/v1", "CustomResourceDefinition"):
        _omit_false(spec, "preserveUnknownFields")
        spec.setdefault("conversion", {"strategy": "None"})
    if root == ("v1", "Pod"):
        _pod_spec(spec, direct=True)
    if root in _WORKLOADS:
        spec.setdefault("revisionHistoryLimit", 10)
        if root[1] == "Deployment":
            spec.setdefault("progressDeadlineSeconds", 600)
        elif spec.get("updateStrategy", {}).get("type") == "RollingUpdate":
            rolling = spec["updateStrategy"].get("rollingUpdate")
            if type(rolling) is dict and rolling.get("maxUnavailable") == 1:
                rolling.setdefault("maxSurge", 0)
        if "template" in spec:
            template = spec["template"]
            metadata = template.get("metadata", {})
            if "creationTimestamp" in metadata and metadata["creationTimestamp"] is None:
                metadata.pop("creationTimestamp")
            _pod_spec(template["spec"], direct=False)
    return value


def matches_configuration(expected, observed):
    """Compare configurations with exact JSON scalar types; never prove runtime."""
    try:
        return _equal(configuration(expected), configuration(observed))
    except (DefaultError, TypeError, KeyError, AttributeError, ValueError, RecursionError):
        return False
