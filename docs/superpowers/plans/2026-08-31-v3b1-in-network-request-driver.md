# V3B-1 In-Network Request Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the failed host-published V3B-1 client path with three one-shot request drivers inside split internal track networks, then produce one request-free readiness proof and one accepted local-Envoy enforcement demonstration.

**Architecture:** Add a shared closed driver-protocol module, a container-side one-shot executable, and a host-side interactive-process adapter. Each track receives a driver/Envoy frontend and an Envoy/authz/target backend; Envoy is the only dual-homed component, has no host publication, and remains the enforcement boundary. New schema versions bind non-circular driver definitions and exact public driver results while legacy bundles remain verified by their original schema.

**Tech Stack:** Python 3.12.13, `unittest`, canonical JSON/JSONL, `http.client`, `subprocess`, Docker CLI 29.7.2, Colima 0.10.3, Envoy 1.39.1, Ed25519 compact JWS, SHA-256, SVG/HTML/Markdown, GitHub Actions and GitHub CLI.

---

## Execution constraints

- Work only on a `codex/` feature branch in an isolated Git worktree.
- Follow RED -> GREEN -> REFACTOR for every production behavior change.
- Do not alter KIL decay, Q-state verification, authorization, Envoy policy, or
  target semantics.
- Do not start Docker/Colima during Tasks 1-9; those tasks are static only.
- Do not issue a consequential request until the request-free live gate passes
  from merged public main.
- After request intent, never restart, reconnect, replace, or retry a driver.
- Preserve ignored private journals and failed bundles; never force-add them.
- Append every substantive checkpoint to
  `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`.

## File structure

**Create:**

- `src/kil/v3b1_driver_protocol.py` — shared closed driver definition,
  instruction, readiness, result, failure, canonicalization, and secret rules.
- `src/kil/v3b1_request_driver.py` — image-resident one-shot retained-connection
  executable.
- `tools/v3b1_driver_transport.py` — host-side attached Docker-process protocol,
  deadlines, stdin/stdout framing, cancellation, and process-result handling.
- `tests/test_v3b1_request_driver.py` — pure protocol and container executable
  tests.
- `tests/fixtures/v3b1-request-driver-protocol.json` — sanitized closed protocol
  transcript.
- `tests/fixtures/v3b1-public-bundle-v1/` — deterministic legacy public-bundle
  fixture captured before writer migration.

**Modify implementation/contracts:**

- `tools/v3b1_local_envoy.py`
- `tools/v3b1_harness_contract.py`
- `tests/test_v3b1_local_envoy.py`
- `tests/fixtures/v3b1-integration-contract.json`
- `deploy/kind/Dockerfile.v3b`
- `deploy/kind/Dockerfile.v3b.dockerignore`
- `deploy/kind/v3b-profile.json`
- `src/kil/v3b_preflight.py`
- `tests/test_v3b_preflight.py`
- `tests/test_v3b_container_contract.py`
- `tests/test_v3b_tool_bootstrap.py`

**Modify documentation/publication:**

- `README.md`
- `tools/README.md`
- `adapters/envoy/README.md`
- `docs/lab/V3-PROGRESS.md`
- `docs/paper/kinetic-infrastructure.md`
- `docs/architecture/v3-envoy-live-validation.svg`
- `docs/design-drafts/hybrid-two-timescale-architecture.html`
- `docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`
- `docs/superpowers/plans/2026-08-30-v3b1-integration-contract.md`
- `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- ignored live board `artifacts/generated/v3b1-task6-live-status.md`

Do not modify `src/kil/run_bundle.py` or its modeled-replay tests; they are a
separate V3A artifact path.

### Task 1: Freeze legacy verification and add closed driver protocol contracts

**Files:**

- Create: `src/kil/v3b1_driver_protocol.py`
- Create: `tests/test_v3b1_request_driver.py`
- Create: `tests/fixtures/v3b1-request-driver-protocol.json`
- Create: `tests/fixtures/v3b1-public-bundle-v1/`
- Modify: `tools/v3b1_harness_contract.py`
- Modify: `tests/test_v3b1_local_envoy.py`

- [x] **Step 1: Freeze one deterministic legacy bundle before changing writers**

Use the existing `published_presenter_bundle()` test helper to materialize the
current complete `kil.v3b1-public-manifest.v1` file set under
`tests/fixtures/v3b1-public-bundle-v1/`. Add a test that copies the fixture to a
temporary directory and requires `verify_presenter_bundle()` to accept it.
Label its request facts as a deterministic synthetic compatibility fixture; do
not call it a historical or live run.

- [x] **Step 2: Write RED tests for non-circular definitions and closed records**

Add tests with these exact public APIs:

```python
from kil.v3b1_driver_protocol import (
    DriverProtocolError,
    canonical_record,
    driver_definition,
    parse_instruction,
    parse_result,
)

