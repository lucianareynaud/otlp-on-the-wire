import http.client
import http.server
import json
import threading

import pytest
from conftest import path

from capture_lab import Receiver


@pytest.fixture(scope="module")
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv.server_address[1]
    srv.shutdown()


def _post(port, content_type, body, url="/v1/traces"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", url, body=body, headers={"Content-Type": content_type})
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp.status


def _body():
    with open(path("fixtures/trace.bin"), "rb") as fh:
        return fh.read()


def test_protobuf_body_with_protobuf_content_type_is_accepted(server):
    assert _post(server, "application/x-protobuf", _body()) == 200


def test_protobuf_body_declared_as_json_is_bad_data_400(server):
    assert _post(server, "application/json", _body()) == 400


def test_unsupported_media_type_is_415(server):
    assert _post(server, "application/octet-stream", _body()) == 415


def test_failure_request_files_declare_the_content_types_under_test():
    with open(path("failures/wrong-content-type-json.request.bin"), "rb") as fh:
        assert b"Content-Type: application/json\r\n" in fh.read()
    with open(path("failures/unsupported-content-type.request.bin"), "rb") as fh:
        assert b"Content-Type: application/octet-stream\r\n" in fh.read()


def _post_full(port, content_type, body):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", "/v1/traces", body=body, headers={"Content-Type": content_type})
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    return resp.status, resp.getheader("Content-Type"), payload


def test_json_request_gets_json_status_body_on_bad_data(server):
    status, ctype, payload = _post_full(server, "application/json", _body())
    assert status == 400 and ctype == "application/json"
    doc = json.loads(payload)
    assert doc["code"] == 3 and "OTLP/JSON" in doc["message"]


def test_json_request_success_is_json_empty_object(server):
    status, ctype, payload = _post_full(server, "application/json", b"{}")
    assert (status, ctype, payload) == (200, "application/json", b"{}")


def test_protobuf_request_gets_protobuf_status_body_on_bad_data(server):
    from google.rpc import status_pb2

    status, ctype, payload = _post_full(server, "application/x-protobuf", _body()[:100])
    assert status == 400 and ctype == "application/x-protobuf"
    st = status_pb2.Status()
    st.ParseFromString(payload)
    assert st.code == 3 and "x-protobuf" in st.message


def test_protobuf_request_success_has_empty_body(server):
    assert _post_full(server, "application/x-protobuf", _body()) == (200, "application/x-protobuf", b"")


def test_json_request_with_valid_otlp_json_is_accepted(server):
    import bench_batch
    from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as ts

    req = ts.ExportTraceServiceRequest()
    req.ParseFromString(_body())
    assert _post_full(server, "application/json", bench_batch.otlp_json(req)) == (200, "application/json", b"{}")


def test_json_request_with_base64_ids_is_bad_data(server):
    import bench_batch
    from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as ts

    req = ts.ExportTraceServiceRequest()
    req.ParseFromString(_body())
    doc = json.loads(bench_batch.otlp_json(req))
    doc["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"] = "W47/95gDgQPSabYzgT/GDA=="
    status, ctype, payload = _post_full(server, "application/json", json.dumps(doc).encode())
    assert status == 400 and ctype == "application/json"
    assert "32 hex characters" in json.loads(payload)["message"]
