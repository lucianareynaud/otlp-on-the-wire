import json

import pytest
from conftest import path
from google.protobuf import json_format

from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as ts

import bench_batch
from otlp_json import OTLPJSONError, decode


def _specimen():
    with open(path("fixtures/trace.bin"), "rb") as fh:
        return fh.read()


def _otlp_json_doc():
    req = ts.ExportTraceServiceRequest()
    req.ParseFromString(_specimen())
    return json.loads(bench_batch.otlp_json(req))


def test_valid_otlp_json_round_trips_to_the_binary_specimen():
    decoded = decode(json.dumps(_otlp_json_doc()), ts.ExportTraceServiceRequest)
    span = decoded.resource_spans[0].scope_spans[0].spans[0]
    assert span.trace_id.hex() == "5b8efff798038103d269b633813fc60c"
    assert span.span_id.hex() == "eee19b7ec3c1b174"
    assert span.kind == 2 and span.status.code == 1
    assert decoded.SerializeToString() == _specimen()


def test_generic_protojson_parser_silently_corrupts_hex_ids():
    generic = json_format.Parse(json.dumps(_otlp_json_doc()), ts.ExportTraceServiceRequest())
    span = generic.resource_spans[0].scope_spans[0].spans[0]
    assert len(span.trace_id) == 24 and len(span.span_id) == 12   # hex read as base64


def test_base64_ids_are_rejected():
    doc = _otlp_json_doc()
    doc["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"] = "W47/95gDgQPSabYzgT/GDA=="
    with pytest.raises(OTLPJSONError, match="32 hex characters"):
        decode(json.dumps(doc), ts.ExportTraceServiceRequest)


def test_enum_names_are_rejected():
    doc = _otlp_json_doc()
    doc["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["kind"] = "SPAN_KIND_SERVER"
    with pytest.raises(OTLPJSONError, match="enums as integers"):
        decode(json.dumps(doc), ts.ExportTraceServiceRequest)


def test_snake_case_field_names_are_rejected_and_unknown_fields_ignored():
    doc = _otlp_json_doc()
    span = doc["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    span["futureField"] = {"anything": 1}
    decode(json.dumps(doc), ts.ExportTraceServiceRequest)
    span["trace_id"] = span.pop("traceId")
    with pytest.raises(OTLPJSONError, match="lowerCamelCase"):
        decode(json.dumps(doc), ts.ExportTraceServiceRequest)


def test_int64_accepts_decimal_string_and_integer():
    doc = _otlp_json_doc()
    span = doc["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    span["startTimeUnixNano"] = 1788696000000000000
    decoded = decode(json.dumps(doc), ts.ExportTraceServiceRequest)
    assert decoded.SerializeToString() == _specimen()


def test_protojson_surface_is_inherited_null_exponent_and_urlsafe_base64():
    doc = _otlp_json_doc()
    span = doc["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    span["traceState"] = None                        # null leaves the field unset
    span["droppedAttributesCount"] = "1e2"            # exponent notation is valid ProtoJSON for integers
    span["attributes"].append({"key": "blob", "value": {"bytesValue": "__8"}})   # URL-safe base64, no padding
    decoded = decode(json.dumps(doc), ts.ExportTraceServiceRequest)
    s = decoded.resource_spans[0].scope_spans[0].spans[0]
    assert s.trace_state == "" and s.dropped_attributes_count == 100
    assert s.attributes[1].value.bytes_value == b"\xff\xff"


def test_exponent_notation_on_a_nanosecond_timestamp_loses_precision():
    doc = _otlp_json_doc()
    doc["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["endTimeUnixNano"] = "1.7886960000125e18"
    decoded = decode(json.dumps(doc), ts.ExportTraceServiceRequest)
    end = decoded.resource_spans[0].scope_spans[0].spans[0].end_time_unix_nano
    assert end != 1788696000012500000 and abs(end - 1788696000012500000) < 256   # ProtoJSON parses it via a double


def test_invalid_protojson_is_reported_as_otlp_json_error():
    doc = _otlp_json_doc()
    doc["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["startTimeUnixNano"] = "not-a-number"
    with pytest.raises(OTLPJSONError, match="ProtoJSON"):
        decode(json.dumps(doc), ts.ExportTraceServiceRequest)
