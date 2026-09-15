"""Durable private checkpoint for the V4 control-plane manifest source."""
from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import secrets
import stat

from kil.v3b2_control_plane_manifest_source import (
    MAX_SOURCE_RECORD_BYTES,
    ControlPlaneManifestBinding,
    ControlPlaneManifestSourceError,
    ControlPlaneManifestSourceProof,
)
from kil.v3b2_proofs import ExpectedContext, canonical, decode


_SCHEMA = "kil.v4.control-plane-manifest-source.v1"
_CONTEXT_FIELDS = {"run_id", "intent_sequence", "family", "intent", "inputs"}
_PROOF_FIELDS = {
    "run_id", "cluster_uid", "node_container_id", "node_config_id",
    "raw_observations", "bindings", "runtime_complete", "application_complete",
}
_BINDING_FIELDS = {"component", "path", "byte_count", "sha256", "semantic_sha256"}


class ControlPlaneManifestSourceRecordError(ValueError):
    """The retained source record is unsafe, malformed, or context-free."""


def _context_document(context: ExpectedContext) -> dict[str, object]:
    if type(context) is not ExpectedContext:
        raise ControlPlaneManifestSourceRecordError(
            "source record requires an exact expected context")
    try:
        context.__post_init__()
        if context.family != "control_plane_manifest_source":
            raise ControlPlaneManifestSourceRecordError(
                "source record context family is invalid")
        return {
            "run_id": context.run_id,
            "intent_sequence": context.intent_sequence,
            "family": context.family,
            "intent": decode(context.intent),
            "inputs": decode(context.inputs),
        }
    except ControlPlaneManifestSourceRecordError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, UnicodeError,
            RecursionError) as error:
        raise ControlPlaneManifestSourceRecordError(
            "source record context is malformed") from error


def _proof_document(proof: ControlPlaneManifestSourceProof) -> dict[str, object]:
    if type(proof) is not ControlPlaneManifestSourceProof:
        raise ControlPlaneManifestSourceRecordError(
            "source record requires an exact manifest source proof")
    try:
        proof.__post_init__()
        return {
            "run_id": proof.run_id,
            "cluster_uid": proof.cluster_uid,
            "node_container_id": proof.node_container_id,
            "node_config_id": proof.node_config_id,
            "raw_observations": [decode(row, maximum=MAX_SOURCE_RECORD_BYTES)
                                 for row in proof.raw_observations],
            "bindings": [asdict(binding) for binding in proof.bindings],
            "runtime_complete": proof.runtime_complete,
            "application_complete": proof.application_complete,
        }
    except ControlPlaneManifestSourceRecordError:
        raise
    except (ControlPlaneManifestSourceError, TypeError, ValueError, KeyError,
            AttributeError, UnicodeError, RecursionError) as error:
        raise ControlPlaneManifestSourceRecordError(
            "manifest source proof does not revalidate") from error


def _require_context_binding(proof_document: dict[str, object],
                             expected: dict[str, object]) -> None:
    raw = proof_document.get("raw_observations")
    if type(raw) is not list or not raw or type(raw[0]) is not dict:
        raise ControlPlaneManifestSourceRecordError(
            "manifest source proof lacks retained context authority")
    retained = raw[0].get("expected_context")
    if retained != expected or canonical(retained) != canonical(expected):
        raise ControlPlaneManifestSourceRecordError(
            "manifest source proof differs from the exact expected context")


def encode_control_plane_manifest_source_record(*, proof, context) -> bytes:
    """Encode one canonical, closed source checkpoint."""
    expected = _context_document(context)
    encoded_proof = _proof_document(proof)
    _require_context_binding(encoded_proof, expected)
    payload = canonical({"schema": _SCHEMA, "context": expected,
                         "proof": encoded_proof})
    if len(payload) > MAX_SOURCE_RECORD_BYTES:
        raise ControlPlaneManifestSourceRecordError(
            "manifest source record exceeds its four MiB byte bound")
    return payload