definition = driver_definition(
    track="signed_state_only",
    image_id="sha256:" + "1" * 64,
    bootstrap_sha256="2" * 64,
    frontend_segment_sha256="3" * 64,
)
self.assertEqual(definition["endpoint"], {"host": "envoy", "port": 8080})
self.assertNotIn("container_name", definition)
self.assertNotIn("run_id", definition)
self.assertEqual(
    canonical_record(definition), canonical_record(dict(reversed(list(definition.items()))))
)
```

Require duplicate keys, noncanonical bytes, unknown fields, invalid track,
unexpected endpoint, oversized input, authorization/Q-state fields in public
records, compact JWS values, environment material, paths, tokens, and exception
messages to fail with `DriverProtocolError`.

- [x] **Step 3: Run the focused tests and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_v3b1_request_driver -v
```

Expected: FAIL because `kil.v3b1_driver_protocol` does not exist.

- [x] **Step 4: Implement the minimal closed protocol**

Define fixed constants and closed validators:

```python
TRACKS = (
    "credential_policy_baseline",
    "signed_state_only",
    "signed_plus_local_reduce",
)
DRIVER_ENDPOINT = {"host": "envoy", "port": 8080}
MAX_INSTRUCTION_BYTES = 32 * 1024
MAX_RESULT_BYTES = 8 * 1024
MAX_RESPONSE_BODY_BYTES = 4096
DRIVER_RUNTIME_POLICY = {
    "user": "65532:65532",
    "read_only": True,
    "no_new_privileges": True,
    "cap_drop": ["ALL"],
    "nano_cpus": 500_000_000,
    "memory": 268_435_456,
    "memory_swap": 268_435_456,
    "pids_limit": 128,
    "restart": "no",
    "stop_timeout": 10,
    "log_driver": "json-file",
    "log_options": {"max-file": "1", "max-size": "1m"},
    "tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=16m,uid=65532,gid=65532,mode=0700"},
    "stdin_open": True,
    "tty": False,
    "healthcheck": "disabled",
    "mounts": [],
    "ports": {},
}

class DriverProtocolError(ValueError):
    pass

def require_track(value: object) -> str:
    if type(value) is not str or value not in TRACKS:
        raise DriverProtocolError("driver track is invalid")
    return value

def require_sha256(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise DriverProtocolError("driver SHA-256 is invalid")
    return value

def require_image_id(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"sha256:[a-f0-9]{64}", value) is None:
        raise DriverProtocolError("driver image ID is invalid")
    return value

def canonical_record(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")

def driver_definition(*, track: str, image_id: str,
                      bootstrap_sha256: str,
                      frontend_segment_sha256: str) -> dict[str, object]:
    value = {
        "schema_version": "kil.v3b1-driver-definition.v1",
        "role": "request_driver",
        "track": require_track(track),
        "image_id": require_image_id(image_id),
        "bootstrap_sha256": require_sha256(bootstrap_sha256),
        "frontend_segment_sha256": require_sha256(frontend_segment_sha256),
        "endpoint": dict(DRIVER_ENDPOINT),
        "runtime_policy": DRIVER_RUNTIME_POLICY,
    }
    reject_sensitive_material(value)
    return value
```

Use one duplicate-key rejecting JSON loader and exact field sets for readiness,
instruction, success result, transport-failure result, and driver-control
failure. Public-safe records must be recursively secret-scanned.

- [x] **Step 5: Make harness inventory contracts recognize the new fixed names**

Extend container roles to `authz|target|envoy|driver|validate` and network names
to `frontend|backend`. Add sanitized inventory cases to both fixtures. Keep the
legacy v1 patterns available only through explicit schema dispatch.

- [x] **Step 6: Verify GREEN and commit**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_v3b1_request_driver -v
PYTHONPATH=src .venv/bin/python -m unittest tests.test_v3b1_local_envoy.EvidenceBundleTest -v
PYTHONPATH=src .venv/bin/python -m py_compile src/kil/v3b1_driver_protocol.py tools/v3b1_harness_contract.py
git diff --check
```

Expected: all selected tests PASS and the frozen v1 fixture still verifies.

Commit:

```bash
git add src/kil/v3b1_driver_protocol.py tests/test_v3b1_request_driver.py \
  tests/fixtures/v3b1-request-driver-protocol.json \
  tests/fixtures/v3b1-public-bundle-v1 tools/v3b1_harness_contract.py \
  tests/fixtures/v3b1-integration-contract.json tests/test_v3b1_local_envoy.py
