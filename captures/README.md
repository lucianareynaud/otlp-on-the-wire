# captures/

Real traffic recorded on the loopback interface by `tools/capture_lab.py` (scapy sniffer on the loopback interface: `lo` on Linux, `lo0` on macOS). Every byte was produced by the client and server implementations named below; nothing is synthesized. Each `.pcap` has a `.walk.txt` companion produced by `tools/wirewalk.py --protobuf`, so the frames can be read without installing anything.

| Capture | Client | Server | What it shows |
|---------|--------|--------|---------------|
| `trace-http1-plaintext.pcap` | Python `urllib` POSTing `fixtures/trace.bin` | stdlib `http.server` receiver | `POST /v1/traces`, `Content-Type: application/x-protobuf`, `Content-Length: 140`, the 140-byte body verbatim, `200 OK` with `Content-Length: 0`. |
| `trace-grpc-h2c.pcap` | `grpcio` 1.83.1 generated `TraceServiceStub`, `Export(trace.bin)` | `grpcio` server | Connection preface, SETTINGS, HEADERS (`:path /opentelemetry.proto.collector.trace.v1.TraceService/Export`, `te: trailers`, `grpc-timeout`), DATA `000091 00 01 00000001` + `00 0000008c` + 140 bytes, response HEADERS `:status 200`, DATA `00 00000000` (empty response), trailers HEADERS `grpc-status: 0` with END_STREAM. |
| `trace-grpc-gzip.pcap` | same, `compression=grpc.Compression.Gzip` | same | `grpc-encoding: gzip` is declared in HEADERS, yet the DATA frame carries flag `00` and 140 uncompressed bytes: grpc-core skips compression when it would not shrink the message. The header names the algorithm; the per-message flag says whether it was applied. |
| `trace-sdk-grpc.pcap` | OpenTelemetry Python SDK 1.44.0 + `OTLPSpanExporter` (gRPC), span built to match the specimen | same | The real SDK payload is 146 bytes: the 140 of the specimen plus `85 01 00 01 00 00` — `Span.flags (16)`, fixed32 = 0x100 (HAS_IS_REMOTE set, IS_REMOTE clear, trace-flag bits zero). `user-agent: OTel-OTLP-Exporter-Python/1.44.0 grpc-python/1.83.1 …`. |

Read with Wireshark (Analyze → Decode As → port 4317 → HTTP2; load `opentelemetry-proto` under Protobuf search paths), with `tshark -r trace-grpc-h2c.pcap -Y 'http2.type == 0' -T fields -e http2.data.data`, or with `python3 tools/wirewalk.py captures/trace-grpc-h2c.pcap --protobuf`.
