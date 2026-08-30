# V3B-1 Toolchain and Envoy HTTP Boundary Implementation Plan

> **Execution contract:** Implement this plan task-by-task with test-first checkpoints. Steps use checkbox (`- [ ]`) syntax for tracking. No delegation is implied by this plan.

**Goal:** Establish a reproducible V3B laboratory toolchain and run the existing V3A authorization contract through a real Envoy HTTP `ext_authz` boundary before creating the Kind cluster.

**Architecture:** V3B is split into two falsifiable increments. V3B-1 pins and verifies the host tools, implements thin HTTP processes around the already-reviewed `AuthorizationAdapter` and harmless target ledger, builds one content-identified KIL service image, and proves permit/deny/no-forward behavior through pinned Envoy locally. V3B-2 will reuse those exact artifacts in the three-namespace Kind topology and execute the complete cluster failure matrix; V3C remains repetition, latency, and publication promotion.

**Tech Stack:** Python 3.12.13, `unittest`, `cryptography==50.0.0`, Colima 0.10.3, Lima 2.2.0, Docker CLI 29.7.2, Kind 0.32.0, Kubernetes node 1.36.1, kubectl 1.36.3, Envoy 1.39.0, Calico 3.32.0, JSON/JSONL, SHA-256.

---

## Scope and resolved version profile

The founder-approved topology and HTTP contract remain unchanged. The version
table in the approved design was explicitly planned rather than resolved. The
released, mutually supported profile on 2026-08-30 is:

| Component | V3B-1 identity |
|---|---|
| Host | macOS 26.6.1, arm64 |
| Colima | 0.10.3, dedicated profile `kil-v3-lab` |
| Lima | 2.2.0 |
| Docker CLI | 29.7.2, official Apple-silicon static client archive |
| Kind | 0.32.0 |
| Kubernetes node | `kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5` |
| kubectl | 1.36.3 |
| Envoy | `docker.io/envoyproxy/envoy:v1.39.0`, resolved to a registry digest before use |
| Calico | 3.32.0, reserved for V3B-2 NetworkPolicy enforcement |
| KIL application | Python 3.12.13 plus `cryptography==50.0.0` |

Kind 0.32.0 officially defaults to Kubernetes 1.36.1 and publishes the exact
multi-architecture node digest above. Calico 3.32 is tested against Kubernetes
1.36. Envoy 1.39.0 is the available stable 1.39 release and includes the July
2026 `ext_authz` security fixes. The earlier planned Kind 0.33.0, Kubernetes
1.37.0 node image, and Envoy 1.39.1 are not the resolved stable combination and
must not be fabricated in evidence.

## File map

- `deploy/kind/v3b-profile.json` — tracked desired versions, release URLs, exact node digest, fixed ports, and evidence labels.
- `src/kil/v3b_preflight.py` — closed profile parser plus pure tool/version/hash checks.
- `tests/test_v3b_preflight.py` — proves profile closure, version mismatch failure, and exact-cluster safety.
- `tools/bootstrap_v3b_tools.py` — downloads only allowlisted release assets into ignored `.tools/`, verifies upstream sidecars where published, and writes a local content lock.
- `tests/test_v3b_tool_bootstrap.py` — proves URL allowlisting, size bounds, safe archive extraction, checksum enforcement, and atomic replacement.
- `src/kil/ext_authz_http.py` — pure HTTP request/response mapping around the existing immutable `AuthorizationAdapter` plus the stdlib server entry point.
- `tests/test_ext_authz_http.py` — proves the exact trusted-input contract, redaction, generic denial/error responses, fixed track, and decision logging.
- `src/kil/target_http.py` — harmless target application and append-before-response JSONL ledger.
- `tests/test_target_http.py` — proves the two no-effect paths, exact marker semantics, duplicate detection, and no credential persistence.
- `src/kil/v3b_envoy.py` — deterministic Envoy bootstrap-configuration renderer.
- `tests/test_v3b_envoy.py` — inspects the rendered filter order, timeout, fail-closed mode, headers, clusters, and access-log join fields.
- `deploy/kind/Dockerfile.v3b` — non-root KIL service image using an externally supplied digest-pinned Python base.
- `tests/test_v3b_container_contract.py` — statically enforces non-root execution, read-only-compatible paths, healthcheck, and no embedded secrets.
- `tools/v3b1_local_envoy.py` — exact local lifecycle controller for the dedicated Colima profile, image locks, three Envoy containers, adapters, targets, and joined evidence.
- `tests/test_v3b1_local_envoy.py` — proves command construction, exact-name teardown, request equality, and claim-language boundaries without invoking containers.
- `docs/lab/V3-PROGRESS.md` — records V3B-1 results without promoting them to Kind validation.

