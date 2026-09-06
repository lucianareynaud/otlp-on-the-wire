"""Schemaless Protobuf wire-format walker for "OTLP on the Wire".

Usage: python3 rawdecode.py <file.bin> [--depth N]

Prints every record with its absolute offset, tag bytes, field number, wire
type and value. A LEN record is ambiguous without a schema: the same bytes may
be a string, an opaque byte array (an id), or an embedded message. This tool
does not choose. For every LEN payload it prints the raw bytes, the UTF-8
rendering when the bytes are valid UTF-8, and the candidate sub-message walk
when the bytes parse as a well-formed record sequence. Reconciling the three
against the schema is the reader's job; docs/fixture-map.md is the public map.
"""
from __future__ import annotations

import sys

WIRE_TYPES = {0: "VARINT", 1: "I64", 2: "LEN", 5: "I32"}


class WireError(ValueError):
    pass


def read_varint(buf: bytes, i: int):
    shift, value, start = 0, 0, i
    while True:
        if i >= len(buf):
            raise WireError(f"truncated varint at offset {start:#x}")
        byte = buf[i]
        value |= (byte & 0x7F) << shift
        i += 1
        if not byte & 0x80:
            return value, i, buf[start:i]
        shift += 7
        if shift > 63:
            raise WireError(f"varint longer than 10 bytes at offset {start:#x}")


def parse_records(buf: bytes):
    """Yield (offset, field, wire_type, tag_bytes, payload_bytes, value) or raise WireError."""
    i = 0
    while i < len(buf):
        offset = i
        tag, j, tag_bytes = read_varint(buf, i)
        field, wire_type = tag >> 3, tag & 7
        if field == 0:
            raise WireError(f"field number 0 at offset {offset:#x}")
        if wire_type == 0:
            value, k, vb = read_varint(buf, j)
            yield offset, field, wire_type, tag_bytes, vb, value
            i = k
        elif wire_type == 1:
            if j + 8 > len(buf):
                raise WireError(f"truncated I64 at offset {offset:#x}")
            raw = buf[j:j + 8]
            yield offset, field, wire_type, tag_bytes, raw, int.from_bytes(raw, "little")
            i = j + 8
        elif wire_type == 5:
            if j + 4 > len(buf):
                raise WireError(f"truncated I32 at offset {offset:#x}")
            raw = buf[j:j + 4]
            yield offset, field, wire_type, tag_bytes, raw, int.from_bytes(raw, "little")
            i = j + 4
        elif wire_type == 2:
            length, k, lb = read_varint(buf, j)
            if k + length > len(buf):
                raise WireError(
                    f"LEN field {field} at offset {offset:#x} declares {length} bytes, only {len(buf) - k} remain"
                )
            yield offset, field, wire_type, tag_bytes + lb, buf[k:k + length], length
            i = k + length
        else:
            raise WireError(f"wire type {wire_type} (group) at offset {offset:#x} is not used by OTLP")


def is_well_formed(buf: bytes) -> bool:
    try:
        for _ in parse_records(buf):
            pass
        return True
    except WireError:
        return False


def walk(buf: bytes, base: int, depth: int, max_depth: int) -> None:
    indent = "  " * depth
    for offset, field, wt, tag_bytes, payload, value in parse_records(buf):
        abs_off = base + offset
        head = f"{abs_off:04x}  {indent}{tag_bytes.hex():<8} field={field:<3}{WIRE_TYPES[wt]:<7}"
        if wt == 0:
            print(f"{head} value={payload.hex()} -> {value}")
        elif wt == 1:
            print(f"{head} bytes={payload.hex()} -> u64 {value} (LE)")
        elif wt == 5:
            print(f"{head} bytes={payload.hex()} -> u32 {value} (LE)")
        else:
            print(f"{head} len={value}")
            payload_off = abs_off + len(tag_bytes)
            print(f"{'':6}{indent}  raw:  {payload.hex()}")
            try:
                text = payload.decode("utf-8")
                if all(32 <= ord(c) < 127 for c in text):
                    print(f"{'':6}{indent}  utf8: {text!r}")
            except UnicodeDecodeError:
                pass
            if value > 0 and is_well_formed(payload):
                print(f"{'':6}{indent}  candidate sub-message:")
                if depth < max_depth:
                    walk(payload, payload_off, depth + 2, max_depth)
                else:
                    print(f"{'':6}{indent}    (max depth reached)")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    path = argv[0]
    max_depth = 12
    if "--depth" in argv:
        max_depth = int(argv[argv.index("--depth") + 1])
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        walk(data, 0, 0, max_depth)
    except WireError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"{len(data):04x}  end ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