git commit -m "Lock the V3B-1 request driver protocol"
```

### Task 2: Implement the one-shot container-side driver

**Files:**

- Create: `src/kil/v3b1_request_driver.py`
- Modify: `tests/test_v3b1_request_driver.py`
- Modify: `deploy/kind/Dockerfile.v3b`
- Modify: `deploy/kind/Dockerfile.v3b.dockerignore`
- Modify: `tools/v3b1_local_envoy.py`
- Modify: `tests/test_v3b_container_contract.py`

- [x] **Step 1: Write RED executable tests with an injected connection**

Test this exact callable boundary:

```python
exit_code = execute_driver(
    track="signed_state_only",
    stdin=instruction_stream,
    stdout=output_stream,
    connection_factory=fake_connection_factory,
    monotonic_ns=fake_clock,
)
```

Require:

- one canonical readiness line before the first stdin read;
- EOF after readiness returns zero, sends no HTTP bytes, and emits no more
  stdout;
- one valid instruction reuses the retained connection exactly once;
- the response body is read at `MAX_RESPONSE_BODY_BYTES + 1`, never echoed, and
  oversize is terminal;
- duplicate, unknown, trailing, noncanonical, wrong-track, wrong-path,
  wrong-method, nonempty-body, or unapproved-header input sends nothing;
- success emits one canonical secret-free result;
- request-send, response-header, and response-body failures emit one closed
  failure result without raw exception text; and
- no path reconnects or retries.

- [x] **Step 2: Run each new test and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_v3b1_request_driver.RequestDriverTest -v
```

Expected: FAIL because `kil.v3b1_request_driver.execute_driver` is unavailable.

- [x] **Step 3: Implement the retained-connection state machine**

Implement only:

```python
def execute_driver(*, track: str, stdin: BinaryIO, stdout: BinaryIO,
                   connection_factory: Callable[..., object] = HTTPConnection,
                   monotonic_ns: Callable[[], int] = time.monotonic_ns) -> int:
    connection = connection_factory("envoy", 8080, timeout=2.0)
    connection.connect()
    stdout.write(canonical_record(readiness_record(track, monotonic_ns())))
    stdout.flush()
    raw = read_bounded_single_line(stdin, MAX_INSTRUCTION_BYTES)
    if raw is None:
        connection.close()
        return 0
    instruction = parse_instruction(raw, expected_track=track)
    result = perform_one_request(connection, instruction, monotonic_ns)
    stdout.write(canonical_record(result))
    stdout.flush()
    connection.close()
    return 0 if result["status"] == "complete" else 1
```

In the same module, define `read_bounded_single_line()` to read at most
`limit + 1` bytes and reject missing newline/trailing bytes; define
`readiness_record()` as the exact readiness schema constructor; and define
`perform_one_request()` as the only function allowed to call `request()`,
`getresponse()`, and bounded `read()`. These helpers return only records parsed
by the Task 1 protocol validators.

`main()` accepts only `--track` and fixed `--endpoint envoy:8080`, then calls
`execute_driver()` with binary standard streams. It must never log to stderr.

- [x] **Step 4: Include and attest the module in the immutable image**

Add `src/kil/v3b1_driver_protocol.py` and `src/kil/v3b1_request_driver.py` to
the Docker build copy and dockerignore allowlist, `_BUILD_CONTEXT_FILES`, and
container-contract tests. The bootstrap digest is the SHA-256 of the exact
driver module bytes included in the build context.

- [x] **Step 5: Verify GREEN and commit**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_v3b1_request_driver -v
PYTHONPATH=src .venv/bin/python -m unittest tests.test_v3b_container_contract -v
PYTHONPATH=src .venv/bin/python -m py_compile src/kil/v3b1_driver_protocol.py src/kil/v3b1_request_driver.py
git diff --check
```

Commit:

```bash
git add src/kil/v3b1_request_driver.py tests/test_v3b1_request_driver.py \
  deploy/kind/Dockerfile.v3b deploy/kind/Dockerfile.v3b.dockerignore \
  tools/v3b1_local_envoy.py tests/test_v3b_container_contract.py
git commit -m "Add the one-shot V3B-1 request driver"
```

### Task 3: Advance profile, content identity, manifest, and active-state schemas

**Files:**

- Modify: `deploy/kind/v3b-profile.json`
- Modify: `src/kil/v3b_preflight.py`
- Modify: `tests/test_v3b_preflight.py`
- Modify: `tools/v3b1_local_envoy.py`
- Modify: `tests/test_v3b1_local_envoy.py`

- [x] **Step 1: Write RED profile and identity tests**

Require `kil.v3b-profile.v2` to contain no `gateway_ports`. Require:

```python
self.assertEqual(manifest["schema_version"], "kil.v3b1-manifest.v2")
self.assertEqual(
    manifest["content_identity"]["schema_version"],
    "kil.v3b1-content-identity.v3",
)
self.assertEqual(len(manifest["segment_definitions"]), 6)
self.assertEqual(len(manifest["driver_definitions"]), 3)
```

Change only runtime names, labels, and full IDs in test data and assert the
content-identity digest is unchanged. Add hybrid-schema rejection tests: v1 may
not contain driver fields and v2/v3 may not omit them.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_v3b_preflight -v
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_v3b1_local_envoy.ControllerContractTest -v
```

