"""Builds the deliberately broken fixtures under failures/ from fixtures/trace.bin.

Each file is the canonical 140-byte specimen with exactly one thing wrong, so a
reader can predict the failure before running a decoder on it. See
failures/README.md for what each one teaches.
"""
from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "fixtures", "trace.bin")
OUT = os.path.join(ROOT, "failures")


def grpc_frame(flag: int, declared_len: int, body: bytes) -> bytes:
    return bytes([flag]) + declared_len.to_bytes(4, "big") + body


def main() -> None:
    with open(SRC, "rb") as fh:
        body = fh.read()
    assert len(body) == 140 and body[0x30] == 0x10 and body[0x58] == 0x39
    os.makedirs(OUT, exist_ok=True)
    files = {
        "grpc-bad-length.bin": grpc_frame(0, len(body) - 1, body),
        "grpc-compressed-flag-without-encoding.bin": grpc_frame(1, len(body), body),
        "trace-idlen-0f.bin": body[:0x30] + b"\x0f" + body[0x31:],
        "trace-wiretype-3a.bin": body[:0x58] + b"\x3a" + body[0x59:],
        "trace-truncated-100.bin": body[:100],
        "wrong-content-type-json.request.bin": (
            b"POST /v1/traces HTTP/1.1\r\nHost: collector:4318\r\n"
            b"Content-Type: application/json\r\nContent-Length: 140\r\n\r\n" + body
        ),
        "unsupported-content-type.request.bin": (
            b"POST /v1/traces HTTP/1.1\r\nHost: collector:4318\r\n"
            b"Content-Type: application/octet-stream\r\nContent-Length: 140\r\n\r\n" + body
        ),
        "wrong-signal-route.request.bin": (
            b"POST /v1/metrics HTTP/1.1\r\nHost: collector:4318\r\n"
            b"Content-Type: application/x-protobuf\r\nContent-Length: 140\r\n\r\n" + body
        ),
    }
    for name, data in files.items():
        with open(os.path.join(OUT, name), "wb") as fh:
            fh.write(data)
        print(f"{name}: {len(data)} bytes")


if __name__ == "__main__":
    main()
