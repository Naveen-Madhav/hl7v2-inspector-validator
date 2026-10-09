"""Expected outcomes are specified independently from validator execution."""

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Case:
    name: str
    text: str
    expected_rules: frozenset[str] = frozenset()
    expected_location: str = ""


def sample(name: str) -> str:
    return (ROOT / "samples" / f"{name}.hl7").read_text().rstrip("\r\n")


def replace_field(text: str, segment: str, number: int, value: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(segment + "|"):
            parts = line.split("|")
            position = number - 1 if segment == "MSH" else number
            parts.extend([""] * max(0, position + 1 - len(parts)))
            parts[position] = value
            lines[index] = "|".join(parts)
            break
    return "\n".join(lines)


def benchmark_cases() -> list[Case]:
    adt, orm, oru = (
        sample(name) for name in ("adt_a01_baseline", "orm_o01_baseline", "oru_r01_baseline")
    )

    def broken(name: str, text: str, rules: set[str], location: str) -> Case:
        return Case(name, text, frozenset(rules), location)

    return [
        Case("Baseline admission", adt),
        Case("Baseline laboratory order", orm),
        Case("Baseline laboratory result", oru),
        broken("Missing header", "\n".join(adt.splitlines()[1:]), {"R01", "R02"}, "MSH"),
        broken("Duplicate delimiter", adt.replace("^~\\&", "^^\\&"), {"R02"}, "MSH-1 / MSH-2"),
        broken(
            "Mismatched structure",
            replace_field(adt, "MSH", 9, "ADT^A01^ORU_R01"),
            {"R03"},
            "MSH-9",
        ),
        broken("Missing version", replace_field(adt, "MSH", 12, ""), {"R04"}, "MSH-12"),
        broken("Missing control ID", replace_field(adt, "MSH", 10, ""), {"R05"}, "MSH[1]-10"),
        broken("Invalid processing ID", replace_field(adt, "MSH", 11, "Q"), {"R06"}, "MSH-11"),
        broken("Missing visit", "\n".join(adt.splitlines()[:-1]), {"R07"}, "PV1"),
        broken(
            "Order before control segment",
            sample("orm_o01_broken"),
            {"R07", "R08"},
            "OBR [1] · line 3",
        ),
        broken("Empty patient class", replace_field(adt, "PV1", 2, ""), {"R09"}, "PV1[1]-2"),
        broken("Missing patient identifier", replace_field(adt, "PID", 3, ""), {"R10"}, "PID[1]-3"),
        broken("Empty patient name", replace_field(adt, "PID", 5, "^^^"), {"R11"}, "PID[1]-5"),
        broken(
            "Impossible event date",
            replace_field(adt, "EVN", 2, "20260230120000"),
            {"R12"},
            "EVN[1]-2",
        ),
        broken("Missing laboratory service", replace_field(orm, "OBR", 4, ""), {"R13"}, "OBR[1]-4"),
        broken(
            "Text declared as numeric", sample("oru_r01_broken"), {"R14"}, "OBX[1]-5 repetition 1"
        ),
        broken(
            "Final observation without value", replace_field(oru, "OBX", 5, ""), {"R15"}, "OBX[1]-5"
        ),
        Case("Reduced date precision", replace_field(adt, "PID", 7, "1990")),
        Case("Fraction and timezone", replace_field(adt, "MSH", 7, "20261009120000.1234+0530")),
        Case("Unicode single-component name", replace_field(adt, "PID", 5, "Černý")),
        Case("Repeated laboratory orders", orm + "\n" + "\n".join(orm.splitlines()[-2:])),
        Case(
            "Custom delimiters",
            adt.translate(str.maketrans({"|": "*", "^": "%", "~": "$", "\\": "!", "&": "?"})),
        ),
        Case("Explicit null optional field", replace_field(adt, "EVN", 3, '""')),
    ]