Expected: FAIL on the old profile, gateway-port tracks, and old schema IDs.

- [x] **Step 3: Implement acyclic definitions and schema dispatch**

Use name-independent definitions:

```python
segment = {
    "schema_version": "kil.v3b1-segment-definition.v1",
    "track": track.value,
    "segment": segment_name,
    "internal": True,
}
endpoint = {"transport": "tcp", "host": "envoy", "port": 8080}
```

The content preimage contains six segment definitions and three driver
definition hashes. The private manifest derives network/container names only
after the content identity and run ID exist. Add explicit validators for old
and new schema versions; never accept a permissive union.

Advance active state, lifecycle journal, readiness poison, request, join,
public manifest, public commitment, and authoritative bundle schemas only where
new fields are required. Preserve v1 verifier functions unchanged behind
dispatch.

- [x] **Step 4: Verify GREEN and commit**

Run the two focused suites, compilation, and `git diff --check`.

Commit:

```bash
git add deploy/kind/v3b-profile.json src/kil/v3b_preflight.py \
  tests/test_v3b_preflight.py tools/v3b1_local_envoy.py \
  tests/test_v3b1_local_envoy.py
git commit -m "Define the V3B-1 driver content identity"
```

### Task 4: Build and attest the split internal runtime topology

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Modify: `tools/v3b1_harness_contract.py`
- Modify: `tests/test_v3b1_local_envoy.py`

- [x] **Step 1: Write RED command and attestation tests**

Add exact tests requiring:

- six `--internal` bridge creations;
- three authz, three target, and three Envoy running containers;
- three driver `docker create` commands with interactive stdin, no TTY,
  `--no-healthcheck`, no mount, no publication, and no backend network;
- Envoy attached to backend and frontend, with fixed frontend alias `envoy`;
- frontend configuration exactly `{driver, envoy}`, with physical membership
  containing only running roles: `{envoy}` for a created/exited/dead driver and
  `{driver, envoy}` only while the driver is running;
- nominal running backend membership exactly `{envoy, authz, target}`, with
  stopped roles absent;
- driver state `created`; Envoy/authz/target states `running`;
- `HostConfig.PortBindings == {}` and live published ports empty/null; and
- no command contains `--publish`, `-p`, a host port, or a non-internal segment.

- [x] **Step 2: Verify RED**

Run the named topology and `RuntimeAttestationTest` cases. Expect failures on
three networks, nine objects, running-only inspection, and host publication.

- [x] **Step 3: Implement runtime commands and exact topology attestation**

Create all backend segments first, then frontend segments. Start services on
backend. Connect each Envoy to its frontend with one durable
`network_connect_intent` / `network_connect_complete` transition and alias
`envoy`. Create each driver stopped on frontend using its full immutable module
command.

Make `_inspect_container()` role- and phase-aware. Preserve per-network aliases
from `NetworkSettings.Networks`. Make `_inspect_network()` validate segment and
closed member-role sets. `up_complete` requires twelve persistent track objects,
three validators, six networks, and no host publication.

- [x] **Step 4: Update state, inventory, and pure teardown builders**

Advance full-ID state validation, object counts, fixed-name parsing,
`teardown_commands()`, and partial-up maxima to 15 containers and six networks.
Keep source-attestation cardinality at exactly nine enforcement sources.

- [x] **Step 5: Verify GREEN and commit**

Run `ControllerContractTest`, `RuntimeAttestationTest`, and teardown command
tests, then compilation and diff hygiene.

Commit:

```bash
git add tools/v3b1_local_envoy.py tools/v3b1_harness_contract.py \
  tests/test_v3b1_local_envoy.py
git commit -m "Build the isolated V3B-1 driver topology"
```

### Task 5: Add attached driver sessions and the readiness-only lifecycle

**Files:**

- Create: `tools/v3b1_driver_transport.py`
- Modify: `tools/v3b1_local_envoy.py`
- Modify: `tests/test_v3b1_local_envoy.py`
- Modify: `tests/fixtures/v3b1-integration-contract.json`

- [x] **Step 1: Write RED host-session tests**

Define an injected adapter:

```python
class DriverProcess(Protocol):
    stdin: BinaryIO
    stdout: BinaryIO
    def poll(self) -> int | None: ...
    def wait(self, timeout: float) -> int: ...

class DriverProcessFactory(Protocol):
    def start(self, command: Sequence[str]) -> DriverProcess: ...
```

