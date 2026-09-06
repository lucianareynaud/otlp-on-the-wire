# OTLP on the Wire

**Reading the OpenTelemetry Protocol Byte by Byte**

[![test](https://github.com/lucianareynaud/otlp-on-the-wire/actions/workflows/test.yml/badge.svg)](https://github.com/lucianareynaud/otlp-on-the-wire/actions/workflows/test.yml)

`otlp-on-the-wire` is the public evidence layer for the project: deterministic OTLP fixtures, deliberately broken payloads, packet captures from real implementations, a schema-less Protobuf walker, an OTLP/JSON decoder, capture tooling, and a 41-test regression suite.

The full guided manuscript is distributed separately. This repository is intentionally sufficient to reproduce and verify the technical claims without containing the book.

## Six questions

Use the repository by asking the same six questions at every layer:

1. **What bytes are these?** Identify the exact byte range before assigning meaning.
2. **Who owns their meaning?** Protobuf wire grammar, an OTLP `.proto`, gRPC framing, HTTP/2, or HTTP semantics.
3. **Which layer added them?** Separate telemetry payload from message framing and transport framing.
4. **What breaks if they are wrong?** Distinguish framing errors, decode errors, semantic corruption, and routing errors.
5. **How do I prove it?** Close nested lengths, compare against generated parsers, and verify against captured traffic.
6. **What do they cost?** Measure envelope overhead, repeated attribute keys, batching, compression, and payload size.

## Start here

The shortest path through the repository is bottom-up:

1. `fixtures/trace.bin` — the canonical 140-byte `ExportTraceServiceRequest`.
2. `tools/build_specimens.py` — see exactly how the trace, metric, and log specimens are generated.
3. `tools/rawdecode.py` — walk Protobuf records without a schema and observe what the bytes alone cannot tell you.
4. [`docs/fixture-map.md`](docs/fixture-map.md) — reconcile the 140 bytes against the OTLP trace schema offset by offset.
5. `captures/trace-grpc-h2c.pcap` + `tools/wirewalk.py` — move outward from Protobuf to the 5-byte gRPC prefix and HTTP/2 frames.
6. `tools/capture_lab.py` — inspect the minimal OTLP/HTTP and gRPC endpoints used to record the captures.
7. `tools/otlp_json.py` — study the OTLP-specific deviations from ordinary ProtoJSON.
8. `fixtures/metrics.bin` and `fixtures/logs.bin` — compare the same Resource/Scope grouping across signals.
9. `failures/` — predict a fault at the correct layer before running the decoder.
10. `tools/bench_batch.py` — reproduce the payload-size and compression measurements.

For the system map, see [`docs/architecture.md`](docs/architecture.md). For clean-room reproduction, see [`docs/reproducing.md`](docs/reproducing.md).

## Quick start

```bash
make venv
make test
make decode
make walk
make bench
```

`make test` runs **41 tests** without root. The shipped PCAPs are read-only test inputs; `rdpcap` does not require raw-socket privileges. Only `make captures`, which re-records traffic from loopback, needs elevated privileges.

## Repository map

| Path | Purpose |
|---|---|
| `fixtures/` | Deterministic trace, metrics, logs, and warm-up OTLP binary specimens. |
| `failures/` | Eight single-fault variants with expected failure behavior. |
| `captures/` | Four packet captures plus decoded wire-walk reports. |
| `tools/` | Fixture builders, failure generator, benchmark, schema-less walker, capture walker, OTLP/JSON decoder, and capture lab. |
| `tests/` | 41 regression tests covering fixture hashes, wire arithmetic, failures, OTLP/JSON, HTTP semantics, gRPC limits, and captured bytes. |
| `docs/fixture-map.md` | Public offset-by-offset map of the canonical 140-byte trace fixture. |
| `docs/architecture.md` | Layer model and ownership boundaries. |
| `docs/reproducing.md` | Reproduction and verification procedure. |

## Reproducibility contract

The repository pins the library versions used to produce the shipped bytes. Rebuilding fixtures and failure cases must reproduce the checked-in artifacts exactly; the tests enforce their hashes and semantics. Benchmark results are seeded and regenerated from source.

The capture files are intentionally checked in. Tests read them without network access or root. Re-recording them is a separate operation because it exercises raw-socket capture on the loopback interface (`lo0` on macOS, `lo` on Linux; override with `OTLP_WIRE_IFACE`).

## Project boundary

This repository contains the **evidence and tooling**, not the full book. The public offset map is included because it is a directly verifiable reference artifact. The commercial manuscript contains the guided model-building, failure analysis, cross-signal interpretation, payload economics, and forward-looking protocol discussion around those artifacts.

## Citation

Citation metadata is in [`CITATION.cff`](CITATION.cff). GitHub will expose a “Cite this repository” action after publication.

Suggested short citation:

> Reynaud, Luciana. *OTLP on the Wire*. v1.0.0, 2026. https://github.com/lucianareynaud/otlp-on-the-wire

## License

Source code, tests, build tooling, workflows, and accompanying generated test artifacts are licensed under **Apache-2.0**; see [`LICENSE`](LICENSE).

Original public documentation is licensed under **CC BY 4.0**; see [`LICENSE-DOCS`](LICENSE-DOCS). The separately distributed book is not included in this repository and is not licensed under CC BY 4.0.
