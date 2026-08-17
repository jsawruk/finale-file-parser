from __future__ import annotations

import pytest

from finale_file_parser.enigma import (
    PercussionAppearance,
    PercussionNote,
    percussion_notes,
)
from finale_file_parser.enigma.document import (
    DetailsPool,
    EnigmaDocument,
    EntriesPool,
    OptionsPool,
    OthersPool,
    Pool,
    Record,
    TextsPool,
)
from finale_file_parser.enigma.music import Entry, read_entry
from finale_file_parser.enigma.percussion import MalformedPercussionError

EMPTY: tuple[Record, ...] = ()


def _note(harm_lev: int) -> Record:
    return Record(
        tag="note",
        attrs={"id": "1"},
        text="",
        fields={"harmLev": str(harm_lev), "harmAlt": "0"},
    )


def _appearance_fields(harm_lev: str = "9") -> dict[str, str]:
    return {
        "harmLev": harm_lev,
        "percNoteType": "38",
        "dwholeNotehead": "250",
        "wholeNotehead": "119",
        "halfNotehead": "250",
        "closedNotehead": "207",
    }


def _document(
    *,
    routes: dict[int, str | None],
    definitions: dict[tuple[str, str], dict[str, str]],
    assignments: tuple[tuple[str, str, str], ...],
) -> EnigmaDocument:
    notes = (_note(0), _note(1))
    entry = Record(
        tag="entry",
        attrs={"entnum": "1", "prev": "0", "next": "0"},
        text="",
        fields={"numNotes": "2", "dura": "1024", "note": notes},
    )
    others: list[Record] = [
        Record(
            tag="measSpec",
            attrs={"cmper": "1"},
            text="",
            fields={"keySig": Record(tag="keySig", attrs={}, text="", fields={"key": "0"})},
        )
    ]
    details: list[Record] = []
    for staff, map_id in routes.items():
        frame = staff * 10
        others.extend(
            (
                Record(
                    tag="staffSpec",
                    attrs={"cmper": str(staff)},
                    text="",
                    fields={},
                ),
                Record(
                    tag="frameSpec",
                    attrs={"cmper": str(frame), "inci": "0"},
                    text="",
                    fields={"startEntry": "1", "endEntry": "1"},
                ),
                Record(
                    tag="playbackRoute",
                    attrs={"cmper": str(staff)},
                    text="",
                    fields={} if map_id is None else {"percMapRefID": map_id},
                ),
            )
        )
        details.append(
            Record(
                tag="gfhold",
                attrs={"cmper1": str(staff), "cmper2": "1"},
                text="",
                fields={"frame1": str(frame)},
            )
        )
    others.extend(
        Record(
            tag="percussionNoteInfo",
            attrs={"cmper": map_id, "inci": note_code},
            text="",
            fields=fields,
        )
        for (map_id, note_code), fields in definitions.items()
    )
    details.extend(
        Record(
            tag="percussionNoteCode",
            attrs={"entnum": "1", "inci": inci},
            text="",
            fields={"noteID": note_id, "noteCode": note_code},
        )
        for inci, note_id, note_code in assignments
    )
    return EnigmaDocument(
        version="test",
        header=Pool(records=EMPTY),
        mappings=Pool(records=EMPTY),
        options=OptionsPool(records=EMPTY),
        others=OthersPool(records=tuple(others)),
        details=DetailsPool(records=tuple(details)),
        entries=EntriesPool(records=(entry,)),
        texts=TextsPool(records=EMPTY),
    )


def test_resolves_the_selected_map_row_in_entry_note_order() -> None:
    document = _document(
        routes={1: "7"},
        definitions={("7", "42"): _appearance_fields()},
        assignments=(("1", "2", "42"),),
    )
    appearance = PercussionAppearance(
        harm_lev=9,
        percussion_type=38,
        double_whole_notehead=250,
        whole_notehead=119,
        half_notehead=250,
        closed_notehead=207,
    )
    assert percussion_notes(document) == {
        (1, 1): (None, PercussionNote(map_id=7, note_code=42, appearance=appearance))
    }