def _decode_record(payload: bytes, context: ExpectedContext
                   ) -> ControlPlaneManifestSourceProof:
    expected = _context_document(context)
    if type(payload) is not bytes or not payload or len(payload) > MAX_SOURCE_RECORD_BYTES:
        raise ControlPlaneManifestSourceRecordError(
            "manifest source record exceeds its bounded byte range")
    try:
        document = decode(payload, maximum=MAX_SOURCE_RECORD_BYTES)
        if (type(document) is not dict
                or set(document) != {"schema", "context", "proof"}
                or canonical(document) != payload or document["schema"] != _SCHEMA):
            raise ControlPlaneManifestSourceRecordError(
                "manifest source record envelope is not canonical and closed")
        retained_context = document["context"]
        if (type(retained_context) is not dict
                or set(retained_context) != _CONTEXT_FIELDS
                or retained_context != expected
                or canonical(retained_context) != canonical(expected)):
            raise ControlPlaneManifestSourceRecordError(
                "manifest source record does not bind the exact expected context")
        retained_proof = document["proof"]
        if type(retained_proof) is not dict or set(retained_proof) != _PROOF_FIELDS:
            raise ControlPlaneManifestSourceRecordError(
                "manifest source proof fields are not closed")
        raw = retained_proof["raw_observations"]
        bindings = retained_proof["bindings"]
        if (type(raw) is not list or type(bindings) is not list
                or any(type(row) is not dict for row in raw)
                or any(type(row) is not dict or set(row) != _BINDING_FIELDS
                       for row in bindings)):
            raise ControlPlaneManifestSourceRecordError(
                "manifest source nested records are not closed")
        reconstructed = ControlPlaneManifestSourceProof(
            retained_proof["run_id"], retained_proof["cluster_uid"],
            retained_proof["node_container_id"], retained_proof["node_config_id"],
            tuple(canonical(row) for row in raw),
            tuple(ControlPlaneManifestBinding(**row) for row in bindings),
            retained_proof["runtime_complete"],
            retained_proof["application_complete"],
        )
        reconstructed.__post_init__()
        encoded_proof = _proof_document(reconstructed)
        _require_context_binding(encoded_proof, expected)
        if retained_proof != encoded_proof:
            raise ControlPlaneManifestSourceRecordError(
                "manifest source proof differs from reconstruction")
        return reconstructed
    except ControlPlaneManifestSourceRecordError:
        raise
    except (ControlPlaneManifestSourceError, TypeError, ValueError, KeyError,
            AttributeError, UnicodeError, RecursionError) as error:
        raise ControlPlaneManifestSourceRecordError(
            "manifest source record is malformed") from error


def _checkpoint_name(path: Path, context: ExpectedContext) -> tuple[Path, str]:
    if not isinstance(path, Path):
        raise ControlPlaneManifestSourceRecordError(
            "manifest source checkpoint path must be a Path")
    expected_name = f"control-plane-manifest-source-{context.intent_sequence}.json"
    if (not path.is_absolute() or ".." in path.parts or str(path) != str(Path(path))
            or path.name != expected_name):
        raise ControlPlaneManifestSourceRecordError(
            "manifest source checkpoint path is not deterministic")
    return path.parent, expected_name


def _open_parent(path: Path) -> tuple[int, os.stat_result]:
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        descriptor = os.open(path, flags)
        anchor = os.fstat(descriptor)
        named = os.stat(path, follow_symlinks=False)
        if (not stat.S_ISDIR(anchor.st_mode) or not stat.S_ISDIR(named.st_mode)
                or stat.S_IMODE(anchor.st_mode) != 0o700
                or stat.S_IMODE(named.st_mode) != 0o700
                or anchor.st_uid != os.geteuid() or named.st_uid != os.geteuid()
                or (anchor.st_dev, anchor.st_ino) != (named.st_dev, named.st_ino)):
            raise ControlPlaneManifestSourceRecordError(
                "checkpoint parent must be one owned private directory")
        return descriptor, anchor
    except ControlPlaneManifestSourceRecordError:
        try:
            os.close(descriptor)
        except (NameError, OSError):
            pass
        raise
    except OSError as error:
        raise ControlPlaneManifestSourceRecordError(
            "checkpoint parent cannot be opened safely") from error


