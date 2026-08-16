import pytest

from finale_file_parser.enigma.document import (
    EnigmaDocument,
    MalformedEnigmaError,
    Pool,
    Record,
    field_int,
    parse_enigma,
)
from finale_file_parser.errors import FinaleFileError

NS = "http://www.makemusic.com/2012/finale"


def _doc(body: str, *, version: str = "18.0", root: str = "finale") -> bytes:
    return f'<{root} version="{version}" xmlns="{NS}">{body}</{root}>'.encode()


FULL = _doc(
    """
    <header><headerData><wordOrder>1</wordOrder></headerData></header>
    <mappings><mapGroup minInclusive="17.0"/></mappings>
    <options><beamOptions><maxSlope>10</maxSlope></beamOptions></options>
    <others>
      <articDef cmper="1"><charMain>46</charMain></articDef>
      <measSpec cmper="1"/>
      <measSpec cmper="1" part="1" shared="true"/>
      <measSpec cmper="1" part="2" shared="true"/>
      <shapeData cmper="9"><data>1</data><data>2</data><data>3</data></shapeData>
    </others>
    <details><gfhold cmper1="1" cmper2="2"><val>x</val></gfhold></details>
    <entries>
      <entry entnum="1"><dura>1024</dura><note id="1"/><note id="2"/></entry>
    </entries>
    <texts><expression number="3"><text>PLACEHOLDER</text></expression></texts>
    """
)


def test_version() -> None:
    assert parse_enigma(FULL).version == "18.0"


def test_all_seven_pools_present() -> None:
    doc: EnigmaDocument = parse_enigma(FULL)
    for pool in (
        doc.header,
        doc.mappings,
        doc.options,
        doc.others,
        doc.details,
        doc.entries,
        doc.texts,
    ):
        assert isinstance(pool, Pool)
    assert doc.header.records[0].tag == "headerData"
    assert doc.mappings.records[0].tag == "mapGroup"


def test_records_preserved_in_document_order() -> None:
    tags = [r.tag for r in parse_enigma(FULL).others.records]
    assert tags == ["articDef", "measSpec", "measSpec", "measSpec", "shapeData"]


def test_of_tag_returns_all_matching_records_in_order() -> None:
    measspecs = parse_enigma(FULL).others.of_tag("measSpec")
    assert len(measspecs) == 3
    # the collision the survey found: score record + two per-part variants, all kept
    assert measspecs[0].attrs == {"cmper": "1"}
    assert measspecs[1].attrs == {"cmper": "1", "part": "1", "shared": "true"}
    assert measspecs[2].attrs == {"cmper": "1", "part": "2", "shared": "true"}


def test_of_tag_missing_returns_empty() -> None:
    assert parse_enigma(FULL).others.of_tag("nonesuch") == ()


def test_attrs_hold_all_attributes_verbatim() -> None:
    artic = parse_enigma(FULL).others.of_tag("articDef")[0]
    assert artic.attrs == {"cmper": "1"}
    assert artic.fields == {"charMain": "46"}


def test_scalar_field() -> None:
    entry = parse_enigma(FULL).entries.of_tag("entry")[0]
    assert entry.fields["dura"] == "1024"


def test_repeated_scalar_field_is_a_tuple() -> None:
    sd = parse_enigma(FULL).others.of_tag("shapeData")[0]
    assert sd.fields["data"] == ("1", "2", "3")


def test_repeated_nested_field_is_a_tuple_of_records() -> None:
    entry = parse_enigma(FULL).entries.of_tag("entry")[0]
    notes = entry.fields["note"]
    assert isinstance(notes, tuple) and len(notes) == 2
    assert all(isinstance(n, Record) for n in notes)


def test_single_nested_field_is_a_record() -> None:
    doc = parse_enigma(_doc("<others><fb cmper='1'><cell><fret>0</fret></cell></fb></others>"))
    cell = doc.others.of_tag("fb")[0].fields["cell"]
    assert isinstance(cell, Record)
    assert cell.fields == {"fret": "0"}