### Task 1: Resolve and enforce the V3B profile

**Files:**

- Create: `deploy/kind/v3b-profile.json`
- Create: `src/kil/v3b_preflight.py`
- Create: `tests/test_v3b_preflight.py`
- Modify: `docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`
- Modify: `adapters/envoy/README.md`

- [x] **Step 1: Write the failing profile tests**

```python
from pathlib import Path
import json
import unittest

from kil.v3b_preflight import ProfileError, V3BProfile


ROOT = Path(__file__).resolve().parents[1]


class V3BProfileTest(unittest.TestCase):
    def test_loads_the_closed_released_profile(self):
        profile = V3BProfile.load(ROOT / "deploy/kind/v3b-profile.json")
        self.assertEqual(profile.kind_version, "0.32.0")
        self.assertEqual(profile.kubernetes_version, "1.36.1")
        self.assertEqual(profile.envoy_version, "1.39.0")
        self.assertEqual(profile.cluster_name, "kil-v3-lab")
        self.assertEqual(profile.colima_profile, "kil-v3-lab")
        self.assertEqual(profile.evidence_scope, "local_envoy_boundary")

    def test_rejects_unknown_profile_fields(self):
        raw = json.loads((ROOT / "deploy/kind/v3b-profile.json").read_text())
        raw["validated"] = True
        with self.assertRaisesRegex(ProfileError, "unknown"):
            V3BProfile.from_mapping(raw)

    def test_refuses_any_other_cluster_or_colima_profile(self):
        raw = json.loads((ROOT / "deploy/kind/v3b-profile.json").read_text())
        raw["cluster_name"] = "default"
        with self.assertRaisesRegex(ProfileError, "kil-v3-lab"):
            V3BProfile.from_mapping(raw)
```

- [x] **Step 2: Run the focused test and verify RED**

Run:

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_v3b_preflight -v
```

Expected: `ModuleNotFoundError: No module named 'kil.v3b_preflight'`.

- [x] **Step 3: Add the exact tracked profile**

Create `deploy/kind/v3b-profile.json` as a closed JSON object containing these
literal identities and URLs:

```json
{
  "schema_version": "kil.v3b-profile.v1",
  "host_os": "darwin",
  "host_arch": "arm64",
  "colima_version": "0.10.3",
  "colima_profile": "kil-v3-lab",
  "lima_version": "2.2.0",
  "docker_cli_version": "29.7.2",
  "docker_cli_url": "https://download.docker.com/mac/static/stable/aarch64/docker-29.7.2.tgz",
  "kind_version": "0.32.0",
  "kind_url": "https://github.com/kubernetes-sigs/kind/releases/download/v0.32.0/kind-darwin-arm64",
  "kind_checksum_url": "https://github.com/kubernetes-sigs/kind/releases/download/v0.32.0/kind-darwin-arm64.sha256sum",
  "kubernetes_version": "1.36.1",
  "kind_node_image": "kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5",
  "kubectl_version": "1.36.3",
  "kubectl_url": "https://dl.k8s.io/release/v1.36.3/bin/darwin/arm64/kubectl",
  "kubectl_checksum_url": "https://dl.k8s.io/release/v1.36.3/bin/darwin/arm64/kubectl.sha256",
  "envoy_version": "1.39.0",
  "envoy_image": "docker.io/envoyproxy/envoy:v1.39.0",
  "calico_version": "3.32.0",
  "calico_manifest_url": "https://raw.githubusercontent.com/projectcalico/calico/v3.32.0/manifests/calico.yaml",
  "cluster_name": "kil-v3-lab",
  "gateway_ports": [18080, 18081, 18082],
  "evidence_scope": "local_envoy_boundary"
}
```

- [x] **Step 4: Implement the closed immutable profile**

Implement `V3BProfile` as a frozen, slotted dataclass. `load()` must reject
non-objects, missing fields, unknown fields, JSON type coercion, non-HTTPS
URLs, non-allowlisted hosts, ports outside 1024–65535, duplicate ports, and any
cluster or Colima profile not exactly `kil-v3-lab`. It must require the literal
node digest above and may not accept mutable-only node identities.

- [x] **Step 5: Correct the planned-version table without changing topology**

In the approved design, label the old 0.33.0/1.37.0/1.39.1 row as the original
planning target and add the resolved profile from `v3b-profile.json`. State
that this is a release-availability correction, not an architecture or evidence
boundary change. In `adapters/envoy/README.md`, preserve the five trusted
semantic inputs while clarifying Envoy raw-HTTP transport behavior: method,
path, and Authorization are conveyed automatically; the explicit
`allowed_headers` matcher adds `x-request-id` and `x-kil-q-state`; Host and
Content-Length may also be present as transport metadata but are ignored by
the authorization evaluation.

- [x] **Step 6: Verify and commit Task 1**

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_v3b_preflight -v
make validate PYTHON=/Users/mistorm/.local/bin/python3.12
git add deploy/kind/v3b-profile.json src/kil/v3b_preflight.py tests/test_v3b_preflight.py docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md adapters/envoy/README.md
git commit -m "Resolve the V3B stable toolchain profile"
```

