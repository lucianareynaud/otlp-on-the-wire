# Reproducing the repository

## Prerequisites

- macOS or Linux
- `python3`
- `git`
- `make`

Root privileges are **not** required for tests, decoding, benchmarks, or reading the shipped captures. They are required only to re-record packet captures.

## Clean environment

```bash
git clone https://github.com/lucianareynaud/otlp-on-the-wire.git
cd otlp-on-the-wire
make venv
```

The Makefile automatically uses `.venv/bin/python` after the environment exists.

## Run the release gate

```bash
make test
```

Expected result for v1.0.0:

```text
41 passed
```

The suite covers:

- fixture sizes, hashes, and deterministic regeneration;
- warm-up gRPC framing;
- canonical trace semantics and nested record arithmetic;
- schema-less parsing and deliberate malformed-wire cases;
- wrong-signal routing and gRPC receive limits;
- OTLP/JSON round-trip plus required rejections/deviations;
- OTLP/HTTP success/error encoding, `400` versus `415`, and `google.rpc.Status` bodies;
- byte sequences inside the checked-in HTTP/1.1, gRPC, gzip, and SDK captures.

## Rebuild deterministic artifacts

```bash
make specimens
make failures
make bench
```

Then verify that the working tree remains unchanged:

```bash
git diff --exit-code -- fixtures failures docs/bench_batch.csv docs/bench_batch.txt
```

A non-zero exit indicates that a supposedly deterministic artifact changed and must be investigated before release.

## Inspect the canonical trace

Schema-less record walk:

```bash
make decode
```

Public schema reconciliation:

```bash
cat docs/fixture-map.md
```

Raw hex on macOS:

```bash
xxd fixtures/trace.bin
```

## Inspect real transport bytes

```bash
make walk
```

This reads `captures/trace-grpc-h2c.pcap`, reconstructs the TCP stream, walks HTTP/2 and gRPC framing, and descends into the Protobuf message.

The shipped captures are sufficient for all tests and exercises. Reading a PCAP with Scapy does not require raw sockets.

## Re-record captures

Re-recording is intentionally outside the normal test path:

```bash
make captures
```

The command uses `sudo` because `tools/capture_lab.py` sniffs loopback traffic. Interface selection is:

- macOS: `lo0`
- Linux: `lo`
- override: `OTLP_WIRE_IFACE=<interface>`

Example on macOS:

```bash
OTLP_WIRE_IFACE=lo0 make captures
```

Capture bytes can differ across library or runtime versions even when application semantics are equivalent. Treat a capture change as evidence to inspect, not automatically as a regression.

## Verify release hashes

```bash
sha256sum fixtures/*.bin fixtures/warmup/*.bin
```

For v1.0.0 the expected values are recorded in `RELEASE_NOTES_v1.0.0.md` and `docs/fixture-map.md`.
