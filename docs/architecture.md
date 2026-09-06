# Architecture

The repository is organized around one rule: **do not assign meaning to bytes until the layer that owns that meaning is explicit**.

## Layer model

```text
packet capture
└── TCP byte stream
    ├── HTTP/1.1 request/response
    │   └── OTLP/HTTP body
    │       └── Export*ServiceRequest Protobuf
    │
    └── HTTP/2 connection
        └── gRPC stream
            └── 5-byte Length-Prefixed-Message
                └── Export*ServiceRequest Protobuf
                    └── Resource* → Scope* → signal item
                        └── KeyValue / AnyValue
```

A failure is diagnosable only after locating the first layer whose contract no longer holds.

## Ownership boundaries

| Layer | Owns | Evidence in this repo |
|---|---|---|
| Protobuf wire format | tags, wire types, varints, LEN records, little-endian fixed fields | `tools/rawdecode.py`, `docs/fixture-map.md`, `tests/test_rawdecode.py` |
| OTLP schema | field numbers, message nesting, ids, timestamps, signal-specific types | `fixtures/`, generated OTel bindings used by builders/tests |
| OTLP/JSON | ProtoJSON plus OTLP-specific deviations | `tools/otlp_json.py`, `tests/test_otlp_json.py` |
| gRPC message framing | compressed flag + 4-byte big-endian message length | `captures/trace-grpc-*.pcap`, `tests/test_captures.py` |
| HTTP/2 | frame headers, SETTINGS, HPACK, DATA/HEADERS/trailers | `tools/wirewalk.py`, capture `.walk.txt` files |
| OTLP/HTTP | endpoint path, media type, HTTP response behavior | `tools/capture_lab.py`, `tests/test_http_receiver.py` |
| Operational limits | receiver message limits and wrong-signal routing | `tests/test_envelopes.py`, `failures/` |
| Payload economics | batch size, encoding size, gzip crossover | `tools/bench_batch.py`, `docs/bench_batch.csv` |

## Artifact flow

```text
tools/build_specimens.py
        │
        ├── fixtures/trace.bin
        ├── fixtures/metrics.bin
        └── fixtures/logs.bin
                │
                ├── tools/rawdecode.py
                ├── docs/fixture-map.md
                ├── tools/make_failures.py → failures/
                ├── tools/bench_batch.py → docs/bench_batch.{csv,txt}
                └── tools/capture_lab.py → captures/*.pcap
                                            │
                                            └── tools/wirewalk.py → *.walk.txt
```

Tests bind the graph together. A change to the specimen should force a deliberate update to its hash, offset map, derived failures, captures, and any benchmark output that depends on it.

## Failure isolation

The repository intentionally contains failures that look similar from the application layer but originate in different contracts:

- malformed Protobuf record or length;
- syntactically valid Protobuf with corrupted semantics;
- gRPC prefix/message-length disagreement;
- gRPC compression flag inconsistent with message encoding;
- supported media type with undecodable payload (`400`);
- unsupported media type (`415`);
- valid wire structure routed to the wrong OTLP signal parser;
- request larger than the receiver's configured gRPC message limit.

The diagnostic method is always the same: identify the first layer whose invariant fails, then stop blaming layers below it.

## Public/private boundary

The repository is the reproducible evidence surface. It deliberately contains the canonical byte map, because that artifact can be independently checked and cited. The full guided manuscript is a separate publication and is not stored in this repository.
