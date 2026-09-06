"""Walks an OTLP capture layer by layer: TCP → HTTP/1.1 or HTTP/2 → gRPC → Protobuf.

Usage: python3 wirewalk.py <capture.pcap> [--protobuf]

For port 4318 the tool prints the HTTP/1.1 request head and the response head
and hands the body to the schemaless Protobuf walker. For port 4317 it prints
the HTTP/2 connection preface, every frame with its 9-byte header decoded,
HPACK-decoded HEADERS (including trailers), and, inside DATA frames, the gRPC
Length-Prefixed-Message prefix; uncompressed messages and gzip-compressed
messages are then walked as Protobuf. Pass --protobuf to include the full
record walk; by default the report stops at the gRPC prefix so the envelope is
readable on its own.

The capture must be plaintext (h2c / http). Requires: scapy hpack.
"""
from __future__ import annotations

import gzip
import os
import sys

from hpack import Decoder
from scapy.all import IP, TCP, Raw, rdpcap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rawdecode import WireError, walk  # noqa: E402

PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
FRAME_TYPES = {
    0x0: "DATA", 0x1: "HEADERS", 0x2: "PRIORITY", 0x3: "RST_STREAM", 0x4: "SETTINGS",
    0x5: "PUSH_PROMISE", 0x6: "PING", 0x7: "GOAWAY", 0x8: "WINDOW_UPDATE", 0x9: "CONTINUATION",
}
FLAG_NAMES = {
    "DATA": {0x1: "END_STREAM", 0x8: "PADDED"},
    "HEADERS": {0x1: "END_STREAM", 0x4: "END_HEADERS", 0x8: "PADDED", 0x20: "PRIORITY"},
    "SETTINGS": {0x1: "ACK"},
    "PING": {0x1: "ACK"},
    "CONTINUATION": {0x4: "END_HEADERS"},
}
SETTINGS_NAMES = {1: "HEADER_TABLE_SIZE", 2: "ENABLE_PUSH", 3: "MAX_CONCURRENT_STREAMS",
                  4: "INITIAL_WINDOW_SIZE", 5: "MAX_FRAME_SIZE", 6: "MAX_HEADER_LIST_SIZE"}
GRPC_STATUS = {"0": "OK", "1": "CANCELLED", "2": "UNKNOWN", "3": "INVALID_ARGUMENT", "4": "DEADLINE_EXCEEDED",
               "8": "RESOURCE_EXHAUSTED", "12": "UNIMPLEMENTED", "13": "INTERNAL", "14": "UNAVAILABLE", "16": "UNAUTHENTICATED"}


def reassemble(pcap_path: str, ports=(4317, 4318)):
    """Return {(src, sport, dst, dport): bytes} with duplicate segments removed."""
    streams: dict[tuple, dict[int, bytes]] = {}
    for pkt in rdpcap(pcap_path):
        if not (pkt.haslayer(TCP) and pkt.haslayer(Raw)):
            continue
        tcp = pkt[TCP]
        if tcp.sport not in ports and tcp.dport not in ports:
            continue
        key = (pkt[IP].src, tcp.sport, pkt[IP].dst, tcp.dport)
        streams.setdefault(key, {})[tcp.seq] = bytes(pkt[Raw].load)
    out = {}
    for key, segs in streams.items():
        out[key] = b"".join(segs[s] for s in sorted(segs))
    return out


def flags_text(kind: str, flags: int) -> str:
    names = [n for bit, n in FLAG_NAMES.get(kind, {}).items() if flags & bit]
    return "|".join(names) if names else "-"


def walk_grpc_messages(buf: bytes, base: int, encoding: str | None, show_protobuf: bool) -> bytes:
    """Consume complete Length-Prefixed-Messages from buf; return the unconsumed tail."""
    i = 0
    while i + 5 <= len(buf):
        flag = buf[i]
        length = int.from_bytes(buf[i + 1:i + 5], "big")
        if i + 5 + length > len(buf):
            break
        print(f"      gRPC Length-Prefixed-Message @{base + i}: flag={flag:02x} length={buf[i + 1:i + 5].hex()} -> {length}")
        message = buf[i + 5:i + 5 + length]
        if length == 0:
            print("      (empty message: ExportTraceServiceResponse with no fields serializes to zero bytes)")
        elif flag == 1:
            if encoding == "gzip":
                raw = gzip.decompress(message)
                print(f"      compressed with grpc-encoding: gzip; {length} bytes -> {len(raw)} bytes after gunzip")
                message = raw
            else:
                print(f"      compressed flag set but grpc-encoding is {encoding!r}: protocol violation")
                message = b""
        if message and show_protobuf:
            print("      Protobuf:")
            try:
                walk(message, 0, 4, 12)
            except WireError as exc:
                print(f"      ERROR {exc}")
        elif message:
            print(f"      Protobuf message: {len(message)} bytes, first bytes {message[:8].hex()} ...")
        i += 5 + length
    return buf[i:]


