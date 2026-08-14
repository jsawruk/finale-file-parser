# Hex highlighting and per-field decoding in the inspector

**Goal:** the record pane tints each known field's byte range and shows what it
decodes to, the way `docs/formats/finale-formats.pdf` renders a struct.

**Status:** scoped, not started. Investigation below is done — start at Task 1.

## What already exists

`scripts/format_spec/hexview.py` defines the model and the rendering:

```python
@dataclass(frozen=True)
class Field:
    offset: int
    size: int
    name: str
    type_: str
    note: str = ""

@dataclass
class Struct:
    name: str
    fields: list[Field]
    data: bytes          # example bytes, for the PDF only
    caption: str = ""
    notes: list[str] = ...
```

`render_struct_table` already keys a field table to a tinted hex dump by
`PALETTE[i % len(PALETTE)]`. **The tinting logic is written**; what is missing is
the library being able to reach it.

Sixteen structs exist. Nine are record payload layouts, in
`scripts/format_spec/catalog.py`:

| Struct | Record |
| --- | --- |
| `MeasSpec` | measSpec |
| `FrameSpec` | frameSpec |
| `GfHold` | gfhold |
| `StaffSpec` | staffSpec |
| `TupletDef` | tupletDef |
| `StaffGroup` | staffGroup |
| `LyricVerseSlot` | lyric verse |
| `ArticAssign` | articAssign |
| `InstUsedSlot` | instUsed |

Seven are container-level and are NOT record payloads, in `content.py`:
`MusFileHeader`, `DclPoolRecord`, `MusRecord2011`, `DclOthersRow`,
`DclDetailsRow`, `EntrySlotFirst`, `NoteRec`.

## Coverage, stated honestly up front

Nine layouts against **146 `others` tags and 41 `details` tags** in
`2_Aura Lee.mus` alone. Most records will stay plain hex, and that is correct —
those are the ones whose layout this project does not claim to know. The pane
must therefore look deliberate when it has no layout, not broken.

## Tasks

### Task 1: move the layout model into the package

Create `src/finale_file_parser/formats/layouts.py` holding `Field`, `Struct`
(without `data`, which is a PDF concern) and the nine record layouts, keyed by
the tag they describe. Then have `scripts/format_spec/` import from it, keeping
its `data` examples where they are.

**Verify:** `make spec` output is byte-identical to what is committed. The build
is reproducible, so any diff at all means the move changed the document.

### Task 2: attach spans to a record

In `report/model.py`, when a record's tag has a layout, add to its entry the
field spans: `[{offset, size, name, type, note}]`. Do NOT add decoded values
here — the renderer reads them off the bytes it already has, and duplicating
them would repeat the payload in the JSON. Watch the 16 MB budget: it was
already tripped once this branch by carrying XML alongside fields.

### Task 3: tint the hex and key the table

In `report/html.py`, `hexBlock` currently emits one `<span>` per row. Emit one
per field instead, tinted from the same palette the PDF uses, with the
unclaimed bytes untinted. Below it, the field table: swatch, offset span, size,
type, name, decoded value, note.

Decode in the renderer from the bytes: `u8`/`u16`/`u32` little-endian, signed
where `type_` says so. A `.mus` byte order is per-document — check
`MusPool.byte_order` rather than assuming little.

### Task 4: name the tag

The same catalogue carries names and descriptions for 68 tags. Show the record
type's name and one-line description in the panel heading, so
`others / &a / 48/0` reads as something. This is the change most likely to
answer "I do not know what any of this means".

## Also open, same area

Records sharing a key render identically in the tree — several rows read
`65534/0`. Only visible on a real corpus document; the synthetic fixture hid it.
Distinguish them by incidence or position.