### Task 2: Bootstrap tools into an isolated content lock

**Files:**

- Create: `tools/bootstrap_v3b_tools.py`
- Create: `tests/test_v3b_tool_bootstrap.py`
- Modify: `.gitignore`
- Modify: `Makefile`

- [ ] **Step 1: Write failing downloader-safety tests**

Tests must use in-memory byte streams and temporary directories; they must not
access the network. Cover these exact behaviors:

```python
class V3BToolBootstrapTest(unittest.TestCase):
    def test_rejects_a_non_allowlisted_download_host(self):
        with self.assertRaisesRegex(ToolBootstrapError, "allowlisted"):
            validate_download_url("https://example.invalid/docker.tgz")

    def test_checksum_mismatch_never_replaces_existing_binary(self):
        destination.write_bytes(b"known-good")
        with self.assertRaisesRegex(ToolBootstrapError, "checksum"):
            install_direct_binary(b"tampered", "0" * 64, destination)
        self.assertEqual(destination.read_bytes(), b"known-good")

    def test_docker_archive_accepts_only_the_docker_member(self):
        with self.assertRaisesRegex(ToolBootstrapError, "archive member"):
            extract_docker_cli(archive_with_member("../escape"), destination)
```

- [ ] **Step 2: Verify RED**

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_v3b_tool_bootstrap -v
```

Expected: import failure because `tools/bootstrap_v3b_tools.py` does not exist.

- [ ] **Step 3: Implement bounded atomic downloads**

The tool must:

- accept only URLs already present in `V3BProfile`;
- cap Docker at 64 MiB and direct binaries/checksum files at 128 MiB;
- use a temporary directory under `.tools/tmp`, never `/` or the home root;
- verify Kind and kubectl against their release-specific upstream checksum
  files before `os.replace`;
- extract only the literal `docker/docker` regular-file member from the Docker
  archive, rejecting links and traversal;
- set mode `0755` only after verification;
- write `.tools/locks/v3b-tools.json` with source URL, archive SHA-256,
  executable SHA-256, byte size, and captured version output; and
- never modify shell startup files or the global active Docker context.

Add `.tools/` to `.gitignore`. Add `make v3b-tools` using the selected Python
and `make v3b-preflight` with `PATH=$(CURDIR)/.tools/bin:$(PATH)`.

- [ ] **Step 4: Verify unit behavior before host/network mutation**

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_v3b_tool_bootstrap -v
make validate PYTHON=/Users/mistorm/.local/bin/python3.12
```

- [ ] **Step 5: Execute the explicit host/network gate**

After action approval, run:

```bash
make v3b-tools PYTHON=/Users/mistorm/.local/bin/python3.12
PATH="$PWD/.tools/bin:$PATH" docker --version
PATH="$PWD/.tools/bin:$PATH" kind version
PATH="$PWD/.tools/bin:$PATH" kubectl version --client -o json
```

The gate fails if any version or executable hash differs from the profile and
local content lock. The Docker archive hash, which has no upstream sidecar in
the official static index, is recorded explicitly as locally observed source
content and may not be described as publisher-attested.

- [ ] **Step 6: Commit Task 2 without committing downloaded binaries**

