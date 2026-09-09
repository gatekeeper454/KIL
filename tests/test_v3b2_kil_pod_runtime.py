from copy import deepcopy
from dataclasses import replace
import json, unittest

from kil.v3b2_proofs import RawObservation
from kil.v3b2_node_image_references import ExpectedNodeImage, node_image_inspect_argv, validate_node_image_references
from kil.v3b2_runtime_ownership import validate_runtime_ownership
from kil.v3b2_runtime_endpoints import validate_runtime_endpoints
from kil.v3b2_generated_kil_pod_configuration import validate_generated_kil_pod_configuration
from tests.test_v3b2_runtime_endpoints import fixture as endpoint_fixture, encode
from tests.test_v3b2_generated_kil_pod_configuration import fixture as generated_fixture
from tests.test_v3b2_driver_pod_configuration import fixture as driver_fixture


def fixture():
    args=endpoint_fixture(); document=json.loads(args["runtime_objects"]); rows=document["items"]
    generated=json.loads(generated_fixture()["runtime_objects"])
    source={(r["metadata"].get("namespace",""),r["metadata"]["name"]):r for r in generated["items"] if r["kind"]=="Pod"}
    drivers={r["metadata"]["namespace"]:r for r in driver_fixture()["pods"]}
    kil=[r for r in rows if r["kind"]=="Pod" and r["metadata"].get("namespace","").startswith("kil-")]
    for index,row in enumerate(kil,1):
        key=(row["metadata"]["namespace"],row["metadata"]["name"]); status=row.get("status")
        if row["metadata"]["name"]=="driver":
            template=deepcopy(drivers[key[0]])
        else: template=deepcopy(source[key])
        uid,rv=row["metadata"]["uid"],row["metadata"]["resourceVersion"]
        row.clear(); row.update(template); row["metadata"].update(uid=uid,resourceVersion=rv)
        ip=(status or {}).get("podIP",f"10.244.2.{index}")
        row["spec"]["nodeName"]="kil-v3-lab-control-plane"
        row["metadata"]["annotations"].update({"cni.projectcalico.org/podIP":ip+"/32",
            "cni.projectcalico.org/podIPs":ip+"/32","cni.projectcalico.org/containerID":f"{index:064x}"})
        role="driver" if key[1]=="driver" else next(c["name"] for c in row["spec"]["containers"])
        row["status"]={"phase":"Running","hostIP":"192.168.5.2","podIP":ip,"podIPs":[{"ip":ip}],
            "conditions":[{"type":"Ready","status":"True"},{"type":"Initialized","status":"True"}],
            "containerStatuses":[{"name":role,"image":"","imageID":"","containerID":"containerd://"+f"{100+index:064x}",
                "ready":True,"started":True,"restartCount":0,"state":{"running":{"startedAt":"2026-09-08T01:02:03Z"}}}]}
    args["runtime_objects"]=encode(document); ownership=validate_runtime_ownership(**args)
    configuration=validate_generated_kil_pod_configuration(ownership=ownership)
    endpoints=validate_runtime_endpoints(ownership=ownership)
    identity=ownership.owned_identity; workload=ownership.workload
    expected=(ExpectedNodeImage("kil","kil.local/kil-v3b2:sha256-"+workload.kil_image_id[7:],"sha256:"+"c"*64,
              workload.kil_image_id,"application/vnd.oci.image.manifest.v1+json",
              ("kil.local/kil-v3b2:sha256-"+workload.kil_image_id[7:],),(),"sha256:"+"c"*64),
             ExpectedNodeImage("envoy",workload.envoy_image_digest,"sha256:"+"e"*64,
              "sha256:"+workload.envoy_image_digest.rsplit(":",1)[1],"application/vnd.oci.image.index.v1+json",
              (),(workload.envoy_image_digest,),"sha256:"+"e"*64))
    env=(("DOCKER_CONFIG","/tmp/owned/docker-config"),("DOCKER_HOST",identity.docker_host)); inspections=[]; table=["REF TYPE DIGEST STATUS SIZE UNPACKED"]
    for i,e in enumerate(expected):
        status={"id":e.config_digest,"repoTags":list(e.allowed_repo_tags),"repoDigests":list(e.allowed_repo_digests),"size":"1","username":"","pinned":False}
        inspections.append(RawObservation(f"cri_image_{i}",node_image_inspect_argv(identity.node_container_id,e.query_reference),env,0,json.dumps({"status":status}).encode(),b""))
        for alias in (*e.allowed_repo_tags,*e.allowed_repo_digests): table.append(f"{alias} {e.target_media_type} {e.target_digest} complete (1/1) 1 B true")
    node=RawObservation("node_images",("docker","exec",identity.node_container_id,"/usr/local/bin/ctr","--address","/run/containerd/containerd.sock","--namespace","k8s.io","images","check","--snapshotter","overlayfs"),env,0,("\n".join(table)+"\n").encode(),b"")
    images=validate_node_image_references(identity=identity,docker_config="/tmp/owned/docker-config",expected_images=expected,inspections=tuple(inspections),node_images=node)
    raw=json.loads(ownership.runtime_objects)
    for row in raw["items"]:
        if row["kind"]=="Pod" and row["metadata"].get("namespace","").startswith("kil-"):
            role=row["status"]["containerStatuses"][0]["name"]; image=images.bindings[1 if role=="envoy" else 0]
            row["status"]["containerStatuses"][0].update(image=image.runtime_image,imageID=image.image_ref)
    args["runtime_objects"]=encode(raw); ownership=validate_runtime_ownership(**args)
    return validate_generated_kil_pod_configuration(ownership=ownership),validate_runtime_endpoints(ownership=ownership),images,args

