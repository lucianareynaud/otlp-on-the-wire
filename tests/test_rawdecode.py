import pytest
from conftest import path

from rawdecode import WireError, is_well_formed, parse_records, read_varint


def records(data: bytes):
    return list(parse_records(data))


def test_varint_examples():
    assert read_varint(b"\x89\x01", 0)[0] == 137
    assert read_varint(b"\xc8\x01", 0)[0] == 200
    assert read_varint(b"\xac\x02", 0)[0] == 300
    assert read_varint(b"\x96\x01", 0)[0] == 150


def test_trace_specimen_outer_structure():
    with open(path("fixtures/trace.bin"), "rb") as fh:
        data = fh.read()
    top = records(data)
    assert len(top) == 1
    offset, field, wt, tag_bytes, payload, length = top[0]
    assert (field, wt, tag_bytes.hex(), length) == (1, 2, "0a8901", 137)
    resource_spans = records(payload)
    assert [(f, wt, ln) for _, f, wt, _, _, ln in resource_spans] == [(1, 2, 28), (2, 2, 105)]
    scope_spans = records(resource_spans[1][4])
    assert [(f, ln) for _, f, _, _, _, ln in scope_spans] == [(1, 8), (2, 93)]
    span = records(scope_spans[1][4])
    assert [(f, wt) for _, f, wt, _, _, _ in span] == [(1, 2), (2, 2), (5, 2), (6, 0), (7, 1), (8, 1), (9, 2), (15, 2)]
    assert span[3][5] == 2                        # kind = SERVER
    assert span[4][5] == 1788696000000000000      # start_time, little-endian
    assert span[5][5] - span[4][5] == 12_500_000


def test_span_length_arithmetic():
    with open(path("fixtures/trace.bin"), "rb") as fh:
        data = fh.read()
    span = records(records(records(records(data)[0][4])[1][4])[1][4])
    record_sizes = [len(tag) + (len(payload) if wt != 0 else len(payload)) for _, _, wt, tag, payload, _ in span]
    assert record_sizes == [18, 10, 11, 2, 9, 9, 30, 4]
    assert sum(record_sizes) == 93


def test_ids_are_not_well_formed_messages():
    with open(path("fixtures/trace.bin"), "rb") as fh:
        data = fh.read()
    assert not is_well_formed(bytes.fromhex("5b8efff798038103d269b633813fc60c"))
    assert not is_well_formed(bytes.fromhex("eee19b7ec3c1b174"))
    assert is_well_formed(bytes.fromhex("0a066d616e75616c"))   # InstrumentationScope{name:"manual"} is ambiguous with an 8-byte id


def test_truncated_payload_is_detected():
    with open(path("failures/trace-truncated-100.bin"), "rb") as fh:
        data = fh.read()
    with pytest.raises(WireError, match="declares 137 bytes, only 97 remain"):
        records(data)


def test_corrupted_wire_type_parses_but_loses_the_timestamp():
    with open(path("failures/trace-wiretype-3a.bin"), "rb") as fh:
        data = fh.read()
    span = records(records(records(records(data)[0][4])[1][4])[1][4])
    fields = [(f, wt) for _, f, wt, _, _, _ in span]
    assert (7, 2) in fields and (656, 0) in fields and (7, 1) not in fields
