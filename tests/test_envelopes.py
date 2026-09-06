import gzip

import grpc
import pytest
from concurrent import futures
from conftest import path
from google.protobuf.message import DecodeError

from opentelemetry.proto.collector.logs.v1 import logs_service_pb2 as ls
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2 as ms
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as ts
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc as ts_grpc

import bench_batch


def test_grpc_bad_length_fixture_is_detectable():
    with open(path("failures/grpc-bad-length.bin"), "rb") as fh:
        framed = fh.read()
    declared = int.from_bytes(framed[1:5], "big")
    assert declared == 139 and len(framed) - 5 == 140


def test_compressed_flag_without_encoding_is_not_gzip():
    with open(path("failures/grpc-compressed-flag-without-encoding.bin"), "rb") as fh:
        framed = fh.read()
    assert framed[0] == 1
    with pytest.raises(gzip.BadGzipFile):
        gzip.decompress(framed[5:])


def test_trace_bytes_rejected_by_metrics_and_logs_parsers():
    with open(path("fixtures/trace.bin"), "rb") as fh:
        body = fh.read()
    with pytest.raises(DecodeError):
        ms.ExportMetricsServiceRequest().ParseFromString(body)
    with pytest.raises(DecodeError):
        ls.ExportLogsServiceRequest().ParseFromString(body)


def test_otlp_json_specimen_size_and_rules():
    req = ts.ExportTraceServiceRequest()
    with open(path("fixtures/trace.bin"), "rb") as fh:
        req.ParseFromString(fh.read())
    js = bench_batch.otlp_json(req)
    assert len(js) == 440
    assert b'"traceId":"5b8efff798038103d269b633813fc60c"' in js
    assert b'"kind":2' in js and b'"startTimeUnixNano":"1788696000000000000"' in js


def test_empty_response_serializes_to_zero_bytes():
    assert ts.ExportTraceServiceResponse().SerializeToString() == b""


class _Service(ts_grpc.TraceServiceServicer):
    def Export(self, request, context):
        return ts.ExportTraceServiceResponse()


def _serve(options):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1), options=options)
    ts_grpc.add_TraceServiceServicer_to_server(_Service(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    return server, port


def test_default_grpc_limit_rejects_oversized_request_as_resource_exhausted():
    big = bench_batch.build_batch(30000)           # ~4.7 MiB serialized
    assert len(big.SerializeToString()) > 4 * 1024 * 1024
    server, port = _serve(options=[])
    try:
        with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
            with pytest.raises(grpc.RpcError) as exc:
                ts_grpc.TraceServiceStub(channel).Export(big, timeout=30)
            assert exc.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
    finally:
        server.stop(grace=None)


def test_raised_grpc_limit_accepts_the_same_request():
    big = bench_batch.build_batch(30000)
    server, port = _serve(options=[("grpc.max_receive_message_length", 64 * 1024 * 1024)])
    try:
        with grpc.insecure_channel(f"127.0.0.1:{port}", options=[("grpc.max_send_message_length", 64 * 1024 * 1024)]) as channel:
            resp = ts_grpc.TraceServiceStub(channel).Export(big, timeout=30)
            assert resp.SerializeToString() == b""
    finally:
        server.stop(grace=None)