def _verify_parent(parent: int, path: Path, anchor: os.stat_result) -> None:
    try:
        opened = os.fstat(parent)
        named = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise ControlPlaneManifestSourceRecordError(
            "checkpoint parent identity changed") from error
    keys = ("st_dev", "st_ino", "st_mode", "st_uid")
    if (not stat.S_ISDIR(opened.st_mode) or not stat.S_ISDIR(named.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o700
            or stat.S_IMODE(named.st_mode) != 0o700
            or opened.st_uid != os.geteuid() or named.st_uid != os.geteuid()
            or any(getattr(opened, key) != getattr(anchor, key)
                   or getattr(named, key) != getattr(anchor, key) for key in keys)):
        raise ControlPlaneManifestSourceRecordError(
            "checkpoint parent identity or permissions changed")


def _read_named(parent: int, name: str, payload: bytes | None = None,
                *, durable: bool = False) -> bytes:
    flags = (os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        descriptor = os.open(name, flags, dir_fd=parent)
    except OSError as error:
        raise ControlPlaneManifestSourceRecordError(
            "checkpoint is missing or cannot be opened safely") from error
    try:
        before = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_SOURCE_RECORD_BYTES
                or before.st_nlink != 1 or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)):
            raise ControlPlaneManifestSourceRecordError(
                "checkpoint must be an owned bounded 0600 single-link regular file")
        chunks: list[bytes] = []
        length = 0
        while length <= MAX_SOURCE_RECORD_BYTES:
            chunk = os.read(descriptor, min(65536,
                MAX_SOURCE_RECORD_BYTES + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        keys = ("st_dev", "st_ino", "st_size", "st_mode", "st_nlink", "st_uid",
                "st_mtime_ns", "st_ctime_ns")
        if (length != before.st_size or any(
                getattr(before, key) != getattr(after, key)
                or getattr(before, key) != getattr(current, key) for key in keys)):
            raise ControlPlaneManifestSourceRecordError(
                "checkpoint identity changed during read")
        result = b"".join(chunks)
        if payload is not None and result != payload:
            raise ControlPlaneManifestSourceRecordError(
                "existing checkpoint differs from canonical source bytes")
        if durable:
            os.fsync(descriptor)
        return result
    except ControlPlaneManifestSourceRecordError:
        raise
    except OSError as error:
        raise ControlPlaneManifestSourceRecordError(
            "checkpoint cannot be read safely") from error
    finally:
        os.close(descriptor)


def publish_control_plane_manifest_source_record(*, path, proof, context) -> bytes:
    """Publish exact bytes once; an existing target must be byte-identical."""
    payload = encode_control_plane_manifest_source_record(
        proof=proof, context=context)
    private, name = _checkpoint_name(path, context)
    parent, anchor = _open_parent(private)
    temporary: str | None = None
    staged_identity: tuple[int, int] | None = None
    descriptor: int | None = None
    try:
        _verify_parent(parent, private, anchor)
        try:
            os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            temporary = f".{name}.{secrets.token_hex(16)}.tmp"
            flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
            descriptor = os.open(temporary, flags, 0o600, dir_fd=parent)
            os.fchmod(descriptor, 0o600)
            staged = os.fstat(descriptor)
            staged_identity = (staged.st_dev, staged.st_ino)
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise ControlPlaneManifestSourceRecordError(
                        "checkpoint staging write was incomplete")
                offset += written
            os.fsync(descriptor)
            current = os.stat(temporary, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                    or current.st_uid != os.geteuid()
                    or stat.S_IMODE(current.st_mode) != 0o600
                    or current.st_size != len(payload)
                    or (current.st_dev, current.st_ino) != staged_identity):
                raise ControlPlaneManifestSourceRecordError(
                    "checkpoint staging identity changed")
            _verify_parent(parent, private, anchor)
            from kil.v3b2_evidence import _rename_directory_exclusive
            try:
                _rename_directory_exclusive(parent, temporary, parent, name)
            except FileExistsError:
                pass
            else:
                temporary = None
        _verify_parent(parent, private, anchor)
        _read_named(parent, name, payload, durable=True)
        _verify_parent(parent, private, anchor)
        os.fsync(parent)
        _verify_parent(parent, private, anchor)
        return payload
    except ControlPlaneManifestSourceRecordError:
        raise
    except OSError as error:
        raise ControlPlaneManifestSourceRecordError(
            "checkpoint publication failed safely") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None and staged_identity is not None:
            try:
                current = os.stat(temporary, dir_fd=parent,
                                  follow_symlinks=False)
                if (current.st_dev, current.st_ino) == staged_identity:
                    os.unlink(temporary, dir_fd=parent)
            except OSError:
                pass
        os.close(parent)


def read_control_plane_manifest_source_record(*, path, context):
    """Read only the deterministic retained checkpoint and revalidate it."""
    private, name = _checkpoint_name(path, context)
    parent, anchor = _open_parent(private)
    try:
        _verify_parent(parent, private, anchor)
        payload = _read_named(parent, name)
        _verify_parent(parent, private, anchor)
    finally:
        os.close(parent)
    return _decode_record(payload, context)


__all__ = (
    "ControlPlaneManifestSourceRecordError",
    "encode_control_plane_manifest_source_record",
    "publish_control_plane_manifest_source_record",
    "read_control_plane_manifest_source_record",
)
