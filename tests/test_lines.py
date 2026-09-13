import pytest

from gedcom_mcp.gedcom.lines import CONC_WIDTH, GedcomParseError, new_document, parse_bytes, parse_text


def test_roundtrip_is_byte_identical(fixture_bytes: bytes) -> None:
    doc = parse_bytes(fixture_bytes)
    assert doc.codec == "utf-8"
    assert doc.bom == b"\xef\xbb\xbf"
    assert doc.eol == "\r\n"
    assert doc.to_bytes() == fixture_bytes


def test_untouched_lines_survive_edits_elsewhere(fixture_bytes: bytes) -> None:
    doc = parse_bytes(fixture_bytes)
    doc.record("@I4@").sub("SEX").value = "M"
    out = doc.to_bytes()
    original_lines = fixture_bytes.split(b"\r\n")
    new_lines = out.split(b"\r\n")
    assert len(original_lines) == len(new_lines)
    diffs = [(a, b) for a, b in zip(original_lines, new_lines, strict=True) if a != b]
    assert diffs == [(b"1 SEX F", b"1 SEX M")]


def test_cont_conc_folding(fixture_bytes: bytes) -> None:
    doc = parse_bytes(fixture_bytes)
    note = doc.record("@I1@").sub("NOTE")
    assert note.text == (
        "William was apprenticed at fourteen and ran his own forge on Redcliffe Street "
        'from about 1865 until his death.\nHe was known locally as "Iron Bill".'
    )
    shared = doc.record("@N1@")
    assert shared.text.startswith(
        "Shared research note: the Smith forge appears on the 1881 and 1891 censuses.\n"
    )


def test_set_text_splits_long_and_multiline_values() -> None:
    doc = new_document()
    rec = doc.add_record("NOTE", "@N1@")
    long = "x" * (CONC_WIDTH + 10)
    rec.set_text(f"{long}\nsecond line")
    tags = [c.tag for c in rec.children]
    assert tags == ["CONC", "CONT"]
    assert rec.value == "x" * CONC_WIDTH
    assert rec.text == f"{long}\nsecond line"
    # re-parse what we wrote and make sure it folds back identically
    again = parse_bytes(doc.to_bytes())
    assert again.record("@N1@").text == f"{long}\nsecond line"


def test_set_text_keeps_non_continuation_children() -> None:
    doc = parse_text("0 @N1@ NOTE hello\n1 CONT world\n1 SOUR @S1@\n0 TRLR\n")
    rec = doc.record("@N1@")
    rec.set_text("replaced")
    assert [c.tag for c in rec.children] == ["SOUR"]
    assert rec.render() == "0 @N1@ NOTE replaced"


def test_new_document_is_well_formed() -> None:
    doc = new_document()
    text = doc.render()
    assert text.startswith("0 HEAD\r\n1 SOUR gedcom-mcp\r\n")
    assert "1 CHAR UTF-8" in text
    assert text.endswith("0 TRLR\r\n")
    rec = doc.add_record("INDI", doc.next_xref("I"))
    assert rec.xref == "@I1@"
    assert doc.records[-1].tag == "TRLR"


def test_next_xref_skips_used_ids(fixture_bytes: bytes) -> None:
    doc = parse_bytes(fixture_bytes)
    assert doc.next_xref("I") == "@I13@"
    assert doc.next_xref("F") == "@F5@"
    assert doc.next_xref("N") == "@N2@"
    assert doc.next_xref("X") == "@X1@"


def test_lf_and_no_bom_preserved() -> None:
    raw = b"0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME A /B/\n0 TRLR\n"
    doc = parse_bytes(raw)
    assert doc.eol == "\n"
    assert doc.bom == b""
    assert doc.to_bytes() == raw


def test_bad_level_structure_raises() -> None:
    with pytest.raises(GedcomParseError):
        parse_text("0 HEAD\n2 CHAR UTF-8\n0 TRLR\n")
    with pytest.raises(GedcomParseError):
        parse_text("0 HEAD\nnot a line\n0 TRLR\n")


def test_adopt_renumbers_levels() -> None:
    doc = parse_text("0 @I1@ INDI\n1 BIRT\n2 DATE 1900\n0 @I2@ INDI\n0 TRLR\n")
    birt = doc.record("@I1@").sub("BIRT")
    doc.record("@I2@").adopt(birt)
    assert doc.record("@I1@").sub("BIRT") is None
    assert doc.record("@I2@").path_value("BIRT/DATE") == "1900"
    assert birt.level == 1 and birt.sub("DATE").level == 2


def test_lf_file_with_stray_carriage_returns_in_notes() -> None:
    """Ancestry 2025 exports use LF line endings but embed CRs inside CONT values."""
    raw = (
        b"0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME A /B/\n1 NOTE first\r\n"
        b"2 CONT second\n2 CONT \r\n2 CONT third\n0 TRLR\n"
    )
    doc = parse_bytes(raw)
    assert doc.eol == "\n"
    assert doc.to_bytes() == raw
    assert doc.record("@I1@").sub("NOTE").text == "first\nsecond\n\nthird"
