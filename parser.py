"""Lossless ER7 inspection, with hl7apy parsing and version-specific metadata.

Raw field values remain authoritative. No message is repaired or persisted here.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from hl7apy import load_reference
from hl7apy.consts import VALIDATION_LEVEL
from hl7apy.exceptions import HL7apyException
from hl7apy.parser import parse_message

MAX_BYTES = 1_000_000
MAX_SEGMENTS = 1_000
MAX_TREE_NODES = 20_000


@dataclass(frozen=True)
class Encoding:
    field: str = "|"
    component: str = "^"
    repetition: str = "~"
    escape: str = "\\"
    subcomponent: str = "&"


@dataclass(frozen=True)
class Segment:
    name: str
    occurrence: int
    line: int
    raw: str
    fields: tuple[str, ...]

    def value(self, number: int) -> str:
        return self.fields[number - 1] if 0 < number <= len(self.fields) else ""

    @property
    def label(self) -> str:
        return f"{self.name} [{self.occurrence}] · line {self.line}"


@dataclass
class Inspection:
    normalized: str
    segments: list[Segment] = field(default_factory=list)
    encoding: Encoding | None = None
    version: str = ""
    message_type: tuple[str, ...] = ()
    parsed: bool = False
    parse_error: str | None = None
    input_error: str | None = None
    notes: list[str] = field(default_factory=list)

    def named(self, name: str) -> list[Segment]:
        return [segment for segment in self.segments if segment.name == name]


def usable(value: str) -> bool:
    return bool(value.strip()) and value.strip() != '""'


def value_state(value: str) -> str:
    if value == '""':
        return "Explicit null"
    return "Present" if usable(value) else "Empty"


def decode_upload(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ValueError("The file exceeds the 1 MB input limit.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Use a UTF-8 text file containing one HL7 message.") from exc


def inspect_message(text: str) -> Inspection:
    result = Inspection(normalized="")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        result.input_error = "The input contains unsupported Unicode characters."
        return result
    if size > MAX_BYTES:
        result.input_error = "The message exceeds the 1 MB input limit."
        return result
    normalized = text.removeprefix("\ufeff").replace("\r\n", "\r").replace("\n", "\r")
    normalized = normalized.strip("\r")
    result.normalized = normalized
    if normalized != text:
        result.notes.append(
            "Line endings and any UTF-8 BOM were normalized for parsing; field values were preserved."
        )
    if not normalized:
        result.input_error = "Add a message or load a synthetic sample to begin."
        return result
    if len(normalized.split("\r")) > MAX_SEGMENTS:
        result.input_error = "The message exceeds the 1,000-segment input limit."
        return result
    if re.search(r"[\x00-\x0c\x0e-\x1f\x7f]", normalized):
        result.input_error = (
            "Control characters are unsupported. Use unframed ER7 text, without MLLP wrappers."
        )
        return result
    lines = normalized.split("\r")
    headers = [line for line in lines if line.startswith("MSH")]
    if headers:
        header = headers[0]
        if len(header) >= 4:
            delimiter = header[3]
            pieces = header.split(delimiter)
            codes = pieces[1] if len(pieces) > 1 else ""
            if (
                len(codes) == 4
                and len(set(delimiter + codes)) == 5
                and all(33 <= ord(char) <= 126 and not char.isalnum() for char in delimiter + codes)
            ):
                result.encoding = Encoding(delimiter, *codes)
    if (
        result.encoding
        and sum(
            normalized.count(char)
            for char in (
                result.encoding.field,
                result.encoding.component,
                result.encoding.repetition,
                result.encoding.subcomponent,
            )
        )
        > MAX_TREE_NODES
    ):
        result.input_error = (
            "The message exceeds the 20,000-separator inspection limit. Reduce input complexity."
        )
        return result
    counts: Counter[str] = Counter()
    separator = result.encoding.field if result.encoding else None
    for line_number, line in enumerate(lines, 1):
        name = line[:3]
        counts[name] += 1
        values: tuple[str, ...] = ()
        if separator:
            parts = line.split(separator)
            values = tuple([separator, *parts[1:]]) if name == "MSH" else tuple(parts[1:])
        result.segments.append(Segment(name, counts[name], line_number, line, values))
    if result.encoding:
        msh = result.named("MSH")[0]
        result.version = msh.value(12).split(result.encoding.component)[0]
        result.message_type = tuple(msh.value(9).split(result.encoding.component))
    if len(headers) != 1 or not lines[0].startswith("MSH") or not result.encoding:
        result.parse_error = (
            "A single leading MSH header with usable delimiters is required for parsing."
        )
        return result
    if not usable(result.version):
        result.parse_error = "MSH-12 must declare a version before version-specific parsing."
        return result
    try:
        parse_message(normalized, validation_level=VALIDATION_LEVEL.TOLERANT, find_groups=False)
        result.parsed = True
    except (HL7apyException, ValueError, TypeError, IndexError, AttributeError):
        # Exception text can contain input. Keep the UI/logs free of raw diagnostic payloads.
        result.parse_error = "hl7apy could not parse this input. Review header, segment identifiers, version, and datatype values. Raw inspection remains available."
    return result


@lru_cache(maxsize=256)
def field_metadata(segment: str, version: str) -> dict[int, tuple[str, str]]:
    """Cache only public standard metadata, never message contents."""
    try:
        reference = load_reference(segment, "Segment", version)
        return {
            int(name.rsplit("_", 1)[1]): (definition[3].replace("_", " ").title(), definition[2])
            for name, definition, _cardinality, _kind in reference[1]
        }
    except (HL7apyException, ValueError, TypeError, IndexError):
        return {}


def field_rows(segment: Segment, version: str) -> list[dict[str, Any]]:
    metadata = field_metadata(segment.name, version)
    return [
        {
            "Field": f"{segment.name}-{number}",
            "Name": metadata.get(number, ("Unspecified", ""))[0],
            "Datatype": metadata.get(number, ("", ""))[1],
            "Value": value,
            "State": value_state(value),
        }
        for number, value in enumerate(segment.fields, 1)
    ]


def segment_tree(segment: Segment, encoding: Encoding) -> dict[str, Any]:
    """Raw hierarchy preserving empty positions, repetitions, and escape text."""
    fields: dict[str, Any] = {}
    for number, value in enumerate(segment.fields, 1):
        if segment.name == "MSH" and number in (1, 2):
            fields[f"MSH-{number}"] = {"raw": value}
            continue
        repetitions = {}
        for repeat_number, repetition in enumerate(value.split(encoding.repetition), 1):
            repetitions[f"Repetition {repeat_number}"] = {
                f"Component {component_number}": {
                    f"Subcomponent {sub_number}": subcomponent
                    for sub_number, subcomponent in enumerate(
                        component.split(encoding.subcomponent), 1
                    )
                }
                for component_number, component in enumerate(
                    repetition.split(encoding.component), 1
                )
            }
        fields[f"{segment.name}-{number}"] = {"raw": value, "repetitions": repetitions}
    return fields