```bash
git add .gitignore Makefile tools/bootstrap_v3b_tools.py tests/test_v3b_tool_bootstrap.py
git commit -m "Add isolated V3B tool bootstrap"
```

### Task 3: Implement the fixed-track HTTP authorization boundary

**Files:**

- Create: `src/kil/ext_authz_http.py`
- Create: `tests/test_ext_authz_http.py`

- [ ] **Step 1: Write failing pure HTTP-mapping tests**

Define immutable `HttpRequest`, `HttpResponse`, and `AuthorizationHttpApp`
interfaces in the tests. Prove:

```python
def test_permit_returns_200_and_only_the_decision_digest(self):
    response = app.handle(valid_signed_request())
    self.assertEqual(response.status, 200)
    self.assertEqual(set(response.headers), {"x-kil-decision-digest"})

def test_policy_denial_is_generic_and_never_contains_internal_reason(self):
    response = app.handle(denied_request())
    self.assertEqual(response.status, 403)
    self.assertEqual(response.body, b"denied\n")
    self.assertNotIn(b"threshold", response.body)

def test_unknown_or_untrusted_headers_never_enter_trusted_fixture_fields(self):
    decision = app.handle(request_with_mode_and_local_evidence_headers())
    self.assertEqual(decision.status, 403)
    self.assertEqual(app.adapter.track, LiveTrack.SIGNED_PLUS_LOCAL_REDUCE)

def test_log_record_redacts_credential_and_signed_state(self):
    app.handle(request_with_secrets())
    encoded = canonical_json(app.records[0])
    self.assertNotIn(b"Bearer", encoded)
    self.assertNotIn(b"eyJ", encoded)
```

- [ ] **Step 2: Verify RED**

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_ext_authz_http -v
```

- [ ] **Step 3: Implement the thin adapter**

The trusted semantic inputs are original method, original path,
`x-request-id`, `authorization`, and `x-kil-q-state`. In Envoy raw HTTP
`ext_authz` mode, method and path are conveyed as the authorization request's
method and path, and Envoy automatically includes Host, Method, Path,
Content-Length, and Authorization. The configured `allowed_headers` matcher
therefore adds only `x-request-id` and `x-kil-q-state`; the application ignores
Host and Content-Length for authorization. Method, path, request ID, credential
validity, action mapping, fixture lookup, expected identity, Q-state, and local
evidence are converted to `LiveFixture`; authorization is delegated unchanged
to the existing immutable `AuthorizationAdapter`. Permit is HTTP 200, policy
denial is generic HTTP 403, and parsing/internal failure is generic HTTP 503.
Every response and JSONL record contains the decision digest when one exists,
but never the credential, Q-state, private key, or internal denial reasons in
the client body.

The stdlib `ThreadingHTTPServer` entry point reads one read-only JSON config
path, fixes the track at process construction, limits headers to 16 KiB, limits
the request body to zero bytes, binds inside the container only, and handles
`/healthz` without invoking authorization.

- [ ] **Step 4: Verify and commit Task 3**

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_ext_authz_http -v
make validate PYTHON=/Users/mistorm/.local/bin/python3.12
git add src/kil/ext_authz_http.py tests/test_ext_authz_http.py
git commit -m "Expose the fixed KIL ext authz HTTP boundary"
```

### Task 4: Implement the harmless target ledger process

**Files:**

- Create: `src/kil/target_http.py`
- Create: `tests/test_target_http.py`

- [ ] **Step 1: Write failing target tests**

```python
def test_admin_marker_is_appended_before_success_response(self):
    response = app.handle(request("/consequential/admin", "v3b-1"))
    self.assertEqual(response.status, 200)
    self.assertEqual(app.records[0]["request_id"], "v3b-1")
    self.assertEqual(app.records[0]["path"], "/consequential/admin")

def test_duplicate_request_id_is_an_evidence_conflict(self):
    app.handle(request("/benign/read", "v3b-1"))
    response = app.handle(request("/benign/read", "v3b-1"))
    self.assertEqual(response.status, 409)
    self.assertTrue(app.invalid)

def test_ledger_never_persists_authorization_or_q_state(self):
    app.handle(request_with_secrets())
    encoded = canonical_json(app.records[0])
    self.assertNotIn(b"authorization", encoded)
    self.assertNotIn(b"q-state", encoded)
```

