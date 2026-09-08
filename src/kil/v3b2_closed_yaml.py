"""A bounded decoder for the closed YAML subset used by V3B-2 evidence."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, DecimalException

__all__ = ("ClosedYAMLError", "decode_closed_yaml")

_MAX_INPUT = 1024 * 1024
_MAX_NODES = 32_768
_MAX_DEPTH = 64
_MAX_LINES = 65_536
_MAX_SCALAR = 256 * 1024
_MAX_INTEGER_DIGITS = 5_000
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-/]*")
_INTEGER = re.compile(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)")
_NUMBERISH = re.compile(
    r"[+-]?(?:[0-9][0-9_]*)(?:\.[0-9_]*)?(?:[eE][+-]?[0-9_]+)?")
_RADIX = re.compile(r"[+-]?0[xXoObB][0-9A-Fa-f_]+")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[Tt ].*)?")
_LEADING_DOT_FLOAT = re.compile(r"[+-]?\.[0-9][0-9_]*(?:[eE][+-]?[0-9_]+)?")
_SEXAGESIMAL = re.compile(
    r"[+-]?[0-9][0-9_]*(?::[0-9][0-9_]*(?:\.[0-9_]*)?)+")
_PLAIN = re.compile(r"[A-Za-z0-9_./:@%+=,$~()?&*!\[\]-]+(?: [A-Za-z0-9_./:@%+=,$~()?&*!\[\]-]+)*")


class ClosedYAMLError(ValueError):
    """The supplied value is outside the bounded closed-YAML language."""


@dataclass(frozen=True, slots=True)
class _Line:
    indent: int
    sequence: bool
    body: str


def _text_bytes(label: str, value: str, maximum: int) -> bytes:
    if len(value) > maximum:
        raise ClosedYAMLError(f"{label} exceeds the closed-YAML bound")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ClosedYAMLError(f"{label} is not Unicode scalar text") from error
    if len(encoded) > maximum:
        raise ClosedYAMLError(f"{label} exceeds the closed-YAML bound")
    return encoded


def _prepare(value: object) -> list[_Line]:
    if type(value) is not str:
        raise ClosedYAMLError("closed YAML must be an exact string")
    if len(value) > _MAX_INPUT:
        raise ClosedYAMLError("closed YAML exceeds the input bound")
    # Validate cheap character properties before UTF-8 encoding or line allocation.
    for character in value:
        codepoint = ord(character)
        if (character in "\r\t" or codepoint == 0xfeff or codepoint == 0
                or codepoint < 0x20 and character != "\n"
                or 0xd800 <= codepoint <= 0xdfff):
            raise ClosedYAMLError("closed YAML contains forbidden text")
    _text_bytes("closed YAML", value, _MAX_INPUT)
    line_count = value.count("\n") + (not value.endswith("\n"))
    if line_count > _MAX_LINES:
        raise ClosedYAMLError("closed YAML exceeds the line bound")
    raw_lines = value.split("\n")
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()
    if not raw_lines or line_count >= _MAX_NODES:
        raise ClosedYAMLError("closed YAML is empty or exceeds the node bound")

    lines: list[_Line] = []
    for raw in raw_lines:
        if not raw or raw.endswith(" "):
            raise ClosedYAMLError("blank lines and trailing whitespace are forbidden")
        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2:
            raise ClosedYAMLError("indentation must use exact two-space steps")
        body = raw[indent:]
        if not body or body.startswith("#"):
            raise ClosedYAMLError("comments are forbidden")
        if body.startswith("%") or body in ("---", "..."):
            raise ClosedYAMLError("YAML directives and document markers are forbidden")
        if body == "-":
            lines.append(_Line(indent, True, ""))
        elif body.startswith("- "):
            lines.append(_Line(indent, True, body[2:]))
        else:
            lines.append(_Line(indent, False, body))
    return lines


def _pair(body: str) -> tuple[str, str | None]:
    match = re.fullmatch(r"([^:]+):(?: (.*))?", body)
    if match is None:
        raise ClosedYAMLError("line is not an exact mapping entry")
    key, raw = match.groups()
    if (_KEY.fullmatch(key) is None or key == "<<"
            or key.lower() in {"y", "n", "yes", "no", "on", "off", "true",
                               "false", "null"}):
        raise ClosedYAMLError("mapping key is not a conservative string key")
    _text_bytes("mapping key", key, _MAX_SCALAR)
    if raw == "":
        raise ClosedYAMLError("empty scalar must be represented as null or quoted text")
    return key, raw


def _quoted_single(raw: str) -> str:
    if len(raw) < 2 or not raw.endswith("'"):
        raise ClosedYAMLError("single-quoted scalar is malformed")
    inner = raw[1:-1]
    output: list[str] = []
    decoded_bytes = 0
    index = 0
    while index < len(inner):
        if inner[index] == "'":
            if index + 1 >= len(inner) or inner[index + 1] != "'":
                raise ClosedYAMLError("single-quoted scalar is malformed")
            character = "'"
            index += 2
        else:
            character = inner[index]
            index += 1
        codepoint = ord(character)
        width = (1 if codepoint <= 0x7f else 2 if codepoint <= 0x7ff
                 else 3 if codepoint <= 0xffff else 4)
        if decoded_bytes > _MAX_SCALAR - width:
            raise ClosedYAMLError("single-quoted scalar exceeds the decoded bound")
        decoded_bytes += width
        output.append(character)
    value = "".join(output)
    _text_bytes("quoted scalar", value, _MAX_SCALAR)
    _safe_decoded_text(value)
    return value


def _safe_decoded_text(value: str) -> None:
    if any(ord(character) < 0x20 or 0x7f <= ord(character) <= 0x9f
           or ord(character) == 0xfeff or 0xd800 <= ord(character) <= 0xdfff
           for character in value):
        raise ClosedYAMLError("quoted scalar decodes to control or surrogate text")


def _scalar(raw: str) -> str | bool | int | None | dict | list:
    if raw == "{}":
        return {}
    if raw == "[]":
        return []
    if raw == "null":
        return None
    if raw == "true":
        return True
    if raw == "false":
        return False
    if _INTEGER.fullmatch(raw) is not None:
        if len(raw) - (raw.startswith("-")) > _MAX_INTEGER_DIGITS:
            raise ClosedYAMLError("decimal integer exceeds the conversion work bound")
        try:
            return int(Decimal(raw))
        except (DecimalException, ValueError) as error:
            raise ClosedYAMLError("decimal integer is too large to decode safely") from error
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ClosedYAMLError("double-quoted scalar is malformed") from error
        if type(value) is not str:
            raise ClosedYAMLError("double-quoted scalar must contain a string")
        _text_bytes("quoted scalar", value, _MAX_SCALAR)
        _safe_decoded_text(value)
        return value
    if raw.startswith("'"):
        return _quoted_single(raw)
    _text_bytes("scalar", raw, _MAX_SCALAR)
    if any(mark in raw for mark in ('"', "'", "{", "}", "#")):
        raise ClosedYAMLError("flow or quoted syntax is malformed")
    if (raw.startswith(("[", "]", "{", "}", ",", "!", "&", "*", "|", ">",
                        "@", "`", "%"))
            or raw in {"-", "?", ":"} or raw.startswith(("- ", "? "))
            or raw.endswith(("]", ":")) or ": " in raw
            or re.search(r"(?:^| )[!&*]", raw) is not None):
        raise ClosedYAMLError("typed, graph, block, or flow YAML syntax is forbidden")
    lowered = raw.lower()
    if (lowered in {"y", "n", "yes", "no", "on", "off", "true", "false",
                    "null", "~",
                    ".inf", "+.inf", "-.inf", ".nan"}
            or _NUMBERISH.fullmatch(raw) is not None
            or _RADIX.fullmatch(raw) is not None
            or _LEADING_DOT_FLOAT.fullmatch(raw) is not None
            or _SEXAGESIMAL.fullmatch(raw) is not None
            or _DATE.fullmatch(raw) is not None):
        raise ClosedYAMLError("ambiguous YAML scalar must be quoted")
    if raw in ("---", "...") or _PLAIN.fullmatch(raw) is None:
        raise ClosedYAMLError("plain scalar is outside the conservative subset")
    return raw


class _Decoder:
    def __init__(self, lines: list[_Line]):
        self.lines = lines
        self.nodes = 0

    def _node(self, count: int = 1) -> None:
        self.nodes += count
        if self.nodes > _MAX_NODES:
            raise ClosedYAMLError("closed YAML exceeds the semantic node bound")

    def parse(self) -> dict:
        if (len(self.lines) == 1 and self.lines[0].indent == 0
                and not self.lines[0].sequence and self.lines[0].body == "{}"):
            self._node()
            return {}
        value, index = self._block(0, 0, 0)
        if index != len(self.lines) or type(value) is not dict:
            raise ClosedYAMLError("closed YAML must contain exactly one mapping root")
        return value

    def _block(self, index: int, indent: int, depth: int) -> tuple[object, int]:
        if depth > _MAX_DEPTH or index >= len(self.lines):
            raise ClosedYAMLError("closed YAML nesting is invalid or unbounded")
        line = self.lines[index]
        if line.indent != indent:
            raise ClosedYAMLError("nested block indentation is inconsistent")
        if line.sequence:
            return self._sequence(index, indent, depth)
        return self._mapping(index, indent, depth)

    def _child(self, index: int, parent_indent: int, depth: int) -> tuple[object, int]:
        if index >= len(self.lines):
            raise ClosedYAMLError("nested mapping has no value")
        line = self.lines[index]
        allowed = ((parent_indent, parent_indent + 2) if line.sequence
                   else (parent_indent + 2,))
        if line.indent not in allowed:
            raise ClosedYAMLError("nested block indentation is inconsistent")
        return self._block(index, line.indent, depth + 1)

    def _put(self, result: dict, key: str, raw: str | None,
             index: int, conceptual_indent: int, depth: int) -> int:
        if key in result:
            raise ClosedYAMLError("duplicate mapping key")
        self._node()  # Mapping keys are semantic string nodes too.
        if raw is None:
            value, index = self._child(index, conceptual_indent, depth)
        else:
            value = _scalar(raw)
            self._node()
        result[key] = value
        return index

    def _mapping(self, index: int, indent: int, depth: int) -> tuple[dict, int]:
        result: dict = {}
        self._node()
        while index < len(self.lines):
            line = self.lines[index]
            if line.indent != indent or line.sequence:
                break
            key, raw = _pair(line.body)
            index = self._put(result, key, raw, index + 1, indent, depth)
        return result, index

    def _sequence(self, index: int, indent: int, depth: int) -> tuple[list, int]:
        result: list = []
        self._node()
        while index < len(self.lines):
            line = self.lines[index]
            if line.indent != indent or not line.sequence:
                break
            index += 1
            if not line.body:
                if (index >= len(self.lines)
                        or self.lines[index].indent != indent + 2):
                    raise ClosedYAMLError("bare-dash child indentation is inconsistent")
                value, index = self._block(index, indent + 2, depth + 1)
            else:
                try:
                    key, raw = _pair(line.body)
                except ClosedYAMLError:
                    value = _scalar(line.body)
                    self._node()
                else:
                    value = {}
                    self._node()
                    index = self._put(value, key, raw, index, indent + 2, depth + 1)
                    while index < len(self.lines):
                        continuation = self.lines[index]
                        if continuation.indent != indent + 2 or continuation.sequence:
                            break
                        next_key, next_raw = _pair(continuation.body)
                        index = self._put(value, next_key, next_raw, index + 1,
                                          indent + 2, depth + 1)
            result.append(value)
        return result, index


def decode_closed_yaml(value: object) -> dict:
    """Decode one exact mapping in KIL's bounded, non-extensible YAML subset."""
    return _Decoder(_prepare(value)).parse()