def test_multiple_assignments_decode_their_entry_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(
        routes={1: "7"},
        definitions={},
        assignments=(("0", "1", "42"), ("1", "2", "43")),
    )
    calls = 0

    def counted_read_entry(record: Record) -> Entry:
        nonlocal calls
        calls += 1
        return read_entry(record)

    monkeypatch.setattr(
        "finale_file_parser.enigma.percussion.read_entry",
        counted_read_entry,
    )

    assert percussion_notes(document) == {
        (1, 1): (
            PercussionNote(map_id=7, note_code=42, appearance=None),
            PercussionNote(map_id=7, note_code=43, appearance=None),
        )
    }
    assert calls == 1


def test_a_mirror_resolves_against_each_staffs_own_map() -> None:
    document = _document(
        routes={1: "7", 2: "8"},
        definitions={
            ("7", "42"): _appearance_fields("9"),
            ("8", "42"): _appearance_fields("12"),
        },
        assignments=(("0", "1", "42"),),
    )
    found = percussion_notes(document)
    first = found[(1, 1)][0]
    second = found[(1, 2)][0]
    assert first is not None and first.appearance is not None
    assert second is not None and second.appearance is not None
    assert first.appearance.harm_lev == 9
    assert second.appearance.harm_lev == 12


def test_an_ordinary_staff_does_not_turn_a_stale_code_into_percussion() -> None:
    document = _document(
        routes={1: None},
        definitions={("7", "42"): _appearance_fields()},
        assignments=(("0", "1", "42"),),
    )
    assert percussion_notes(document) == {}


def test_a_code_absent_from_the_selected_map_remains_explicitly_unresolved() -> None:
    document = _document(
        routes={1: "7"},
        definitions={},
        assignments=(("0", "1", "13"),),
    )
    assert percussion_notes(document) == {
        (1, 1): (PercussionNote(map_id=7, note_code=13, appearance=None), None)
    }


def test_rejects_a_non_integer_note_code() -> None:
    document = _document(
        routes={1: "7"},
        definitions={},
        assignments=(("0", "1", "not-an-integer"),),
    )
    with pytest.raises(MalformedPercussionError, match="noteCode is not an integer"):
        percussion_notes(document)


def test_rejects_inci_that_is_not_zero_based_note_id() -> None:
    document = _document(
        routes={1: "7"},
        definitions={},
        assignments=(("1", "1", "42"),),
    )
    with pytest.raises(MalformedPercussionError, match="inci=1 disagrees with noteID=1"):
        percussion_notes(document)


def test_rejects_a_note_id_outside_the_entry() -> None:
    document = _document(
        routes={1: "7"},
        definitions={},
        assignments=(("2", "3", "42"),),
    )
    with pytest.raises(MalformedPercussionError, match="noteID=3 outside entry 1"):
        percussion_notes(document)


def test_rejects_two_assignments_for_one_entry_note() -> None:
    document = _document(
        routes={1: "7"},
        definitions={},
        assignments=(("0", "1", "42"), ("1", "1", "43")),
    )
    with pytest.raises(MalformedPercussionError, match="duplicate percussion assignment"):
        percussion_notes(document)


def test_rejects_an_incomplete_selected_definition() -> None:
    fields = _appearance_fields()
    del fields["harmLev"]
    document = _document(
        routes={1: "7"},
        definitions={("7", "42"): fields},
        assignments=(("0", "1", "42"),),
    )
    with pytest.raises(MalformedPercussionError, match="harmLev is not an integer"):
        percussion_notes(document)


def test_rejects_a_duplicate_route_after_an_ordinary_route() -> None:
    document = _document(
        routes={1: None},
        definitions={},
        assignments=(("0", "1", "42"),),
    )
    document.others = OthersPool(
        records=(
            *document.others.records,
            Record(
                tag="playbackRoute",
                attrs={"cmper": "01"},
                text="",
                fields={"percMapRefID": "7"},
            ),
        )
    )
    with pytest.raises(MalformedPercussionError, match="duplicate percussion route"):
        percussion_notes(document)