- [ ] **Step 2: Verify RED**

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_target_http -v
```

- [ ] **Step 3: Implement append-before-response semantics**

Accept only `GET /benign/read` and `POST /consequential/admin`. Require a
bounded `x-request-id`, `x-kil-track`, and `x-kil-decision-digest`. Append one
canonical JSON line containing run ID, request ID, fixed track, path,
monotonic receive/response timestamps, and digest before returning HTTP 200.
Unknown paths return 404 without a marker; duplicate IDs mark the ledger
invalid and return 409. No endpoint performs filesystem, credential, cluster,
or administrative side effects beyond appending to the dedicated ledger file.

- [ ] **Step 4: Verify and commit Task 4**

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_target_http -v
make validate PYTHON=/Users/mistorm/.local/bin/python3.12
git add src/kil/target_http.py tests/test_target_http.py
git commit -m "Add the harmless V3B target ledger"
```

### Task 5: Render and lock the Envoy/container contract

**Files:**

- Create: `src/kil/v3b_envoy.py`
- Create: `tests/test_v3b_envoy.py`
- Create: `deploy/kind/Dockerfile.v3b`
- Create: `tests/test_v3b_container_contract.py`

- [ ] **Step 1: Write failing semantic configuration tests**

Tests call `render_envoy_config(track, authz_host, target_host)` and inspect the
returned dictionary. They must prove:

- `envoy.filters.http.ext_authz` immediately precedes the router;
- timeout is exactly `0.250s`, `failure_mode_allow` is false, and
  `status_on_error.code` is `ServiceUnavailable`;
- the authorization request-header matcher contains exactly `x-request-id`
  and `x-kil-q-state`; the semantic contract also consumes Envoy's
  automatically conveyed method, path, and Authorization, ignores Host and
  Content-Length, and admits no mode/local-evidence/identity/issuer input;
- retries and route-cache clearing are absent;
- access logs are JSON to stdout and contain run ID, request ID, track,
  response code, upstream host, upstream service time, and decision digest;
- the target cluster cannot be selected from a request header; and
- the fixed track is rendered from process configuration only.

- [ ] **Step 2: Verify RED**

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_v3b_envoy tests.test_v3b_container_contract -v
```

- [ ] **Step 3: Implement deterministic Envoy JSON rendering**

Return a closed Python dictionary and serialize it with `canonical_json`.
Generate one listener on container port 8080 plus static authz and target
clusters. Response headers may forward only `x-kil-decision-digest`; request
headers sent upstream include the request ID, fixed track, and digest, but not
the credential or Q-state.

- [ ] **Step 4: Add the hardened service image**

`Dockerfile.v3b` must use `ARG PYTHON_BASE_IMAGE` followed by
`FROM ${PYTHON_BASE_IMAGE}` so the build controller supplies a digest-pinned
Python 3.12.13 slim image. Create UID/GID 65532, install the project with the
`lab` extra, copy no generated evidence or private material, use a read-only-
compatible root filesystem, expose only 8080, and run as 65532:65532. Writable
ledger/config paths are mounted explicitly at runtime.

- [ ] **Step 5: Verify and commit Task 5**

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_v3b_envoy tests.test_v3b_container_contract -v
make validate PYTHON=/Users/mistorm/.local/bin/python3.12
git add src/kil/v3b_envoy.py tests/test_v3b_envoy.py deploy/kind/Dockerfile.v3b tests/test_v3b_container_contract.py
git commit -m "Lock the V3B Envoy and container contract"
```

### Task 6: Execute the local pinned-Envoy boundary proof

**Files:**

- Create: `tools/v3b1_local_envoy.py`
- Create: `tests/test_v3b1_local_envoy.py`
- Modify: `docs/lab/V3-PROGRESS.md`
- Modify: `README.md`

- [ ] **Step 1: Write failing lifecycle and evidence tests**

Use an injected command runner. Prove that the controller:

- starts only Colima profile `kil-v3-lab` with Docker, 4 CPUs, 8 GiB memory,
  60 GiB disk, VZ, and no Kubernetes;
- addresses Docker with a command-local socket/context and never changes the
  user's global Docker context;
- resolves the Python base and Envoy tags to registry digests before build/run;
- builds one KIL image, records its image ID and saved-archive SHA-256, and
  refuses an unlocked image;
- names every container with the exact `kil-v3b1-` prefix and binds gateway
  ports only to `127.0.0.1`;
