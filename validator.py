"""Bounded v2.5.1 laboratory/admission checks, not universal conformance certification."""

import csv
import io
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from parser import Inspection, Segment, usable

PROFILE_VERSION = "HL7V2-IV-1.0"
PROFILES = {
    ("ADT", "A01"): ("ADT_A01", ("MSH", "EVN", "PID", "PV1")),
    ("ORM", "O01"): ("ORM_O01", ("MSH", "PID", "ORC", "OBR")),
    ("ORU", "R01"): ("ORU_R01", ("MSH", "PID", "OBR", "OBX")),
}
CHECKED_TYPES = {"NM", "ST", "TX", "CE", "CWE"}
RESULT_STATUSES = {"C", "D", "F", "I", "N", "O", "P", "R", "S", "U", "W", "X"}
NO_VALUE_STATUSES = {"D", "I", "N", "O", "U", "X"}


@dataclass(frozen=True)
class Issue:
    rule: str
    severity: str
    location: str
    explanation: str
    correction: str
    basis: str


@dataclass
class ValidationReport:
    profile: str
    scoped: bool
    parsed: bool
    issues: list[Issue] = field(default_factory=list)
    coverage_notes: list[str] = field(default_factory=list)
    checked_rules: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def errors(self) -> int:
        return sum(issue.severity == "Error" for issue in self.issues)

    @property
    def warnings(self) -> int:
        return sum(issue.severity == "Warning" for issue in self.issues)

    @property
    def complete(self) -> bool:
        return self.scoped and self.parsed and not self.coverage_notes

    def as_dict(self) -> dict:
        return {"profile_version": PROFILE_VERSION, **asdict(self)}

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False)

    def to_csv(self) -> str:
        buffer = io.StringIO(newline="")
        columns = [
            "profile_version",
            "profile",
            "generated_at",
            "coverage",
            "checked_rules",
            "coverage_notes",
            "rule",
            "severity",
            "location",
            "explanation",
            "correction",
            "basis",
        ]
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        common = {
            "profile_version": PROFILE_VERSION,
            "profile": self.profile,
            "generated_at": self.generated_at,
            "coverage": "Scoped" if self.complete else "Limited",
            "checked_rules": "; ".join(self.checked_rules),
            "coverage_notes": "; ".join(self.coverage_notes),
        }
        issues: list[Issue | None] = list(self.issues) if self.issues else [None]
        for issue in issues:
            row = {**common, **(asdict(issue) if issue else {})}
            # Protect spreadsheet users from formula interpretation in user-controlled text.
            writer.writerow(
                {
                    key: "'" + value
                    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
                    else value
                    for key, value in row.items()
                }
            )
        return buffer.getvalue()


