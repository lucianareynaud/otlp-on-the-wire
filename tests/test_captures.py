from conftest import path

from wirewalk import reassemble


def _streams(name):
    return reassemble(path("captures", name))


def test_http1_capture_carries_the_exact_specimen():
    with open(path("fixtures/trace.bin"), "rb") as fh:
        specimen = fh.read()
    client = next(data for (src, sport, dst, dport), data in _streams("trace-http1-plaintext.pcap").items() if dport == 4318)
    head, _, body = client.partition(b"\r\n\r\n")
    assert head.startswith(b"POST /v1/traces HTTP/1.1")
    assert b"Content-Type: application/x-protobuf" in head and b"Content-Length: 140" in head
    assert body == specimen
    server = next(data for (src, sport, dst, dport), data in _streams("trace-http1-plaintext.pcap").items() if sport == 4318)
    assert server.startswith(b"HTTP/1.1 200 OK") and server.endswith(b"Content-Length: 0\r\n\r\n")


def test_grpc_capture_data_frame_matches_the_computed_header():
    with open(path("fixtures/trace.bin"), "rb") as fh:
        specimen = fh.read()
    client = next(data for (src, sport, dst, dport), data in _streams("trace-grpc-h2c.pcap").items() if dport == 4317)
    assert client.startswith(b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n")
    frame_header = bytes.fromhex("000091000100000001")
    idx = client.find(frame_header)
    assert idx > 0
    assert client[idx + 9:idx + 9 + 5] == bytes.fromhex("000000008c")
    assert client[idx + 14:idx + 14 + 140] == specimen


def test_grpc_capture_response_is_empty_message_plus_trailers():
    server = next(data for (src, sport, dst, dport), data in _streams("trace-grpc-h2c.pcap").items() if sport == 4317)
    assert bytes.fromhex("000005000000000001" + "0000000000") in server


def test_gzip_capture_declares_gzip_but_sends_the_small_message_uncompressed():
    client = next(data for (src, sport, dst, dport), data in _streams("trace-grpc-gzip.pcap").items() if dport == 4317)
    assert bytes.fromhex("000091000100000001" + "000000008c") in client


def test_sdk_capture_adds_span_flags():
    client = next(data for (src, sport, dst, dport), data in _streams("trace-sdk-grpc.pcap").items() if dport == 4317)
    assert bytes.fromhex("000097000100000001" + "0000000092") in client
    assert bytes.fromhex("7a021801" + "850100010000") in client
