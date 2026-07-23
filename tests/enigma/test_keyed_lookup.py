import pytest

from finale_file_parser.enigma.document import (
    DetailsPool,
    EntriesPool,
    MalformedEnigmaError,
    OptionsPool,
    OthersPool,
    Pool,
    TextsPool,
    parse_enigma,
)

NS = "http://www.makemusic.com/2012/finale"


def _doc(body: str) -> bytes:
    return f'<finale version="18.0" xmlns="{NS}">{body}</finale>'.encode()


FULL = _doc(
    """
    <header><headerData><wordOrder>1</wordOrder></headerData></header>
    <mappings><mapGroup minInclusive="17.0"/></mappings>
    <options><beamOptions><maxSlope>10</maxSlope></beamOptions></options>
    <others>
      <articDef cmper="1"><charMain>46</charMain></articDef>
      <articDef cmper="2"><charMain>47</charMain></articDef>
      <textBlock cmper="5" inci="0"><t>a</t></textBlock>
      <textBlock cmper="5" inci="1"><t>b</t></textBlock>
      <measSpec cmper="1"><s>score</s></measSpec>
      <measSpec cmper="1" part="1" shared="true"><s>p1</s></measSpec>
      <measSpec cmper="1" part="2" shared="true"><s>p2</s></measSpec>
    </others>
    <details>
      <gfhold cmper1="1" cmper2="2"><v>x</v></gfhold>
      <perfData entnum="9" inci="0"><vel>64</vel></perfData>
    </details>
    <entries><entry entnum="1"><dura>1024</dura></entry></entries>
    <texts>
      <expression number="3"><t>cresc.</t></expression>
      <fileInfo type="title"><t>PLACEHOLDER</t></fileInfo>
    </texts>
    """
)


def test_pool_subtypes() -> None:
    doc = parse_enigma(FULL)
    assert isinstance(doc.options, OptionsPool)
    assert isinstance(doc.others, OthersPool)
    assert isinstance(doc.details, DetailsPool)
    assert isinstance(doc.entries, EntriesPool)
    assert isinstance(doc.texts, TextsPool)
    assert isinstance(doc.header, Pool)  # plain Pool singleton


def test_options_get_by_tag() -> None:
    doc = parse_enigma(FULL)
    beam_options = doc.options.get("beamOptions")
    assert beam_options is not None
    assert beam_options.fields["maxSlope"] == "10"
    assert doc.options.get("missing") is None


def test_others_get_exact() -> None:
    doc = parse_enigma(FULL)
    artic_1 = doc.others.get("articDef", 1)
    assert artic_1 is not None
    assert artic_1.fields["charMain"] == "46"
    artic_2 = doc.others.get("articDef", "2")  # str arg
    assert artic_2 is not None
    assert artic_2.fields["charMain"] == "47"
    text_block = doc.others.get("textBlock", 5, inci=1)
    assert text_block is not None
    assert text_block.fields["t"] == "b"
    assert doc.others.get("articDef", 999) is None


def test_others_part_disambiguation() -> None:
    """The measSpec case: score record has no part; variants have part=1/2."""
    doc = parse_enigma(FULL)
    score = doc.others.get("measSpec", 1)  # part omitted -> score
    assert score is not None
    assert score.fields["s"] == "score"
    part_1 = doc.others.get("measSpec", 1, part=1)
    assert part_1 is not None
    assert part_1.fields["s"] == "p1"
    part_2 = doc.others.get("measSpec", 1, part=2)
    assert part_2 is not None
    assert part_2.fields["s"] == "p2"


def test_others_all_with_returns_score_plus_all_parts() -> None:
    doc = parse_enigma(FULL)
    variants = doc.others.all_with("measSpec", 1)
    assert [r.fields["s"] for r in variants] == ["score", "p1", "p2"]  # document order


def test_details_pair_and_entry_forms() -> None:
    doc = parse_enigma(FULL)
    gfhold = doc.details.get("gfhold", 1, 2)
    assert gfhold is not None
    assert gfhold.fields["v"] == "x"
    perf_data = doc.details.for_entry("perfData", 9, inci=0)
    assert perf_data is not None
    assert perf_data.fields["vel"] == "64"
    assert doc.details.get("gfhold", 9, 9) is None


def test_entries_get_by_entnum() -> None:
    doc = parse_enigma(FULL)
    entry = doc.entries.get(1)
    assert entry is not None
    assert entry.fields["dura"] == "1024"
    assert doc.entries.get(999) is None


def test_texts_get_by_number_or_type() -> None:
    doc = parse_enigma(FULL)
    expression = doc.texts.get("expression", number=3)
    assert expression is not None
    assert expression.fields["t"] == "cresc."
    file_info = doc.texts.get("fileInfo", type="title")
    assert file_info is not None
    assert file_info.fields["t"] == "PLACEHOLDER"


def test_singleton_record_convenience() -> None:
    doc = parse_enigma(FULL)
    header_record = doc.header.record
    assert header_record is not None
    assert header_record.tag == "headerData"
    mappings_record = doc.mappings.record
    assert mappings_record is not None
    assert mappings_record.tag == "mapGroup"
    assert parse_enigma(_doc("<others/>")).header.record is None


def test_of_tag_still_works() -> None:
    doc = parse_enigma(FULL)
    assert len(doc.others.of_tag("measSpec")) == 3
    assert len(doc.others.records) == 7


def test_duplicate_identity_raises() -> None:
    dup = _doc(
        '<others><articDef cmper="1"><x>a</x></articDef>'
        '<articDef cmper="1"><x>b</x></articDef></others>'
    )
    with pytest.raises(MalformedEnigmaError, match="duplicate"):
        parse_enigma(dup)
