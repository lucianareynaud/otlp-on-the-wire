# failures/

Each file is `fixtures/trace.bin` with exactly one thing wrong. Predict the failure before running a decoder, then check. Regenerate with `python3 tools/make_failures.py`.

| File | What is wrong | What you should observe |
|------|---------------|-------------------------|
| `grpc-bad-length.bin` | gRPC Message-Length says 139, body is 140 bytes | A framing error before any Protobuf error: the receiver hands 139 bytes to the parser, which fails on the truncated last record (`18` with no value), and the leftover `01` becomes the first byte of a 5-byte prefix that never completes — the stream stalls waiting for four more bytes. |
| `grpc-compressed-flag-without-encoding.bin` | Compressed-Flag = 1, no `grpc-encoding` header, body uncompressed | Protocol violation per PROTOCOL-HTTP2.md ("if the Message-Encoding header is omitted then the Compressed-Flag must be 0"). Gunzip fails: `BadGzipFile`. |
| `trace-idlen-0f.bin` | `Span.trace_id` length byte `10` → `0f` at offset 0x30 | The 16th id byte (`0c`) becomes a tag: field 1, wire type 4 (end-group). The reference parser raises `DecodeError`; `rawdecode` shows the Span payload is no longer a well-formed candidate. |
| `trace-wiretype-3a.bin` | `39` → `3a` at offset 0x58: start_time tag becomes field 7, LEN | **Parses successfully.** `3a 00` is an empty LEN field 7; `80 29 …` becomes unknown field 656 and is skipped; `end_time` still decodes. The span is structurally valid with `start_time_unix_nano = 0`. Corruption that produces wrong data, not an error. |
| `trace-truncated-100.bin` | First 100 of 140 bytes | `LEN field 1 declares 137 bytes, only 97 remain`. Both parsers reject it; this is what a truncated TCP stream looks like at the Protobuf layer. |
| `wrong-content-type-json.request.bin` | Raw OTLP/HTTP request with `Content-Type: application/json` and a Protobuf body | Not a media-type error: JSON is a supported OTLP/HTTP encoding, so the receiver runs the JSON decoder, `0a` is not JSON, and the Bad Data rule applies — `400 Bad Request` with a `google.rpc.Status` body in the request's encoding (JSON here), not retryable. |
| `unsupported-content-type.request.bin` | The same request with `Content-Type: application/octet-stream` | The media-type error: no OTLP decoder matches; the spec leaves this to HTTP semantics and the conventional answer is `415 Unsupported Media Type`, rejected before any payload decoding. Negotiation failure and decoding failure are different layers. |
| `wrong-signal-route.request.bin` | The trace body POSTed to `/v1/metrics` | The metrics parser raises `DecodeError`: the 16 `trace_id` bytes land in `Metric.name`, a `string`, and `8e` is not valid UTF-8. The structure was compatible; the string validation was not. |

Oversized request: not shipped as a file (it is 4.7 MiB). `tests/test_envelopes.py` builds a 30 000-span batch and shows a default grpcio server returning `RESOURCE_EXHAUSTED`, then the same request accepted with `grpc.max_receive_message_length` raised to 64 MiB.