- sends identical request facts to the three fixed tracks;
- joins decision, Envoy upstream, and target records by run/track/request ID;
- accepts a deny proof only with no upstream host and zero target markers;
- tears down only exact recorded container names and the dedicated Colima
  profile; and
- labels output `local_envoy_boundary`, never `kind_cluster_validated` or
  historical prevention.

- [ ] **Step 2: Verify RED**

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_v3b1_local_envoy -v
```

- [ ] **Step 3: Implement the exact lifecycle controller**

Provide `preflight`, `up`, `run`, `collect`, and `down` subcommands. `up`
refuses any running non-dedicated profile or occupied port; `down` requires a
content-addressed local run manifest and deletes no unrecorded object. The
first run executes the central `permit / permit / deny` case and writes
requests, decisions, Envoy access records, target records, joins, manifest,
summary, and `SHA256SUMS` under
`artifacts/generated/v3b1-local-envoy/<run-id>/`.

- [ ] **Step 4: Verify all non-container behavior**

```bash
PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 -m unittest tests.test_v3b1_local_envoy -v
make validate PYTHON=/Users/mistorm/.local/bin/python3.12
```

- [ ] **Step 5: Execute the explicit runtime-mutation gate**

After approval to start Colima, pull images, and create local containers:

```bash
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 tools/v3b1_local_envoy.py preflight
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 tools/v3b1_local_envoy.py up
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 tools/v3b1_local_envoy.py run
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src /Users/mistorm/.local/bin/python3.12 tools/v3b1_local_envoy.py down
```

The run is accepted only if the three joined outcomes are
`permit / permit / deny`, marker counts are `1 / 1 / 0`, the denied track has
no upstream host, every artifact hash passes, and teardown leaves no recorded
container running. This proves a local Envoy boundary only; Kind and
NetworkPolicy remain V3B-2.

- [ ] **Step 6: Record evidence boundaries and commit Task 6**

Update `docs/lab/V3-PROGRESS.md` and the README with the run ID, implementation
commit, tool/image identities, checksum result, exact joined outcome, and the
statement that V3B-1 does not validate Kind, NetworkPolicy, the historical
incident, or production performance.

```bash
git add tools/v3b1_local_envoy.py tests/test_v3b1_local_envoy.py docs/lab/V3-PROGRESS.md README.md
git commit -m "Validate the local Envoy enforcement boundary"
```

## V3B-1 exit criteria and V3B-2 gate

V3B-1 exits only when:

1. all repository and new contract tests pass;
2. downloaded tools and all executed images have recorded content identities;
3. the same request facts traverse three infrastructure-fixed Envoy gateways;
4. the local-reduction denial joins a KIL deny, no Envoy upstream host, and no
   target marker;
5. no authority-expansion, secret-logging, duplicate-marker, or teardown
   invariant fails; and
6. every public artifact passes `SHA256SUMS` verification.

The next plan, V3B-2, may then create the exact `kil-v3-lab` Kind cluster with
the official digest-pinned 1.36.1 node image, vendored Calico 3.32.0 CNI,
three isolated namespaces, default-deny NetworkPolicy, localhost-only gateway
port forwards, the complete functional failure matrix, and target-isolation
probes. V3C remains thirty-repeat functional confirmation plus latency and
publication promotion.

## Primary release evidence

- [Kind 0.32.0 release and node digest](https://github.com/kubernetes-sigs/kind/releases/tag/v0.32.0)
- [Kubernetes 1.36.3 release](https://github.com/kubernetes/kubernetes/releases/tag/v1.36.3)
- [Envoy 1.39.0 release](https://github.com/envoyproxy/envoy/releases/tag/v1.39.0)
- [Envoy HTTP `ext_authz` filter semantics](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/ext_authz_filter.html)
- [Envoy v3 `ext_authz` API](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/http/ext_authz/v3/ext_authz.proto.html)
- [Calico 3.32.0 release](https://github.com/projectcalico/calico/releases/tag/v3.32.0)
- [Calico 3.32 Kubernetes compatibility](https://docs.tigera.io/calico/latest/getting-started/kubernetes/requirements)
- [Docker Apple-silicon static client index](https://download.docker.com/mac/static/stable/aarch64/)
- [Approved KIL V3 design](../specs/2026-08-29-v3-envoy-live-validation-design.md)

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
