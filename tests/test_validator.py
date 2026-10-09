import csv
import io
import json
from pathlib import Path

import pytest

from parser import inspect_message, value_state
from tests.cases import Case, benchmark_cases, replace_field, sample
from validator import valid_datetime, validate


@pytest.mark.parametrize("case", benchmark_cases(), ids=lambda case: case.name)
def test_independent_benchmark(case: Case) -> None:
    report = validate(inspect_message(case.text))
    assert {issue.rule for issue in report.issues} == case.expected_rules
    assert all(issue.severity == "Error" for issue in report.issues)
    if case.expected_location:
        assert case.expected_location in {issue.location for issue in report.issues}
    else:
        assert report.complete


def test_sample_library_expectations() -> None:
    root = Path(__file__).resolve().parents[1] / "samples"
    for entry in json.loads((root / "manifest.json").read_text()):
        assert entry["synthetic"] is True
        report = validate(inspect_message((root / entry["file"]).read_text()))
        assert {issue.rule for issue in report.issues} == set(entry["expected_rules"])


@pytest.mark.parametrize(
    "value",
    [
        "2026",
        "202610",
        "20260228",
        "2024022912",
        "202610091230",
        "20261009123000.1234-0500",
        "20261009+0530",
    ],
)
def test_legitimate_datetime(value: str) -> None:
    assert valid_datetime(value)


@pytest.mark.parametrize(
    "value",
    [
        "20260229",
        "202600",
        "202613",
        "202610092400",
        "202610091260",
        "20261009123000.12345",
        "202610.1",
        "20261009123000+1460",
        "0000",
        "20261",
        "20261009^Q",
        "20261009123000Z",
    ],
)
def test_invalid_datetime(value: str) -> None:
    assert not valid_datetime(value)


def test_null_and_empty_remain_distinct() -> None:
    assert value_state('""') == "Explicit null"
    assert value_state("") == "Empty"
    report = validate(inspect_message(replace_field(sample("adt_a01_baseline"), "PID", 3, '""')))
    assert "R10" in {issue.rule for issue in report.issues}


def test_partial_coverage_never_appears_complete() -> None:
    texts = [
        replace_field(sample("adt_a01_baseline"), "MSH", 12, "2.4"),
        replace_field(sample("adt_a01_baseline"), "MSH", 9, "ADT^A04^ADT_A01"),
        replace_field(sample("oru_r01_baseline"), "OBX", 2, "ED"),
        sample("adt_a01_baseline") + "\nZIN|Synthetic extension",
    ]
    for text in texts:
        report = validate(inspect_message(text))
        assert not report.complete and report.coverage_notes


def test_repeated_result_groups_are_valid() -> None:
    text = sample("oru_r01_baseline")
    text += "\n" + "\n".join(text.splitlines()[2:])
    report = validate(inspect_message(text))
    assert not report.issues and report.complete


def test_missing_observation_in_second_group() -> None:
    text = sample("oru_r01_baseline") + "\n" + sample("oru_r01_baseline").splitlines()[2]
    report = validate(inspect_message(text))
    assert any(issue.rule == "R07" and "OBR [2]" in issue.location for issue in report.issues)


def test_delete_status_can_omit_value_and_type() -> None:
    text = replace_field(sample("oru_r01_baseline"), "OBX", 11, "D")
    text = replace_field(replace_field(text, "OBX", 5, ""), "OBX", 2, "")
    assert not validate(inspect_message(text)).issues


def test_escape_text_and_invalid_escape() -> None:
    valid = replace_field(sample("oru_r01_baseline"), "OBX", 2, "ST")
    valid = replace_field(valid, "OBX", 5, "Synthetic\\F\\text")
    assert not validate(inspect_message(valid)).issues
    invalid = replace_field(valid, "OBX", 5, "Synthetic\\text")
    assert any(issue.rule == "R08" for issue in validate(inspect_message(invalid)).issues)


def test_identifier_metadata_is_not_identifier() -> None:
    text = replace_field(sample("adt_a01_baseline"), "PID", 3, "^^^DEMO^MR")
    assert any(issue.rule == "R10" for issue in validate(inspect_message(text)).issues)


def test_order_id_mismatch_is_advisory() -> None:
    text = replace_field(sample("orm_o01_baseline"), "OBR", 2, "SYN-OTHER")
    report = validate(inspect_message(text))
    assert len(report.issues) == 1 and report.issues[0].severity == "Warning"


def test_report_exports_include_coverage_and_do_not_mutate_input() -> None:
    text = sample("oru_r01_broken")
    report = validate(inspect_message(text))
    assert json.loads(report.to_json())["issues"][0]["rule"] == "R14"
    row = list(csv.DictReader(io.StringIO(report.to_csv())))[0]
    assert row["profile_version"] and row["generated_at"] and row["checked_rules"]
    assert sample("oru_r01_broken") == text
    clean_rows = list(
        csv.DictReader(io.StringIO(validate(inspect_message(sample("adt_a01_baseline"))).to_csv()))
    )
    assert len(clean_rows) == 1 and clean_rows[0]["rule"] == ""


def test_batch_input_is_rejected_and_not_complete() -> None:
    report = validate(
        inspect_message(sample("adt_a01_baseline") + "\n" + sample("adt_a01_baseline"))
    )
    assert not report.complete
    assert any(issue.rule == "R01" for issue in report.issues)