def walk_http2(direction: str, buf: bytes, show_protobuf: bool) -> None:
    decoder = Decoder()
    pos = 0
    if buf.startswith(PREFACE):
        print(f"  [{direction}] connection preface: {PREFACE!r} ({len(PREFACE)} bytes)")
        pos = len(PREFACE)
    data_pending: dict[int, bytes] = {}
    encodings: dict[int, str | None] = {}
    while pos + 9 <= len(buf):
        length = int.from_bytes(buf[pos:pos + 3], "big")
        ftype = buf[pos + 3]
        flags = buf[pos + 4]
        stream = int.from_bytes(buf[pos + 5:pos + 9], "big") & 0x7FFFFFFF
        kind = FRAME_TYPES.get(ftype, f"0x{ftype:02x}")
        header = buf[pos:pos + 9]
        payload = buf[pos + 9:pos + 9 + length]
        print(f"  [{direction}] frame @{pos}: {header.hex()}  len={length} type={kind} flags={flags_text(kind, flags)} stream={stream}")
        if kind == "SETTINGS" and length:
            for k in range(0, length, 6):
                ident = int.from_bytes(payload[k:k + 2], "big")
                val = int.from_bytes(payload[k + 2:k + 6], "big")
                print(f"      {SETTINGS_NAMES.get(ident, ident)} = {val}")
        elif kind == "WINDOW_UPDATE":
            print(f"      increment = {int.from_bytes(payload, 'big') & 0x7FFFFFFF}")
        elif kind in ("HEADERS", "CONTINUATION"):
            body = payload
            if kind == "HEADERS" and flags & 0x20:
                body = body[5:]
            if flags & 0x8:
                body = body[1:len(body) - body[0]]
            try:
                for name, value in decoder.decode(body):
                    name = name.decode() if isinstance(name, bytes) else name
                    value = value.decode() if isinstance(value, bytes) else value
                    note = ""
                    if name == "grpc-status":
                        note = f"   ({GRPC_STATUS.get(value, '?')})"
                    if name == "grpc-encoding":
                        encodings[stream] = value
                    print(f"      {name}: {value}{note}")
            except Exception as exc:  # hpack raises on state mismatch when a stream is missing
                print(f"      (HPACK decode failed: {exc})")
            if kind == "HEADERS" and flags & 0x1 and stream in data_pending:
                pass
        elif kind == "DATA":
            body = payload
            if flags & 0x8:
                body = body[1:len(body) - body[0]]
            buffered = data_pending.get(stream, b"") + body
            data_pending[stream] = walk_grpc_messages(buffered, 0, encodings.get(stream), show_protobuf)
        pos += 9 + length
    if pos != len(buf):
        print(f"  [{direction}] {len(buf) - pos} trailing bytes not parsed")


def walk_http1(direction: str, buf: bytes, show_protobuf: bool) -> None:
    head, _, body = buf.partition(b"\r\n\r\n")
    print(f"  [{direction}] head ({len(head) + 4} bytes):")
    for line in head.split(b"\r\n"):
        print(f"      {line.decode('latin-1')}")
    if body:
        print(f"  [{direction}] body: {len(body)} bytes, first bytes {body[:8].hex()} ...")
        if show_protobuf:
            print("      Protobuf:")
            try:
                walk(body, 0, 4, 12)
            except WireError as exc:
                print(f"      ERROR {exc}")
    else:
        print(f"  [{direction}] body: 0 bytes")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    show_protobuf = "--protobuf" in argv
    streams = reassemble(argv[0])
    if not streams:
        print("no TCP payload on ports 4317/4318 in this capture")
        return 1
    for (src, sport, dst, dport), data in sorted(streams.items(), key=lambda kv: kv[0][3] in (4317, 4318), reverse=True):
        direction = "client->server" if dport in (4317, 4318) else "server->client"
        print(f"\n== {src}:{sport} -> {dst}:{dport}  ({direction}, {len(data)} payload bytes)")
        if 4317 in (sport, dport):
            walk_http2(direction, data, show_protobuf)
        else:
            walk_http1(direction, data, show_protobuf)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