def test_nesting_four_deep() -> None:
    doc = parse_enigma(_doc("<others><a cmper='1'><b><c><d>leaf</d></c></b></a></others>"))
    a = doc.others.of_tag("a")[0]
    b = a.fields["b"]
    assert isinstance(b, Record)
    c = b.fields["c"]
    assert isinstance(c, Record)
    assert c.fields["d"] == "leaf"


def test_empty_field_is_empty_string() -> None:
    doc = parse_enigma(_doc("<others><x cmper='1'><flag></flag></x></others>"))
    assert doc.others.of_tag("x")[0].fields["flag"] == ""


def test_absent_pool_is_an_empty_pool() -> None:
    doc = parse_enigma(_doc("<entries><entry entnum='1'/></entries>"))
    assert doc.texts.records == ()
    assert doc.header.records == ()


def test_record_is_frozen() -> None:
    rec = parse_enigma(FULL).others.records[0]
    with pytest.raises((AttributeError, TypeError)):
        rec.tag = "y"  # type: ignore[misc]


def test_rejects_non_xml() -> None:
    with pytest.raises(MalformedEnigmaError):
        parse_enigma(b"this is not xml")


def test_rejects_wrong_root() -> None:
    with pytest.raises(MalformedEnigmaError, match="finale"):
        parse_enigma(_doc("", root="notfinale"))


def test_rejects_entity_expansion() -> None:
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE finale ['
        '<!ENTITY a "AAAAAAAAAA"><!ENTITY b "&a;&a;&a;&a;&a;">]>'
        f'<finale version="18.0" xmlns="{NS}">&b;</finale>'
    ).encode()
    with pytest.raises(MalformedEnigmaError):
        parse_enigma(bomb)


def test_malformed_error_is_a_finale_file_error() -> None:
    assert issubclass(MalformedEnigmaError, FinaleFileError)


def test_record_with_attribute_preserves_its_own_text() -> None:
    doc = parse_enigma(
        _doc('<texts><expression number="1">^fontMus(...)cresc.</expression></texts>')
    )
    expr = doc.texts.of_tag("expression")[0]
    assert expr.text == "^fontMus(...)cresc."


def test_record_with_text_and_nested_fields_preserves_both() -> None:
    doc = parse_enigma(_doc("<others><x cmper='1'>LEAD<b>1</b></x></others>"))
    x = doc.others.of_tag("x")[0]
    assert x.text == "LEAD"
    assert x.fields == {"b": "1"}


def test_pure_scalar_field_is_still_a_bare_str_not_a_record() -> None:
    # No attributes, no children -> stays a scalar str; the classification
    # rule for what becomes a Record did not change.
    artic = parse_enigma(FULL).others.of_tag("articDef")[0]
    assert artic.fields["charMain"] == "46"
    assert isinstance(artic.fields["charMain"], str)
    assert not isinstance(artic.fields["charMain"], Record)


def test_field_int_reads_a_scalar_and_refuses_everything_else() -> None:
    """`field_int` is shared by eight readers, so its edges are pinned here.

    Absence is ordinary in this format -- Enigma omits a field rather than
    writing a default -- so a missing value is None, not an error.
    """
    assert field_int("42") == 42
    assert field_int("-1") == 0 - 1
    assert field_int(None) is None
    assert field_int("") is None
    assert field_int("not a number") is None


def test_field_int_cannot_be_fooled_by_a_non_scalar_field() -> None:
    """The property that let eight modules keep private copies of this without
    ever diverging, and that makes one shared copy safe.

    A `Record.fields` value is a str, a Record, or a tuple of either -- never a
    bare int -- so `int(str(value))` has nothing to succeed on except a scalar.
    A Record stringifies to its dataclass repr and a tuple to "('1', '2')", and
    both raise rather than yielding a plausible wrong number.

    Delete the guard by returning `int(value)` for any value and this still
    passes; what it pins is that the *stringifying* form is not more permissive
    than the isinstance-guarded form the other two modules used.
    """
    nested = Record(tag="x", attrs={}, text="", fields={"a": "1"})
    assert field_int(nested) is None
    assert field_int(("1", "2")) is None
    assert field_int((nested,)) is None
    # The single-element tuple is the interesting one: it reads as "('1',)",
    # which contains a digit and still must not decode as 1.
    assert field_int(("1",)) is None