Tests must prove all three processes start before the controller waits for any
single readiness line; all three closed readiness records are durable before
request intent; one common deadline applies; malformed/extra output, nonzero
exit, or ambiguous termination fails closed; and no stderr bytes reach the
journal.

- [x] **Step 2: Write RED readiness-only tests**

Require the new CLI command `readiness` to:

- start all three drivers once;
- receive all three readiness records;
- close all three stdin streams without an instruction;
- observe fixed zero exits and no later stdout;
- persist three `readiness_cancel_complete` records bound to full ID, track, and
  readiness nonce;
- leave all request states `not_attempted`; and
- mark the lifecycle diagnostic-only so `run` is prohibited before `down`.

- [x] **Step 3: Verify RED**

Run `DriverReadinessTest` and the CLI subcommand test. Expect import and missing
subcommand failures.

- [x] **Step 4: Implement the bounded attached-process adapter**

Use the exact command vector
`[docker_binary, "start", "--attach", "--interactive", driver_full_id]`
through `subprocess.Popen`
with binary pipes. Spawn all processes before reading. Read one bounded line per
driver under a common deadline. Expose only closed status/exit facts; discard
raw stderr after a bounded read and never persist it.

Replace socket readiness poison with driver-control/termination categories.
EOF cancellation is successful only when stdout is exhausted and exit status is
zero. Any ambiguity poisons readiness and prohibits `run`.

- [x] **Step 5: Verify GREEN and commit**

Run driver readiness, journal replay, CLI, compilation, and diff checks.

Commit:

```bash
git add tools/v3b1_driver_transport.py tools/v3b1_local_envoy.py \
  tests/test_v3b1_local_envoy.py tests/fixtures/v3b1-integration-contract.json
git commit -m "Add V3B-1 in-network driver readiness"
```

### Task 6: Replace direct host requests with one-shot driver instructions

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Modify: `tools/v3b1_driver_transport.py`
- Modify: `tests/test_v3b1_local_envoy.py`

- [x] **Step 1: Write RED sequencing tests**

Require this fixed ordering for each commanded track:

```text
all_driver_readiness_complete
q_state_issue_if_required
request_intent_persisted
driver_instruction_write_intent
one bounded instruction write
stdin close
one bounded result read
exact exit attestation
raw result persist
normalized request persist
request_attempt_complete
```

Assert that the authorization value and compact Q-state occur only in the
in-memory stdin payload after durable intent and never in commands, environment,
mounts, stdout/stderr, journals, or evidence. Track order remains credential
baseline, signed only, signed plus local reduction.

- [x] **Step 2: Write RED failure tests**

Test partial pipe write, broken stdin, invalid result, missing result, extra
stdout, nonzero exit, timeout, and driver transport failure. Once any
instruction byte may have been written, provenance must say
`request_bytes_may_have_been_sent=true`. The first post-intent failure EOF-
cancels every later driver, leaves later requests `not_attempted`, and enters
teardown without restart, reconnect, replacement, or retry.

- [x] **Step 3: Verify RED**

Run `DriverRequestSequencingTest`; expect the old host `HTTPConnection` path and
socket-specific helpers to violate the new assertions.

- [x] **Step 4: Implement one-shot instruction/result handling**

Remove `_connect_ready_gateways()`, `_reset_request_timeouts()`, and direct host
`HTTPConnection.request()` use. Issue Q-state only after aggregate readiness and
immediately before the bound instruction. Persist intent before calling
`write_instruction()`. Parse the exact closed driver result, validate the
decision digest/status, require exact process exit, and then construct
`kil.v3b1-request.v2`.

Controller-only failure provenance uses closed stages
`instruction_write|stdout_read|process_wait|termination`. It never stores raw
exception text.

- [x] **Step 5: Verify GREEN and commit**

Run driver sequencing, request journal, Q-state expiry, compilation, and diff
checks.

Commit:

```bash
git add tools/v3b1_local_envoy.py tools/v3b1_driver_transport.py \
  tests/test_v3b1_local_envoy.py
git commit -m "Route V3B-1 requests through one-shot drivers"
```

### Task 7: Bind exact driver results into v2 evidence and presenter output

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Modify: `tests/test_v3b1_local_envoy.py`

- [x] **Step 1: Write RED bundle and compatibility tests**

Require exactly:

```text
raw/drivers/credential_policy_baseline.json
raw/drivers/signed_state_only.json
raw/drivers/signed_plus_local_reduce.json
```

Each commanded file is the exact canonical, secret-free driver result with one
trailing newline. Its SHA-256 appears in the normalized request and
`SHA256SUMS`. The offline verifier must reconstruct the bytes, rehash them,
validate the normalized projection, and then join request, Envoy, authz, target,
run, track, request ID, and decision digest.

