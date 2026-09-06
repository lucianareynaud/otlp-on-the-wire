"""Records real OTLP exchanges on the loopback interface into pcap files.

Four captures are produced under captures/:

  trace-http1-plaintext.pcap   fixtures/trace.bin as the body of a POST /v1/traces
                               over HTTP/1.1 (urllib client, stdlib HTTP server)
  trace-grpc-h2c.pcap          fixtures/trace.bin sent through the generated gRPC
                               stub (grpcio) to a grpcio TraceService server, h2c
  trace-grpc-gzip.pcap         the same call with grpc.Compression.Gzip
  trace-sdk-grpc.pcap          the OpenTelemetry Python SDK exporting a span built
                               to match the specimen (real SDK bytes, including
                               fields the hand-built specimen omits)

The sniffer is scapy on the loopback interface ("lo" on Linux, "lo0" on macOS,
override with OTLP_WIRE_IFACE); raw sockets require root. Every byte
in the pcaps was produced by the real client and server implementations named
above; nothing is synthesized. Requires: scapy grpcio opentelemetry-sdk
opentelemetry-exporter-otlp-proto-grpc opentelemetry-proto.
"""
from __future__ import annotations

import gzip
import http.server
import json
import os
import platform
import sys
import threading
import time
import urllib.request
from concurrent import futures

import grpc
from scapy.all import TCP, sniff, wrpcap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otlp_json import OTLPJSONError, decode as decode_otlp_json  # noqa: E402

from google.protobuf import json_format
from google.rpc import code_pb2, status_pb2

from opentelemetry.proto.collector.trace.v1 import trace_service_pb2 as ts
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc as ts_grpc

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURE = os.path.join(ROOT, "fixtures", "trace.bin")
OUT = os.path.join(ROOT, "captures")
GRPC_PORT = 4317
HTTP_PORT = 4318
IFACE = os.environ.get("OTLP_WIRE_IFACE", "lo0" if platform.system() == "Darwin" else "lo")


class TraceService(ts_grpc.TraceServiceServicer):
    def Export(self, request, context):
        return ts.ExportTraceServiceResponse()