class KilPodRuntimeTest(unittest.TestCase):
    def test_exact_twelve_runtime_bindings_remain_incomplete(self):
        from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
        config,endpoints,images,_=fixture(); proof=validate_kil_pod_runtime(configuration=config,endpoints=endpoints,node_images=images)
        self.assertEqual(len(proof.bindings),12); self.assertFalse(proof.runtime_contract_complete); self.assertEqual(replace(proof),proof)
        envoy=next(row for row in proof.bindings if row.role=="envoy")
        self.assertEqual(envoy.runtime_image,images.bindings[1].expected.config_digest)
        self.assertEqual(envoy.image_ref,images.bindings[1].expected.query_reference)

    def test_kil_optional_repo_digest_is_accepted_and_unapproved_alias_is_rejected(self):
        from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
        config,endpoints,images,args=fixture(); expected=list(images.expected_images)
        alias="kil.local/kil-v3b2@"+expected[0].target_digest
        expected[0]=replace(expected[0],allowed_repo_digests=(alias,))
        inspections=list(images.inspections); payload=json.loads(inspections[0].stdout); payload["status"]["repoDigests"]=[alias]
        inspections[0]=replace(inspections[0],stdout=json.dumps(payload).encode())
        node=replace(images.node_images,stdout=images.node_images.stdout+
            f"{alias} {expected[0].target_media_type} {expected[0].target_digest} complete (1/1) 1 B true\n".encode())
        with_digest=validate_node_image_references(identity=images.identity,docker_config=images.docker_config,
            expected_images=tuple(expected),inspections=tuple(inspections),node_images=node)
        document=json.loads(config.ownership.runtime_objects)
        for row in document["items"]:
            if row["kind"]=="Pod" and row["metadata"].get("namespace","").startswith("kil-"):
                status=row.get("status",{}).get("containerStatuses",[])
                if status and status[0]["name"]!="envoy": status[0]["imageID"]=alias
        args["runtime_objects"]=encode(document); own=validate_runtime_ownership(**args)
        proof=validate_kil_pod_runtime(configuration=validate_generated_kil_pod_configuration(ownership=own),
            endpoints=validate_runtime_endpoints(ownership=own),node_images=with_digest)
        self.assertTrue(all(row.image_ref==alias for row in proof.bindings if row.role!="envoy"))
        bad=json.loads(images.inspections[1].stdout); bad["status"]["repoTags"]=["docker.io/envoyproxy/envoy:unapproved"]
        with self.assertRaises(ValueError): validate_node_image_references(identity=images.identity,docker_config=images.docker_config,
            expected_images=images.expected_images,inspections=(images.inspections[0],replace(images.inspections[1],stdout=json.dumps(bad).encode())),node_images=images.node_images)

    def test_constructor_and_owned_docker_authority_are_recomputed(self):
        from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
        config,endpoints,images,_=fixture(); proof=validate_kil_pod_runtime(configuration=config,endpoints=endpoints,node_images=images)
        with self.assertRaises(ValueError): replace(proof, bindings=proof.bindings[:-1])
        with self.assertRaises(ValueError): replace(proof, runtime_contract_complete=True)
        foreign=deepcopy(images); object.__setattr__(foreign,"docker_config","/tmp/foreign/docker-config")
        with self.assertRaises(ValueError): validate_kil_pod_runtime(configuration=config,endpoints=endpoints,node_images=foreign)

    def test_runtime_state_image_and_identity_collisions_reject(self):
        from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
        for mutation in ("waiting","image","image_swap","restart","restart_bool","ready_int","started_int",
                         "duplicate_ready","duplicate_status","cni","init_status","container_collision","ip_collision"):
            config,endpoints,images,args=fixture(); doc=json.loads(args["runtime_objects"]); pod=next(r for r in doc["items"] if r["kind"]=="Pod" and r["metadata"].get("namespace","").startswith("kil-"))
            if mutation=="waiting": pod["status"]["containerStatuses"][0]["state"]={"waiting":{"reason":"x"}}
            elif mutation=="image": pod["status"]["containerStatuses"][0]["imageID"]=images.bindings[0].expected.target_digest
            elif mutation=="image_swap":
                envoy=next(r for r in doc["items"] if r["kind"]=="Pod" and r.get("status",{}).get("containerStatuses",[{}])[0].get("name")=="envoy")
                cs=envoy["status"]["containerStatuses"][0]; cs["image"],cs["imageID"]=cs["imageID"],cs["image"]
            elif mutation=="restart": pod["status"]["containerStatuses"][0]["restartCount"]=1
            elif mutation=="restart_bool": pod["status"]["containerStatuses"][0]["restartCount"]=False
            elif mutation=="ready_int": pod["status"]["containerStatuses"][0]["ready"]=1
            elif mutation=="started_int": pod["status"]["containerStatuses"][0]["started"]=1
            elif mutation=="duplicate_ready": pod["status"]["conditions"].append({"type":"Ready","status":"True"})
            elif mutation=="duplicate_status": pod["status"]["containerStatuses"].append(deepcopy(pod["status"]["containerStatuses"][0]))
            elif mutation=="cni": pod["metadata"]["annotations"]["cni.projectcalico.org/containerID"]="A"*64
            elif mutation=="init_status": pod["status"]["initContainerStatuses"]=[]
            elif mutation=="container_collision": pod["status"]["containerStatuses"][0]["containerID"]="containerd://"+args["owned_identity"].node_container_id
            else:
                other=next(r for r in doc["items"] if r is not pod and r["kind"]=="Pod" and r["metadata"].get("namespace","").startswith("kil-"))
                ip=other["status"]["podIP"]; pod["status"].update(podIP=ip,podIPs=[{"ip":ip}])
                pod["metadata"]["annotations"].update({"cni.projectcalico.org/podIP":ip+"/32","cni.projectcalico.org/podIPs":ip+"/32"})
            args["runtime_objects"]=encode(doc); own=validate_runtime_ownership(**args)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): validate_kil_pod_runtime(configuration=validate_generated_kil_pod_configuration(ownership=own),endpoints=validate_runtime_endpoints(ownership=own),node_images=images)

    def test_malformed_nonready_condition_records_are_not_filtered_out(self):
        from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
        for poison in (None, {}):
            config,endpoints,images,args=fixture(); document=json.loads(args["runtime_objects"])
            driver=next(r for r in document["items"] if r["kind"]=="Pod" and r["metadata"].get("name")=="driver")
            driver["status"]["conditions"].insert(0,poison); args["runtime_objects"]=encode(document)
            own=validate_runtime_ownership(**args)
            with self.subTest(poison=poison),self.assertRaises(ValueError): validate_kil_pod_runtime(
                configuration=validate_generated_kil_pod_configuration(ownership=own),
                endpoints=validate_runtime_endpoints(ownership=own),node_images=images)

    def test_cross_dependency_raw_and_endpoint_uid_sources_cannot_be_mixed(self):
        from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
        config,endpoints,images,args=fixture(); document=json.loads(args["runtime_objects"])
        pod=next(r for r in document["items"] if r["kind"]=="Pod" and r["metadata"].get("namespace","").startswith("kil-") and r["metadata"]["name"]!="driver")
        old=pod["metadata"]["uid"]; pod["metadata"]["uid"]="replacement-pod-uid"
        slice_row=next(r for r in document["items"] if r["kind"]=="EndpointSlice" and
                       r["endpoints"][0].get("targetRef",{}).get("uid")==old)
        slice_row["endpoints"][0]["targetRef"]["uid"]="replacement-pod-uid"
        args["runtime_objects"]=encode(document); changed=validate_runtime_ownership(**args)
        changed_endpoints=validate_runtime_endpoints(ownership=changed)
        with self.assertRaises(ValueError): validate_kil_pod_runtime(configuration=config,endpoints=changed_endpoints,node_images=images)

    def test_source_known_optional_container_status_fields_are_retained_but_not_certified(self):
        from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
        config,endpoints,images,args=fixture(); document=json.loads(args["runtime_objects"])
        pod=next(r for r in document["items"] if r["kind"]=="Pod" and r["metadata"].get("namespace","").startswith("kil-"))
        cs=pod["status"]["containerStatuses"][0]
        cs.update(lastState={}, allocatedResources={"cpu":"1"}, resources={"requests":{"cpu":"1"}},
                  volumeMounts=[{"name":"data"}], user={"linux":{"uid":65532}},
                  allocatedResourcesStatus=[{"name":"example"}], stopSignal="SIGTERM")
        args["runtime_objects"]=encode(document); own=validate_runtime_ownership(**args)
        proof=validate_kil_pod_runtime(configuration=validate_generated_kil_pod_configuration(ownership=own),
            endpoints=validate_runtime_endpoints(ownership=own),node_images=images)
        retained=json.loads(proof.configuration.ownership.runtime_objects)
        retained_cs=next(r for r in retained["items"] if r["metadata"].get("uid")==pod["metadata"]["uid"])["status"]["containerStatuses"][0]
        self.assertEqual(retained_cs["lastState"],{}); self.assertEqual(retained_cs["stopSignal"],"SIGTERM")

    def test_unknown_contradictory_or_wrong_typed_optional_status_fields_reject(self):
        from kil.v3b2_kil_pod_runtime import validate_kil_pod_runtime
        cases=(("lastState",None),("lastState",{"terminated":{"exitCode":0}}),("allocatedResources",[]),
               ("resources",[]),("volumeMounts",{}),("user",[]),("allocatedResourcesStatus",{}),
               ("stopSignal",1),("unknownStatusField",{}))
        for field,value in cases:
            config,endpoints,images,args=fixture(); document=json.loads(args["runtime_objects"])
            pod=next(r for r in document["items"] if r["kind"]=="Pod" and r["metadata"].get("namespace","").startswith("kil-"))
            pod["status"]["containerStatuses"][0][field]=value; args["runtime_objects"]=encode(document)
            own=validate_runtime_ownership(**args)
            with self.subTest(field=field),self.assertRaises(ValueError): validate_kil_pod_runtime(
                configuration=validate_generated_kil_pod_configuration(ownership=own),
                endpoints=validate_runtime_endpoints(ownership=own),node_images=images)

if __name__=="__main__": unittest.main()