Require v1 bundles to reject driver files, v2 bundles to require them, and the
frozen v1 fixture to retain its original HTML bytes and acceptance behavior.

- [x] **Step 2: Write RED presenter tests**

The v2 presenter must visibly contain:

```text
request driver -> Envoy -> authorization -> target or withhold
No host publication
The driver is a laboratory transport witness, not KIL enforcement
Evidence scope: local_envoy_boundary
```

It must derive entirely from verified public records and keep the existing CSP,
escaping, no-script, and no-external-asset rules.

- [x] **Step 3: Verify RED**

Run `EvidenceBundleTest` and presenter tests. Expect the old authoritative file
set, v1-only validators, and old HTML model to fail.

- [x] **Step 4: Implement explicit v1/v2 writer and verifier dispatch**

Keep legacy expected file sets and validators separate. For v2, add the three
driver files to authoritative names, public snapshot, artifact hashes,
commitment, checksums, manifest, and presenter derivation. Empty files are
permitted only for uncommanded tracks in nonpromotable failure bundles; an
accepted bundle requires all three exact results.

- [x] **Step 5: Verify GREEN and commit**

Run all evidence/presenter tests, verify the frozen v1 fixture, compile, and
check the diff.

Commit:

```bash
git add tools/v3b1_local_envoy.py tests/test_v3b1_local_envoy.py
git commit -m "Bind V3B-1 driver results into public evidence"
```

### Task 8: Make recovery and teardown driver-aware

**Files:**

- Modify: `tools/v3b1_local_envoy.py`
- Modify: `tools/v3b1_harness_contract.py`
- Modify: `tests/test_v3b1_local_envoy.py`

- [x] **Step 1: Write RED partial-up and partial-run recovery tests**

Require partial `up` to remove a created-never-started driver only after exact
full-ID, image, command, labels, state, and network attestation. Once any
`driver_start_intent` exists, recovery must never start, attach, restart,
replace, or command that driver.

An intent without a trusted terminal result is ambiguous and nonpromotable;
cleanup must still continue against exact recorded IDs.

- [x] **Step 2: Write RED ordering and inventory tests**

Require every driver to be durably exited or exactly stopped and re-attested
before any Envoy stop. Preserve the existing nine-source freeze. Remove drivers,
Envoys, authz, targets, validators, and then six empty networks through durable
intents and full-ID survivor inventories. Final publication requires 15
containers and six networks absent.

- [x] **Step 3: Verify RED**

Run `JournalRecoveryTest`, `TeardownContinuationTest`, and teardown contract
tests. Expect old nine-container/three-network and running-driver assumptions to
fail.

- [x] **Step 4: Implement phase-aware revalidation and exact cleanup**

Make `_load_and_reverify()` accept created drivers before run and exited/stopped
drivers after readiness/run. Add driver-first finalization to `down()` and keep
source collection restricted to Envoy/authz/target. Update both
`teardown_commands()` and imperative teardown so they cannot diverge.

- [x] **Step 5: Verify GREEN and commit**

Run recovery, teardown, source-freeze, full controller tests, compilation, and
diff hygiene.

Commit:

```bash
git add tools/v3b1_local_envoy.py tools/v3b1_harness_contract.py \
  tests/test_v3b1_local_envoy.py
git commit -m "Recover and tear down V3B-1 request drivers"
```

### Task 9: Unify documentation, diagrams, lab status, and static verification

**Files:**

- Modify: `README.md`
- Modify: `tools/README.md`
- Modify: `adapters/envoy/README.md`
- Modify: `docs/lab/V3-PROGRESS.md`
- Modify: `docs/paper/kinetic-infrastructure.md`
- Modify: `docs/architecture/v3-envoy-live-validation.svg`
- Modify: `docs/design-drafts/hybrid-two-timescale-architecture.html`
- Create: `docs/architecture/hybrid-two-timescale-architecture.html`
- Modify: `docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md`
- Modify: `docs/superpowers/plans/2026-08-30-v3b1-integration-contract.md`
- Modify: `docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Create: `tests/test_v3b1_documentation.py`
- Modify: ignored `artifacts/generated/v3b1-task6-live-status.md`

- [x] **Step 1: Update only mechanism and pending-gate claims**

Show host Docker attach/stdin control separately from consequential traffic.
Show three tracks, each with frontend configured for `{driver, Envoy}` and
backend `{Envoy, authz, target}`; distinguish created-state physical
`{Envoy}` from materialized `{driver, Envoy}`. Show Envoy dual-homing, no host
publication, and evidence joins. The hybrid diagram must separate current local-Envoy V3B-1 from future
Kind/Calico V3B-2.

Before live acceptance, state only that the mechanism is implemented and the
readiness/central gates are pending. Do not claim validation, prevention,
performance, Kind, or NetworkPolicy results.

- [x] **Step 2: Add supersession notes without rewriting history**

The older specs/plans retain their execution records but link to the approved
driver correction. Append lineage; never rewrite older entries.

- [x] **Step 3: Run independent spec and quality review**

Review every requirement in design sections 4-11. Resolve every Critical or
Important issue test-first, then re-run spec review and quality/security review
until both approve.

- [x] **Step 4: Run the complete static gate**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_v3b1_request_driver -v
PYTHONPATH=src .venv/bin/python -m unittest tests.test_v3b_preflight tests.test_v3b_container_contract tests.test_v3b1_local_envoy -v
PYTHONPATH=src .venv/bin/python -m py_compile src/kil/v3b1_driver_protocol.py src/kil/v3b1_request_driver.py src/kil/v3b_preflight.py tools/v3b1_driver_transport.py tools/v3b1_harness_contract.py tools/v3b1_local_envoy.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
make validate PYTHON=.venv/bin/python
git diff --check
```