def valid_datetime(value: str, datatype: str = "TS", component: str = "^") -> bool:
    """Validate raw DT/DTM/TS with allowed precision, fraction, offset, and real dates."""
    if datatype == "TS":
        parts = value.split(component)
        if len(parts) > 2 or (
            len(parts) == 2 and parts[1] not in {"", "Y", "L", "D", "H", "M", "S"}
        ):
            return False
        value = parts[0]
    pattern = r"(?P<digits>\d{4}(?:\d{2}){0,5})(?P<fraction>\.\d{1,4})?(?P<offset>[+-]\d{4})?"
    match = re.fullmatch(pattern, value, flags=re.ASCII)
    if not match:
        return False
    digits, fraction, offset = match.group("digits", "fraction", "offset")
    if datatype == "DT" and (len(digits) > 8 or fraction or offset):
        return False
    if fraction and len(digits) != 14:
        return False
    if offset:
        hour, minute = int(offset[1:3]), int(offset[3:])
        if hour > 14 or minute > 59 or (hour == 14 and minute != 0):
            return False
    try:
        values = [int(digits[:4]), 1, 1, 0, 0, 0]
        for index in range(1, len(digits) // 2 - 1):
            start = 4 + (index - 1) * 2
            values[index] = int(digits[start : start + 2])
        datetime(values[0], values[1], values[2], values[3], values[4], values[5])
    except ValueError:
        return False
    return True


def validate(inspection: Inspection) -> ValidationReport:
    message_type = inspection.message_type
    selected = PROFILES.get((message_type[0], message_type[1])) if len(message_type) >= 2 else None
    scoped = bool(selected and inspection.version == "2.5.1")
    report = ValidationReport(
        selected[0] if selected else "Unrecognized profile", scoped, inspection.parsed
    )

    def add(
        rule: str,
        location: str,
        explanation: str,
        correction: str,
        severity: str = "Error",
        basis: str = "HL7 v2.5.1",
    ) -> None:
        report.issues.append(Issue(rule, severity, location, explanation, correction, basis))

    def required(
        segment: Segment, number: int, rule: str, title: str, basis: str = "Project profile"
    ) -> None:
        if not usable(segment.value(number)):
            add(
                rule,
                f"{segment.name}[{segment.occurrence}]-{number}",
                f"{title} is missing, empty, or explicitly null.",
                f"Supply a usable {title.lower()} for this scenario.",
                basis=basis,
            )

    if inspection.input_error:
        add(
            "R01",
            "Input",
            inspection.input_error,
            "Use one unframed message within the input limits.",
            basis="Input boundary",
        )
        report.coverage_notes.append("Parsing and message checks were not performed.")
        return report
    headers = inspection.named("MSH")
    report.checked_rules.append("R01")
    if len(headers) != 1 or not inspection.segments or inspection.segments[0].name != "MSH":
        add(
            "R01",
            "MSH",
            "Exactly one MSH header must start the message; batch input is unsupported.",
            "Provide one message beginning with MSH.",
        )
        report.coverage_notes.append("Header placement prevents full parsing.")
    report.checked_rules.append("R02")
    if not inspection.encoding:
        add(
            "R02",
            "MSH-1 / MSH-2",
            "The header does not declare five distinct usable separator characters.",
            "Declare a field separator and four encoding characters, for example MSH|^~\\&.",
        )
        report.coverage_notes.append("Field checks cannot run without declared delimiters.")
        return report
    encoding = inspection.encoding
    if not headers:
        return report
    msh = headers[0]
    report.checked_rules.extend(["R03", "R04", "R05", "R06"])
    if (
        len(message_type) != 3
        or not all(usable(part) for part in message_type)
        or (selected and message_type[2] != selected[0])
    ):
        add(
            "R03",
            "MSH-9",
            "Message code, trigger event, and structure must be present and consistent.",
            "Use the selected profile's triplet, such as ADT^A01^ADT_A01.",
            basis="Project profile",
        )
    if not usable(inspection.version):
        add(
            "R04",
            "MSH-12",
            "The HL7 version is missing or null.",
            "Declare the sender's actual version; this validator evaluates 2.5.1.",
        )
    if inspection.version != "2.5.1":
        report.coverage_notes.append("Version-specific validation supports 2.5.1 only.")
    required(msh, 10, "R05", "Message control ID", "HL7 v2.5.1")
    processing_id = msh.value(11).split(encoding.component)[0]
    if processing_id not in {"P", "D", "T"}:
        add(
            "R06",
            "MSH-11",
            "Processing ID must be P (production), D (debugging), or T (training).",
            "Set the code appropriate to the sending environment.",
        )
    if not selected:
        report.coverage_notes.append(
            "Message-specific checks support ADT-A01, ORM-O01, and ORU-R01 only."
        )
    if not scoped:
        return report
    assert selected is not None
    if not inspection.parsed:
        report.coverage_notes.append(
            "hl7apy parsing failed; only recoverable raw-field checks ran."
        )
    core = selected[1]
    report.checked_rules.extend(["R07", "R08", "R09", "R10", "R11", "R12"])
    for name in core:
        if not inspection.named(name):
            add(
                "R07",
                name,
                f"{name} is required for the {selected[0]} demonstration scenario.",
                f"Add the {name} segment in its documented position.",
                basis="Project profile",
            )
    # Validate the core grammar per group; allow repeated order/observation groups.
    state = -1
    for segment in inspection.segments:
        if segment.name not in core:
            report.coverage_notes.append(
                f"{segment.name or '(blank line)'} at line {segment.line} is outside core structural coverage."
            )
            continue
        position = core.index(segment.name)
        repeated_group = segment.occurrence > 1 and (
            (selected[0] == "ORU_R01" and segment.name == "OBR" and state == core.index("OBX"))
            or (selected[0] == "ORM_O01" and segment.name == "ORC" and state == core.index("OBR"))
        )
        repeated_obx = selected[0] == "ORU_R01" and segment.name == "OBX" and state == position
        if (position <= state and not repeated_group and not repeated_obx) or position > state + 1:
            add(
                "R08",
                segment.label,
                "This core segment is duplicated or out of order for the selected scenario.",
                "Check the segment sequence and order-group boundaries.",
                basis="Project profile",
            )
        state = position
        if not segment.raw.startswith(segment.name + encoding.field):
            add(
                "R08",
                segment.label,
                "The segment identifier is not followed by the declared field separator.",
                "Use the separator declared in MSH-1.",
            )
        for number, value in enumerate(segment.fields, 1):
            if segment.name == "MSH" and number in (1, 2):
                continue
            if value.count(encoding.escape) % 2:
                add(
                    "R08",
                    f"{segment.name}[{segment.occurrence}]-{number}",
                    "An escape sequence is not closed.",
                    "Close the escape sequence; encode a literal escape character with the E escape.",
                )
    # Every laboratory order group needs its own OBR, not merely one somewhere in the message.
    if selected[0] == "ORM_O01":
        orders = inspection.named("ORC")
        for order in orders:
            following = [s for s in inspection.segments if s.line > order.line]
            group = following[
                : next((i for i, s in enumerate(following) if s.name == "ORC"), len(following))
            ]
            if not any(s.name == "OBR" for s in group):
                add(
                    "R07",
                    order.label,
                    "This laboratory order group has no OBR segment.",
                    "Include one OBR for each laboratory order.",
                    basis="Project profile",
                )
    for segment in inspection.segments:
        if segment.name == "MSH":
            required(segment, 7, "R09", "Message timestamp", "HL7 v2.5.1")
        elif segment.name == "EVN":
            required(segment, 2, "R09", "Recorded event timestamp", "HL7 v2.5.1")
        elif segment.name == "PV1":
            required(segment, 2, "R09", "Patient class", "HL7 v2.5.1")
        elif segment.name == "PID":
            required(segment, 3, "R10", "Patient identifier")
            for repetition, value in enumerate(segment.value(3).split(encoding.repetition), 1):
                if usable(value) and not usable(value.split(encoding.component)[0]):
                    add(
                        "R10",
                        f"PID[{segment.occurrence}]-3 repetition {repetition}",
                        "Identifier metadata is present but the identifier value is empty.",
                        "Populate the first identifier component.",
                        basis="Project profile",
                    )
            name = segment.value(5)
            if not usable(name) or not any(
                usable(part)
                for part in re.split(
                    f"[{re.escape(encoding.component + encoding.subcomponent + encoding.repetition)}]",
                    name,
                )
            ):
                add(
                    "R11",
                    f"PID[{segment.occurrence}]-5",
                    "Patient name has no usable component.",
                    "Supply the available name using the declared components.",
                    basis="Project profile",
                )
        date_fields = {
            "MSH": (7,),
            "EVN": (2, 6),
            "PID": (7,),
            "PV1": (44, 45),
            "ORC": (9,),
            "OBR": (7, 8, 22),
            "OBX": (14, 19),
        }
        for number in date_fields.get(segment.name, ()):
            value = segment.value(number)
            if usable(value) and not valid_datetime(value, component=encoding.component):
                add(
                    "R12",
                    f"{segment.name}[{segment.occurrence}]-{number}",
                    "Date/time has an invalid format, precision, offset, or calendar value.",
                    "Use HL7 date/time syntax with a real date; reduced precision is allowed.",
                )
    if selected[0] in {"ORM_O01", "ORU_R01"}:
        report.checked_rules.extend(["R13", "R14", "R15"])
        _laboratory_checks(inspection, report, add, required)
    report.coverage_notes = list(dict.fromkeys(report.coverage_notes))
    return report


def _laboratory_checks(
    inspection: Inspection,
    report: ValidationReport,
    add: Callable[..., None],
    required: Callable[..., None],
) -> None:
    encoding = inspection.encoding
    assert encoding is not None
    current_order: Segment | None = None
    for segment in inspection.segments:
        if segment.name == "ORC":
            current_order = segment
            required(segment, 1, "R13", "Order control code", "HL7 v2.5.1")
        elif segment.name == "OBR":
            required(segment, 4, "R13", "Laboratory service identifier")
            if current_order:
                for number in (2, 3):
                    left, right = current_order.value(number), segment.value(number)
                    if usable(left) and usable(right) and left != right:
                        add(
                            "R13",
                            f"OBR[{segment.occurrence}]-{number}",
                            "This order identifier differs from the corresponding ORC identifier.",
                            "Confirm both segments identify the same order in this laboratory scenario.",
                            severity="Warning",
                            basis="Project advisory",
                        )
            current_order = None
            if report.profile == "ORU_R01":
                following = [s for s in inspection.segments if s.line > segment.line]
                group = following[
                    : next(
                        (i for i, s in enumerate(following) if s.name in {"OBR", "PID"}),
                        len(following),
                    )
                ]
                if not any(s.name == "OBX" for s in group):
                    add(
                        "R07",
                        segment.label,
                        "This result group has no OBX segment.",
                        "Include observations for each laboratory result group.",
                        basis="Project profile",
                    )
        elif segment.name == "OBX":
            required(segment, 3, "R15", "Observation identifier")
            status, value_type = segment.value(11), segment.value(2)
            if status not in RESULT_STATUSES:
                add(
                    "R15",
                    f"OBX[{segment.occurrence}]-11",
                    "Observation status is missing or unrecognized.",
                    "Supply an HL7 v2.5.1 observation result status, such as F for final.",
                )
            if status not in NO_VALUE_STATUSES:
                required(segment, 5, "R15", "Observation value")
            if not usable(value_type) and status != "D":
                required(segment, 2, "R14", "Observation value type", "HL7 v2.5.1")
            elif usable(value_type) and value_type not in CHECKED_TYPES:
                report.coverage_notes.append(
                    f"OBX[{segment.occurrence}] datatype {value_type} is not checked; supported types are NM, ST, TX, CE, CWE."
                )
            elif value_type in CHECKED_TYPES:
                for index, value in enumerate(segment.value(5).split(encoding.repetition), 1):
                    if not usable(value):
                        continue
                    location = f"OBX[{segment.occurrence}]-5 repetition {index}"
                    if value_type == "NM" and not re.fullmatch(
                        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value, flags=re.ASCII
                    ):
                        add(
                            "R14",
                            location,
                            "The result declares NM (numeric), but this value is not an HL7 number.",
                            "Supply a numeric value or declare the correct datatype for the intended result.",
                        )
                    elif value_type in {"ST", "TX"} and any(
                        char in value for char in (encoding.component, encoding.subcomponent)
                    ):
                        add(
                            "R14",
                            location,
                            f"The {value_type} value contains an unescaped component separator.",
                            "Escape literal separators, or use an appropriate composite datatype.",
                        )
                    elif value_type in {"CE", "CWE"}:
                        parts = value.split(encoding.component)
                        if len(parts) > (6 if value_type == "CE" else 9):
                            add(
                                "R14",
                                location,
                                f"The coded value has too many components for {value_type} in 2.5.1.",
                                "Review the coded element's component positions.",
                            )
                        elif not any(usable(part) for part in parts):
                            add(
                                "R14",
                                location,
                                "The coded value contains separators but no usable content.",
                                "Supply a code or descriptive text.",
                            )
                        elif usable(parts[0]) and (len(parts) < 3 or not usable(parts[2])):
                            add(
                                "R14",
                                location,
                                "A code is supplied without a coding-system identifier.",
                                "Identify the coding system so the receiver can interpret the code.",
                                severity="Warning",
                                basis="Project advisory",
                            )
