"""Durable policy-before-workload evidence, never fabricated during recovery.

Normal application dispatch publishes this checkpoint under the journal lock.
Readers only revalidate historical raw evidence against its original context;
there is no observation callback or recovery producer in this module.
"""
import os
from pathlib import Path
import stat

from kil.v3b2_application_policy_stage import validate_application_policy_stage, _decode_raw
from kil.v3b2_contracts import V3B2Profile
from kil.v3b2_journal import (
    OwnedIdentity, _journal_append_lock, _private_location, _publish_observed_proof,
    load_journal, load_expected_context,
)
from kil.v3b2_manifests import WorkloadIdentity, render_objects
from kil.v3b2_proofs import ExpectedContext, canonical, decode

_MAX_BYTES = 3 * 1024 * 1024
_SCHEMA = "kil.v3b2-policy-stage-checkpoint.v1"


class PolicyStageCheckpointError(ValueError):
    pass


def _context(context):
    if type(context) is not ExpectedContext:
        raise PolicyStageCheckpointError("checkpoint requires an exact expected context")
    context.__post_init__()
    if context.family != "application_apply":
        raise PolicyStageCheckpointError("checkpoint requires application_apply context")


def _proof(context, observations):
    _context(context)
    inputs = decode(context.inputs)
    profile = V3B2Profile.from_mapping(inputs["profile"])
    workload = WorkloadIdentity(**inputs["workload"])
    return validate_application_policy_stage(context=context,
        expected_context_commitment=context.commitment, profile=profile, workload=workload,
        rendered_objects=render_objects(profile, workload),
        owned_identity=OwnedIdentity(**inputs["owned_identity"]), observations=observations)


def encode_policy_stage_checkpoint(context, observations):
    proof = _proof(context, observations)
    payload = canonical({"schema": _SCHEMA, "run_id": context.run_id,
        "intent_sequence": context.intent_sequence, "context_commitment": context.commitment,
        "observations": decode(proof.raw_observations)})
    if len(payload) > _MAX_BYTES:
        raise PolicyStageCheckpointError("checkpoint exceeds retained byte bound")
    return payload


def decode_policy_stage_checkpoint(payload, context):
    _context(context)
    document = decode(payload, maximum=_MAX_BYTES)
    if (type(document) is not dict or set(document) != {
            "schema", "run_id", "intent_sequence", "context_commitment", "observations"}
            or canonical(document) != payload or document["schema"] != _SCHEMA
            or type(document["intent_sequence"]) is not int
            or document["intent_sequence"] != context.intent_sequence
            or document["run_id"] != context.run_id
            or document["context_commitment"] != context.commitment):
        raise PolicyStageCheckpointError("checkpoint does not bind the exact historical context")
    observations = _decode_raw(canonical(document["observations"]))
    return _proof(context, observations)


def publish_policy_stage_checkpoint(path: Path, context, observations):
    """Publish only while the original expected intent remains pending and live."""
    _context(context)
    with _journal_append_lock(path):
        value = load_journal(path)
        events = value["events"]
        if (value["teardown_from_sequence"] is not None or value["expected_inputs_sha256"] is None
                or value["run_id"] != context.run_id or not events
                or events[-1]["sequence"] != context.intent_sequence
                or events[-1]["event"] != "application_apply_intent"
                or events[-1]["details"] != decode(context.intent)
                or load_expected_context(path, value) != context):
            raise PolicyStageCheckpointError("checkpoint context is stale, unbound, or teardown-only")
        payload = encode_policy_stage_checkpoint(context, observations)
        proof = decode_policy_stage_checkpoint(payload, context)
        _, private = _private_location(path, create_parent=False)
        _publish_observed_proof(private, f"policy-stage-{context.intent_sequence}.json", payload)
        return proof


def read_policy_stage_checkpoint_bytes(path: Path, context):
    """Strictly read and revalidate the exact durable checkpoint bytes."""
    _context(context)
    _, private = _private_location(path, create_parent=False)
    name = f"policy-stage-{context.intent_sequence}.json"
    payload = _read_checkpoint_bytes(private, name, _MAX_BYTES, PolicyStageCheckpointError)
    decode_policy_stage_checkpoint(payload, context)
    return payload


def _read_checkpoint_bytes(private, name, maximum, error_type):
    """Read one bounded immutable private checkpoint with name/descriptor bracketing."""
    parent = os.open(private, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    descriptor = None
    try:
        anchor = os.fstat(parent)
        def verify_parent():
            opened = os.fstat(parent)
            named_parent = os.stat(private, follow_symlinks=False)
            if (not stat.S_ISDIR(opened.st_mode) or not stat.S_ISDIR(named_parent.st_mode)
                    or stat.S_IMODE(opened.st_mode) != 0o700
                    or stat.S_IMODE(named_parent.st_mode) != 0o700
                    or opened.st_uid != os.geteuid() or named_parent.st_uid != os.geteuid()
                    or any(getattr(anchor, key) != getattr(opened, key)
                           or getattr(anchor, key) != getattr(named_parent, key)
                           for key in ("st_dev", "st_ino", "st_mode", "st_uid"))):
                raise error_type("checkpoint parent identity or permissions changed")
        verify_parent()
        descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        before = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= maximum
                or before.st_nlink != 1 or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)):
            raise error_type("checkpoint must be an owned bounded private single-link file")
        chunks, length = [], 0
        while length <= maximum:
            chunk = os.read(descriptor, min(65536, maximum + 1 - length))
            if not chunk: break
            chunks.append(chunk); length += len(chunk)
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        attributes = ("st_dev", "st_ino", "st_size", "st_mode", "st_nlink", "st_uid", "st_mtime_ns", "st_ctime_ns")
        if length != before.st_size or any(getattr(before, key) != getattr(after, key)
                or getattr(before, key) != getattr(current, key) for key in attributes):
            raise error_type("checkpoint changed during read")
        verify_parent()
        payload = b"".join(chunks)
        return payload
    finally:
        if descriptor is not None: os.close(descriptor)
        os.close(parent)


def read_policy_stage_checkpoint(path: Path, context):
    """Strict bounded private read; missing/corrupt evidence is never regenerated."""
    return decode_policy_stage_checkpoint(read_policy_stage_checkpoint_bytes(path, context), context)
