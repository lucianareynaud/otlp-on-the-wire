"""OTLP/JSON decoder: the OTLP deviations on top of the standard ProtoJSON mapping.

Usage as a library:

    from otlp_json import decode
    request = decode(json_bytes, ts.ExportTraceServiceRequest)

Usage from the shell:

    python3 otlp_json.py <request.json> [trace|metrics|logs]   → prints the binary size and hex

OTLP/JSON is defined as the proto3 canonical JSON mapping ("ProtoJSON") plus a
small set of deviations (specification.md, "JSON Protobuf Encoding"): trace_id,
span_id and parent_span_id are hex strings rather than base64; enum values are
integers, never names; field names are lowerCamelCase only; unknown fields are
ignored. Everything else — null leaving a field unset, 64-bit integers as
numbers or strings including exponent notation, ordinary `bytes` fields as
standard or URL-safe base64, special floats, repeated fields, oneofs — is
ProtoJSON and is left to google.protobuf.json_format.

This module therefore does two things and nothing more: it walks the document
against the message descriptors to enforce the four OTLP rules, rewriting hex
ids into the base64 that ProtoJSON expects, and then hands the normalized
document to json_format.ParseDict(ignore_unknown_fields=True). A generic
ProtoJSON parser given a valid OTLP document without this step accepts a hex id
as base64 and silently decodes it into the wrong bytes (32 hex characters are a
legal base64 alphabet and yield 24 bytes); that is the failure this module exists
to prevent.
"""
from __future__ import annotations

import base64
import json
import sys

from google.protobuf import json_format
from google.protobuf.descriptor import FieldDescriptor as F

ID_FIELDS = {"trace_id": 16, "span_id": 8, "parent_span_id": 8}
HEX = set("0123456789abcdefABCDEF")


class OTLPJSONError(ValueError):
    pass


def _normalize_scalar(field, value, where: str):
    if value is None:
        return None
    if field.type == F.TYPE_BYTES and field.name in ID_FIELDS:
        if not isinstance(value, str):
            raise OTLPJSONError(f"{where}: id must be a hex string")
        expected = ID_FIELDS[field.name] * 2
        if len(value) != expected or any(c not in HEX for c in value):
            raise OTLPJSONError(f"{where}: expected {expected} hex characters, got {value!r}")
        return base64.b64encode(bytes.fromhex(value)).decode()
    if field.type == F.TYPE_ENUM:
        if isinstance(value, bool) or not isinstance(value, int):
            raise OTLPJSONError(f"{where}: OTLP/JSON encodes enums as integers, got {value!r}")
        return value
    return value


def _normalize(descriptor, doc, where: str):
    if doc is None:
        return None
    if not isinstance(doc, dict):
        raise OTLPJSONError(f"{where}: expected object")
    by_json_name = {f.json_name: f for f in descriptor.fields}
    by_proto_name = {f.name: f for f in descriptor.fields}
    out = {}
    for key, value in doc.items():
        field = by_json_name.get(key)
        if field is None:
            if key in by_proto_name and by_proto_name[key].json_name != key:
                raise OTLPJSONError(
                    f"{where}.{key}: OTLP/JSON requires lowerCamelCase field names ({by_proto_name[key].json_name!r})"
                )
            continue
        here = f"{where}.{key}"
        if field.is_repeated and value is not None:
            if not isinstance(value, list):
                raise OTLPJSONError(f"{here}: expected array")
            if field.type == F.TYPE_MESSAGE:
                out[key] = [_normalize(field.message_type, item, f"{here}[{i}]") for i, item in enumerate(value)]
            else:
                out[key] = [_normalize_scalar(field, item, f"{here}[{i}]") for i, item in enumerate(value)]
        elif field.type == F.TYPE_MESSAGE:
            out[key] = _normalize(field.message_type, value, here)
        else:
            out[key] = _normalize_scalar(field, value, here)
    return out


def decode(data: bytes | str, message_class):
    try:
        doc = json.loads(data)
    except UnicodeDecodeError as exc:
        raise OTLPJSONError(
            f"not JSON: body is not UTF-8 text (byte {exc.object[exc.start]:#04x} at position {exc.start})"
        ) from exc
    except json.JSONDecodeError as exc:
        raise OTLPJSONError(f"not JSON: {exc.msg} at position {exc.pos}") from exc
    normalized = _normalize(message_class.DESCRIPTOR, doc, message_class.DESCRIPTOR.name)
    try:
        return json_format.ParseDict(normalized or {}, message_class(), ignore_unknown_fields=True)
    except json_format.ParseError as exc:
        raise OTLPJSONError(f"ProtoJSON: {exc}") from exc


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    from opentelemetry.proto.collector.logs.v1 import logs_service_pb2 as ls
    from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2 as ms
    from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as ts

    classes = {
        "trace": ts.ExportTraceServiceRequest,
        "metrics": ms.ExportMetricsServiceRequest,
        "logs": ls.ExportLogsServiceRequest,
    }
    signal = argv[1] if len(argv) > 1 else "trace"
    with open(argv[0], "rb") as fh:
        try:
            message = decode(fh.read(), classes[signal])
        except OTLPJSONError as exc:
            print(f"REJECTED: {exc}")
            return 1
    binary = message.SerializeToString()
    print(f"{len(binary)} bytes")
    print(binary.hex())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
