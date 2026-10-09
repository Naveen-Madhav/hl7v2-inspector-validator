import pytest

from parser import MAX_BYTES, decode_upload, field_rows, inspect_message, segment_tree
from tests.cases import replace_field, sample


def test_raw_positions_repetitions_and_msh_numbering() -> None:
    result = inspect_message(
        replace_field(sample("adt_a01_baseline"), "PID", 3, "A^^^X^MR~B^^^Y^MR") + "||"
    )
    assert result.parsed and result.encoding
    msh, pid = result.named("MSH")[0], result.named("PID")[0]
    assert msh.value(1) == "|" and msh.value(2) == "^~\\&"
    assert msh.value(9) == "ADT^A01^ADT_A01"
    assert len(segment_tree(pid, result.encoding)["PID-3"]["repetitions"]) == 2
    assert result.segments[-1].fields[-2:] == ("", "")
    assert field_rows(pid, "2.5.1")[2]["Datatype"] == "CX"


def test_normalization_preserves_field_whitespace() -> None:
    text = replace_field(sample("adt_a01_baseline"), "PID", 5, " Example^Alex ")
    result = inspect_message(text.replace("\n", "\r\n"))
    assert result.named("PID")[0].value(5) == " Example^Alex "
    assert "\n" not in result.normalized


def test_upload_encoding_and_size() -> None:
    assert decode_upload(b"\xef\xbb\xbfMSH") == "MSH"
    with pytest.raises(ValueError, match="UTF-8"):
        decode_upload(b"\xff")
    with pytest.raises(ValueError, match="5 MB"):
        decode_upload(b"a" * (MAX_BYTES + 1))


@pytest.mark.parametrize(
    "text", ["", "MSH", "MSH|", "MSH|^~\\&", "MSH|^^\\&", "random", "\x0bMSH", "|" * 1_000_001]
)
def test_malformed_input_does_not_crash(text: str) -> None:
    result = inspect_message(text)
    assert not result.parsed
    assert result.input_error or result.parse_error


def test_complexity_boundary() -> None:
    result = inspect_message(sample("adt_a01_baseline") + "\nZIN|" + "^" * 20_001)
    assert result.input_error and "complexity" in result.input_error


def test_unknown_version_has_no_fabricated_metadata() -> None:
    result = inspect_message(replace_field(sample("adt_a01_baseline"), "MSH", 12, "9.9"))
    assert not result.parsed
    assert field_rows(result.named("PID")[0], "9.9")[0]["Name"] == "Unspecified"
