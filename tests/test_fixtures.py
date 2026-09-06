import hashlib

from conftest import path
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as ts

import build_specimens

EXPECTED = {
    "fixtures/trace.bin": (140, "ab3caadd338bbee547e68ffee2e9f0f324999a459001662ac0bae928a7dd2e11"),
    "fixtures/metrics.bin": (154, "634b6f36ca2371d1239b5a31bf596d692b630170c68a5eaac5695194267e5f86"),
    "fixtures/logs.bin": (106, "45fce92afc28ae539a28368a8b325f59ecda59f5b1bf4ffd84913172804f3028"),
    "fixtures/warmup/minimal_trace.otlp.bin": (61, "8bec03a38493bffe618c301cb49a32eb2209800d536ecbca89bc75b56f077bc5"),
    "fixtures/warmup/minimal_trace.grpc.bin": (66, "0238be035ce430364004196e8f16296937f0984d79fa239ef8287a686c1339ea"),
}


def test_fixture_sizes_and_hashes():
    for rel, (size, digest) in EXPECTED.items():
        with open(path(rel), "rb") as fh:
            data = fh.read()
        assert len(data) == size, rel
        assert hashlib.sha256(data).hexdigest() == digest, rel


def test_builders_reproduce_shipped_fixtures():
    for name, builder in (("trace", build_specimens.build_trace),
                          ("metrics", build_specimens.build_metrics),
                          ("logs", build_specimens.build_logs)):
        with open(path("fixtures", f"{name}.bin"), "rb") as fh:
            assert builder() == fh.read(), name


def test_warmup_grpc_frame_wraps_warmup_body():
    with open(path("fixtures/warmup/minimal_trace.grpc.bin"), "rb") as fh:
        framed = fh.read()
    with open(path("fixtures/warmup/minimal_trace.otlp.bin"), "rb") as fh:
        body = fh.read()
    assert framed[0] == 0
    assert int.from_bytes(framed[1:5], "big") == len(body) == 61
    assert framed[5:] == body


def test_trace_specimen_semantics():
    req = ts.ExportTraceServiceRequest()
    with open(path("fixtures/trace.bin"), "rb") as fh:
        req.ParseFromString(fh.read())
    span = req.resource_spans[0].scope_spans[0].spans[0]
    assert span.trace_id.hex() == "5b8efff798038103d269b633813fc60c"
    assert span.span_id.hex() == "eee19b7ec3c1b174"
    assert span.name == "GET /cart" and span.kind == 2 and span.status.code == 1
    assert span.end_time_unix_nano - span.start_time_unix_nano == 12_500_000
    assert req.resource_spans[0].resource.attributes[0].key == "service.name"