Expected: every test PASS, compilation succeeds, and no diff error is emitted.

- [x] **Step 5: Commit**

```bash
git add README.md tools/README.md adapters/envoy/README.md docs/lab/V3-PROGRESS.md \
  docs/paper/kinetic-infrastructure.md docs/architecture/v3-envoy-live-validation.svg \
  docs/architecture/hybrid-two-timescale-architecture.html \
  docs/design-drafts/hybrid-two-timescale-architecture.html \
  docs/superpowers/specs/2026-08-29-v3-envoy-live-validation-design.md \
  docs/superpowers/plans/2026-08-30-v3b1-integration-contract.md \
  docs/superpowers/plans/2026-08-31-v3b1-in-network-request-driver.md \
  docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md tests/test_v3b1_documentation.py
git commit -m "Document the V3B-1 request driver boundary"
```

### Task 10: Publish the correction and execute the request-free live gate

**Files:**

- Modify after the run: `docs/lab/V3-PROGRESS.md`
- Modify after the run: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Modify live: ignored `artifacts/generated/v3b1-task6-live-status.md`

- [x] **Step 1: Push the implementation PR and require CI**

Push the feature branch, create a PR, require both GitHub bootstrap jobs and the
local static gate to pass, resolve review findings, merge, fast-forward local
`main`, and verify local/remote/GitHub main commit equality and a clean tree.

PR #14 completed this step for the created-driver endpoint correction and
merged as `7677052f6fd2b4287f419dc01ec9a1a859191777`. The first merged-source
recovery stop exposed one additional engine representation: an exact service
stop collapses an unbound exposed-port map to `{}`. PR #15 closed that exact
role-bound transition and merged as
`3dce7cbd0153716b9e52cae791b97f50131989f7`. Its recovery then exposed Docker's
physical endpoint rule: a stopped container remains configured for its
networks but is absent from each network's `Containers` map. The current
state-derived membership correction must pass this same publish/CI/merge/
synchronize gate before bounded `down` resumes. The stopped container is owned
and journal-anchored; no request-side action occurred.

- [x] **Step 2: Record exact host state and run preflight**

Read and record all Colima profiles without mutating them. Use the pinned PATH:

```bash
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src .venv/bin/python tools/v3b1_local_envoy.py preflight
```

If a foreign profile must be paused, restore its exact prior status and
resources after the lifecycle.

- [x] **Step 3: Execute the request-free sequence visibly**

Update the ignored live board before every command, then run exactly:

```bash
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src .venv/bin/python tools/v3b1_local_envoy.py up
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src .venv/bin/python tools/v3b1_local_envoy.py readiness
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src .venv/bin/python tools/v3b1_local_envoy.py down
```

Do not invoke `run` in this lifecycle.

- [x] **Step 4: Verify the request-free gate**

Require all three readiness records, three durable cancellations, zero
instructions, zero request intents, zero HTTP actions, nine observed/copied
empty authoritative sources, valid nonpromotable checksums, twelve track and
three validator containers absent, six networks absent, dedicated profile
absent, no active state/poison/journal, and preservation of the bound foreign
context name plus a post-run resource tuple observation.

Task 10 passed with the request-side and teardown conditions above. The public
manifest durably binds the foreign context name as `default` before and after,
and a post-run operator readback observed the stopped resource tuple. The exact
resource tuple was not durably bound at both boundaries, so this execution does
not provide cryptographic proof of exact tuple restoration. A future lifecycle
must persist and bind both before- and after-resource snapshots to close that
evidence gap.

- [ ] **Step 5: Publish the public-safe gate record**

Append progress and lineage with exact run ID, source commit, checksum result,
and claim exclusions. Commit only public-safe references; keep the
nonpromotable bundle and private journal ignored. Push, review, merge, and
synchronize main before the central proof.