class Receiver(http.server.BaseHTTPRequestHandler):
    """Teaching receiver for OTLP/HTTP status-code and error-body behaviour.

    It reads the request body (so the connection stays usable), selects a decoder
    by Content-Type, and follows the OTLP/HTTP specification where it speaks: the
    response uses the same Content-Type as the request; success is 200 with an
    ExportTraceServiceResponse (zero bytes as Protobuf, "{}" as JSON); JSON bodies
    are decoded with tools/otlp_json.py, which applies the OTLP deviations from
    ProtoJSON (hex ids, integer enums, lowerCamelCase); undecodable payload is
    400 (Bad Data); every failure carries a google.rpc.Status body in
    the request's encoding. Where the spec defers to HTTP semantics the receiver
    makes the conventional HTTP choice: 415 for a media type that is not an OTLP
    encoding, 404 for an unknown path. It decodes and discards; it is not a Collector.
    """

    protocol_version = "HTTP/1.1"
    ENCODINGS = ("application/x-protobuf", "application/json")

    def _encode(self, message, content_type: str) -> bytes:
        if content_type == "application/json":
            return json_format.MessageToJson(message, indent=None).encode()
        return message.SerializeToString()

    def _reply(self, http_status: int, message, content_type: str) -> None:
        body = self._encode(message, content_type)
        self.send_response(http_status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _fail(self, http_status: int, rpc_code: int, message: str, content_type: str) -> None:
        self._reply(http_status, status_pb2.Status(code=rpc_code, message=message), content_type)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip()
        reply_type = content_type if content_type in self.ENCODINGS else "application/x-protobuf"
        if self.path != "/v1/traces":
            self._fail(404, code_pb2.NOT_FOUND, f"no OTLP signal at {self.path}", reply_type)
            return
        if content_type not in self.ENCODINGS:
            self._fail(415, code_pb2.INVALID_ARGUMENT, f"unsupported media type {content_type!r}", reply_type)
            return
        if self.headers.get("Content-Encoding") == "gzip":
            try:
                body = gzip.decompress(body)
            except OSError:
                self._fail(400, code_pb2.INVALID_ARGUMENT, "Content-Encoding is gzip but the body is not a gzip stream", reply_type)
                return
        try:
            if content_type == "application/json":
                decode_otlp_json(body, ts.ExportTraceServiceRequest)
            else:
                ts.ExportTraceServiceRequest().ParseFromString(body)
        except OTLPJSONError as exc:
            self._fail(400, code_pb2.INVALID_ARGUMENT, f"payload is not valid OTLP/JSON: {exc}", reply_type)
            return
        except Exception as exc:
            self._fail(400, code_pb2.INVALID_ARGUMENT, f"payload is not valid {content_type}: {type(exc).__name__}", reply_type)
            return
        self._reply(200, ts.ExportTraceServiceResponse(), reply_type)

    def log_message(self, *args):
        return


def with_capture(name: str, ports: tuple[int, ...], action) -> None:
    packets: list = []
    done = threading.Event()

    def sniffer():
        packets.extend(
            sniff(
                iface=IFACE,
                lfilter=lambda p: p.haslayer(TCP) and (p[TCP].sport in ports or p[TCP].dport in ports),
                stop_filter=lambda p: done.is_set(),
                timeout=8,
            )
        )

    t = threading.Thread(target=sniffer, daemon=True)
    t.start()
    time.sleep(1.0)
    action()
    time.sleep(1.0)
    done.set()
    t.join(timeout=10)
    path = os.path.join(OUT, name)
    wrpcap(path, packets)
    print(f"{name}: {len(packets)} packets")


def http_lab(body: bytes) -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def action():
        req = urllib.request.Request(
            f"http://127.0.0.1:{HTTP_PORT}/v1/traces",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-protobuf", "User-Agent": "otlp-on-the-wire/urllib"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200, resp.status

    with_capture("trace-http1-plaintext.pcap", (HTTP_PORT,), action)
    server.shutdown()


def grpc_lab(body: bytes) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    ts_grpc.add_TraceServiceServicer_to_server(TraceService(), server)
    server.add_insecure_port(f"127.0.0.1:{GRPC_PORT}")
    server.start()
    request = ts.ExportTraceServiceRequest()
    request.ParseFromString(body)

    def plain():
        with grpc.insecure_channel(f"127.0.0.1:{GRPC_PORT}") as channel:
            ts_grpc.TraceServiceStub(channel).Export(request, timeout=5)

    def gzipped():
        with grpc.insecure_channel(f"127.0.0.1:{GRPC_PORT}") as channel:
            ts_grpc.TraceServiceStub(channel).Export(request, timeout=5, compression=grpc.Compression.Gzip)

    def sdk():
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.id_generator import IdGenerator
        from opentelemetry.trace import SpanKind, StatusCode

        class FixedIds(IdGenerator):
            def generate_trace_id(self) -> int:
                return 0x5B8EFFF798038103D269B633813FC60C

            def generate_span_id(self) -> int:
                return 0xEEE19B7EC3C1B174

        provider = TracerProvider(resource=Resource({"service.name": "checkout"}), id_generator=FixedIds())
        exporter = OTLPSpanExporter(endpoint=f"http://127.0.0.1:{GRPC_PORT}", insecure=True, timeout=5)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("manual")
        t0 = 1788696000000000000
        span = tracer.start_span("GET /cart", kind=SpanKind.SERVER, start_time=t0)
        span.set_attribute("http.request.method", "GET")
        span.set_status(StatusCode.OK)
        span.end(end_time=t0 + 12_500_000)
        provider.shutdown()

    with_capture("trace-grpc-h2c.pcap", (GRPC_PORT,), plain)
    with_capture("trace-grpc-gzip.pcap", (GRPC_PORT,), gzipped)
    with_capture("trace-sdk-grpc.pcap", (GRPC_PORT,), sdk)
    server.stop(grace=None)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    with open(FIXTURE, "rb") as fh:
        specimen = fh.read()
    if len(specimen) != 140:
        sys.exit(f"unexpected fixture size {len(specimen)}; run tools/build_specimens.py first")
    http_lab(specimen)
    grpc_lab(specimen)
