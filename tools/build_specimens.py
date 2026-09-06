"""Builds the three OTLP specimens used in "OTLP on the Wire".

Writes trace.bin, metrics.bin, logs.bin and prints a hex dump of each.
Requires: pip install opentelemetry-proto protobuf
"""
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as ts
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2 as ms
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2 as ls
from opentelemetry.proto.trace.v1 import trace_pb2 as tr
from opentelemetry.proto.metrics.v1 import metrics_pb2 as me
from opentelemetry.proto.logs.v1 import logs_pb2 as lg

TRACE_ID = bytes.fromhex("5b8efff798038103d269b633813fc60c")
SPAN_ID = bytes.fromhex("eee19b7ec3c1b174")
T0 = 1788696000000000000  # 2026-09-06T12:00:00Z in ns


def hexdump(data: bytes) -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hexpart = " ".join(f"{b:02x}" for b in chunk).ljust(48)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:08x}  {hexpart}  {asc}")
    return "\n".join(lines)


def add_resource_and_scope(resource_group, scope_group_attr: str):
    kv = resource_group.resource.attributes.add()
    kv.key = "service.name"
    kv.value.string_value = "checkout"
    scope_group = getattr(resource_group, scope_group_attr).add()
    scope_group.scope.name = "manual"
    return scope_group


def build_trace() -> bytes:
    req = ts.ExportTraceServiceRequest()
    scope = add_resource_and_scope(req.resource_spans.add(), "scope_spans")
    span = scope.spans.add()
    span.trace_id = TRACE_ID
    span.span_id = SPAN_ID
    span.name = "GET /cart"
    span.kind = tr.Span.SPAN_KIND_SERVER
    span.start_time_unix_nano = T0
    span.end_time_unix_nano = T0 + 12_500_000
    attr = span.attributes.add()
    attr.key = "http.request.method"
    attr.value.string_value = "GET"
    span.status.code = tr.Status.STATUS_CODE_OK
    return req.SerializeToString()


def build_metrics() -> bytes:
    req = ms.ExportMetricsServiceRequest()
    scope = add_resource_and_scope(req.resource_metrics.add(), "scope_metrics")
    metric = scope.metrics.add()
    metric.name = "http.server.request.count"
    metric.unit = "{request}"
    metric.sum.aggregation_temporality = me.AGGREGATION_TEMPORALITY_CUMULATIVE
    metric.sum.is_monotonic = True
    point = metric.sum.data_points.add()
    point.start_time_unix_nano = T0 - 60_000_000_000
    point.time_unix_nano = T0
    point.as_int = 42
    attr = point.attributes.add()
    attr.key = "http.response.status_code"
    attr.value.int_value = 200
    return req.SerializeToString()


def build_logs() -> bytes:
    req = ls.ExportLogsServiceRequest()
    scope = add_resource_and_scope(req.resource_logs.add(), "scope_logs")
    record = scope.log_records.add()
    record.time_unix_nano = T0 + 5_000_000
    record.severity_number = lg.SEVERITY_NUMBER_INFO
    record.severity_text = "INFO"
    record.body.string_value = "cart loaded"
    record.trace_id = TRACE_ID
    record.span_id = SPAN_ID
    return req.SerializeToString()


if __name__ == "__main__":
    for name, builder in (("trace", build_trace), ("metrics", build_metrics), ("logs", build_logs)):
        data = builder()
        with open(f"{name}.bin", "wb") as fh:
            fh.write(data)
        print(f"== {name}.bin  ({len(data)} bytes)")
        print(hexdump(data))
        print()
