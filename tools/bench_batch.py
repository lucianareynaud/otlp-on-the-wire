"""Measures OTLP payload size as a function of batch size and encoding.

Usage: python3 bench_batch.py [--csv]

Builds ExportTraceServiceRequests holding N synthetic spans (N in SIZES) under
one resource and one scope, with three attributes per span, using a seeded
generator so every run yields identical bytes. For each N it reports the
Protobuf size, the gzip -9 size, the OTLP/JSON size (spec encoding: hex ids,
integer enums, decimal-string int64), and the JSON gzip size. The synthetic
spans are deliberately favourable to compression (four span names, one HTTP
method, low-cardinality status codes); the numbers are an upper bound on
compressibility, not a forecast for any real workload.
"""
from __future__ import annotations

import gzip
import json
import random
import sys

from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as ts

SIZES = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)
NAMES = ("GET /cart", "POST /checkout", "GET /items/{id}", "GET /health")
T0 = 1788696000000000000


def build_batch(n: int, seed: int = 7) -> ts.ExportTraceServiceRequest:
    rng = random.Random(seed)
    req = ts.ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    kv = rs.resource.attributes.add()
    kv.key = "service.name"
    kv.value.string_value = "checkout"
    sc = rs.scope_spans.add()
    sc.scope.name = "manual"
    for i in range(n):
        span = sc.spans.add()
        span.trace_id = rng.randbytes(16)
        span.span_id = rng.randbytes(8)
        span.name = rng.choice(NAMES)
        span.kind = 2
        span.start_time_unix_nano = T0 + i * 1_000_000
        span.end_time_unix_nano = span.start_time_unix_nano + rng.randint(1, 50) * 1_000_000
        a = span.attributes.add()
        a.key = "http.request.method"
        a.value.string_value = "GET"
        a = span.attributes.add()
        a.key = "http.response.status_code"
        a.value.int_value = rng.choice((200, 200, 200, 404, 500))
        a = span.attributes.add()
        a.key = "url.path"
        a.value.string_value = span.name.split(" ")[1]
        span.status.code = 1
    return req


def otlp_json(req: ts.ExportTraceServiceRequest) -> bytes:
    """OTLP/JSON per spec: lowerCamelCase keys, hex ids, integer enums, int64 as strings."""
    def kv_list(kvs):
        out = []
        for kv in kvs:
            which = kv.value.WhichOneof("value")
            if which == "string_value":
                v = {"stringValue": kv.value.string_value}
            elif which == "int_value":
                v = {"intValue": str(kv.value.int_value)}
            else:
                raise NotImplementedError(which)
            out.append({"key": kv.key, "value": v})
        return out

    doc = {"resourceSpans": []}
    for rs in req.resource_spans:
        rs_doc = {"resource": {"attributes": kv_list(rs.resource.attributes)}, "scopeSpans": []}
        for sc in rs.scope_spans:
            sc_doc = {"scope": {"name": sc.scope.name}, "spans": []}
            for s in sc.spans:
                sc_doc["spans"].append({
                    "traceId": s.trace_id.hex(),
                    "spanId": s.span_id.hex(),
                    "name": s.name,
                    "kind": s.kind,
                    "startTimeUnixNano": str(s.start_time_unix_nano),
                    "endTimeUnixNano": str(s.end_time_unix_nano),
                    "attributes": kv_list(s.attributes),
                    "status": {"code": s.status.code},
                })
            rs_doc["scopeSpans"].append(sc_doc)
        doc["resourceSpans"].append(rs_doc)
    return json.dumps(doc, separators=(",", ":")).encode()


def gz(b: bytes) -> int:
    return len(gzip.compress(b, 9))


def main(argv: list[str]) -> int:
    csv = "--csv" in argv
    rows = []
    for n in SIZES:
        req = build_batch(n)
        pb = req.SerializeToString()
        js = otlp_json(req)
        rows.append((n, len(pb), gz(pb), len(js), gz(js)))
    if csv:
        print("spans,protobuf_bytes,protobuf_gzip_bytes,json_bytes,json_gzip_bytes")
        for r in rows:
            print(",".join(str(x) for x in r))
        return 0
    print(f"{'spans':>6} {'protobuf':>9} {'B/span':>7} {'pb gzip':>8} {'ratio':>6} {'json':>8} {'json/pb':>7} {'json gzip':>9}")
    for n, pb, pbz, js, jsz in rows:
        print(f"{n:>6} {pb:>9} {pb / n:>7.1f} {pbz:>8} {pb / pbz:>6.2f} {js:>8} {js / pb:>7.2f} {jsz:>9}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