### Task 11: Execute and publish one accepted local-Envoy proof

**Files:**

- Force-add only the one exact accepted run directory selected and returned by
  the offline verifier.
- Modify: `README.md`
- Modify: `docs/lab/V3-PROGRESS.md`
- Modify: `docs/paper/kinetic-infrastructure.md`
- Modify: `docs/specialist/KIL-KTP-SPECIALIST-LINEAGE.md`
- Modify: ignored `artifacts/generated/v3b1-task6-live-status.md`

- [x] **Step 1: Reconfirm clean merged main and pass the fresh request-free v3 gate**

The historical Task 10 record remains v2 evidence. The foreign-resource
snapshot and pseudonymous verifier contract passed independent review, merge,
and synchronization at `5ebf21a88794a9f83a0e6c8ee53e76f6d8e5142d`.
The before- and after-resource snapshots are implemented, tested, and merged
under the private `kil.v3b1-manifest.v3` contract.
A clean worktree at that exact public-main commit executed
`preflight -> up -> readiness -> down` as request-free v3 run
`v3b1-4ac0b6eef70b0483f7883c8a26753d15a007f612953b25e23b8ecb6afd021a8f`.
It recorded three readiness completions, three clean cancellations, zero
instructions, zero request intents, zero HTTP requests, exact owned teardown,
and exactly equal pseudonymous foreign-resource arrays in
`kil.v3b1-public-manifest.v3`. All checksums and the internal nonpromotable
failure-bundle verifier passed. The completed private journal was archived;
the active state, active journal path, and readiness poison were absent after
teardown.

The central `run` remained prohibited until this public-safe checkpoint passed
independent review, public CI, merge, and exact synchronization. That
publication gate subsequently passed, authorizing one new clean lifecycle from
the synchronized correction source named below.

- [x] **Step 2: Invoke `run` once**

Run exactly one:

```bash
PATH="$PWD/.tools/bin:$PATH" PYTHONPATH=src .venv/bin/python tools/v3b1_local_envoy.py run
```

After request intent, do not retry under any circumstance. Whether accepted or
failed, execute `down` once and restore foreign state.

- [x] **Step 3: Verify the accepted proof before staging it**

Require:

- `permit / permit / deny`;
- HTTP `200 / 200 / 403`;
- target markers `1 / 1 / 0`;
- three exact canonical driver results;
- nine complete Envoy/authz/target sources;
- valid request/decision/target joins;
- complete exact teardown;
- an offline verifier proves exact equality of the durable before- and after-
  resource snapshots for every pre-existing foreign profile;
- all `SHA256SUMS` entries valid; and
- offline `view --bundle` acceptance.

- [x] **Step 4: Stage only the exact accepted bundle**

Resolve and validate the run ID from the verified manifest, then stage only its
explicit directory:

```bash
kil_verified_manifest="artifacts/generated/v3b1-local-envoy/$kil_verified_run_id/manifest.json"
test -f "$kil_verified_manifest"
test "$(jq -r .run_id "$kil_verified_manifest")" = "$kil_verified_run_id"
git add -f "artifacts/generated/v3b1-local-envoy/$kil_verified_run_id/"
git diff --cached --name-only
git diff --cached --check
```

`kil_verified_run_id` must be set to the exact run ID printed by the accepted
offline `view --bundle` result and must match `^v3b1-[a-f0-9]{64}$` before these
commands run.

Reject the staging set if it includes any sibling run, private journal,
downloaded tool, key, credential, or ignored parent directory.

- [x] **Step 5: Update the unified asset with calibrated claims**

The paper, README, presenter, progress, and lineage may name the exact run as an
accepted observed intermediate local-Envoy result. They must still exclude Kind
cluster validation, NetworkPolicy validation, historical prevention, and
production performance.

Correction source `514e910ea9427e0497c4fe8a1ec279b554e75176` produced accepted
run `v3b1-625262118e034d9c9b1df9c6e23bb54a78f01fe245a1b953d521b94884846e94`.
The live command was not retried after its post-request copy error; mandatory
teardown recovered and froze the complete authoritative evidence used by the
accepted offline bundle.

- [ ] **Step 6: Review, publish, merge, synchronize, and prepare backup**

Run the full static gate, bundle checksums, offline verifier, secret scan, spec
review, and quality/security review. Commit, push, pass CI, merge, and
fast-forward local main to exact public main. Leave the repo clean.

Do not create the offline backup until the user supplies its destination and
whether ignored private failed-run evidence should be included. Report phase
completion in the active Codex thread; external email requires an available
configured connector or automation and must not be claimed without one.

KTP citation: [canonical `CITATION.cff`](https://github.com/nmcitra/ktp-rfc/blob/main/CITATION.cff).
