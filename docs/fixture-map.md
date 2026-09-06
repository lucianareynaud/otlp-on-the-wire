# Canonical trace fixture: offset map

`fixtures/trace.bin` is the canonical 140-byte `ExportTraceServiceRequest` used throughout the repository.

```text
SHA-256  ab3caadd338bbee547e68ffee2e9f0f324999a459001662ac0bae928a7dd2e11
Size     140 bytes
Signal   traces
Shape    ExportTraceServiceRequest → ResourceSpans → ScopeSpans → Span
```

The table below is the public, citable byte map. Offsets are hexadecimal.

```text
off   bytes                     meaning
----  ------------------------  ----------------------------------------------------------------
0000  0a                        tag → field 1, LEN         ExportTraceServiceRequest.resource_spans[0]
0001  89 01                     length 137                 (= 140 − 3: the whole rest of the message)
0003  0a                        tag → field 1, LEN         ResourceSpans.resource
0004  1c                        length 28
0005  0a                        tag → field 1, LEN         Resource.attributes[0]  (KeyValue)
0006  1a                        length 26
0007  0a 0c                     KeyValue.key (1), length 12
0009  73 65 72 76 69 63 65 2e   "service.name"
      6e 61 6d 65
0015  12 0a                     KeyValue.value (2), length 10   → AnyValue
0017  0a 08                     AnyValue.string_value (1), length 8
0019  63 68 65 63 6b 6f 75 74   "checkout"
0021  12 69                     tag → field 2, LEN         ResourceSpans.scope_spans[0], length 105
0023  0a 08                     ScopeSpans.scope (1), length 8   → InstrumentationScope
0025  0a 06                     InstrumentationScope.name (1), length 6
0027  6d 61 6e 75 61 6c         "manual"
002d  12 5d                     tag → field 2, LEN         ScopeSpans.spans[0], length 93   → Span
002f  0a 10                     Span.trace_id (1), length 16
0031  5b 8e ff f7 98 03 81 03   16 raw bytes; hex rendering 5b8efff798038103d269b633813fc60c
      d2 69 b6 33 81 3f c6 0c
0041  12 08                     Span.span_id (2), length 8
0043  ee e1 9b 7e c3 c1 b1 74   8 raw bytes; hex rendering eee19b7ec3c1b174
004b  2a 09                     Span.name (5), length 9      (0x2a = 00101 010)
004d  47 45 54 20 2f 63 61 72   "GET /cart"
      74
0056  30 02                     Span.kind (6), VARINT = 2    (0x30 = 00110 000) → SPAN_KIND_SERVER
0058  39                        Span.start_time_unix_nano (7), I64   (0x39 = 00111 001)
0059  00 80 29 fb 88 b9 d2 18   LE → 0x18d2b988fb298000 = 1788696000000000000
0061  41                        Span.end_time_unix_nano (8), I64     (0x41 = 01000 001)
0062  20 3c e8 fb 88 b9 d2 18   LE → 0x18d2b988fbe83c20 = 1788696000012500000 (+12.5 ms)
006a  4a 1c                     Span.attributes[0] (9), length 28    (0x4a = 01001 010) → KeyValue
006c  0a 13                     KeyValue.key (1), length 19
006e  68 74 74 70 2e 72 65 71   "http.request.method"
      75 65 73 74 2e 6d 65 74
      68 6f 64
0081  12 05                     KeyValue.value (2), length 5   → AnyValue
0083  0a 03                     AnyValue.string_value (1), length 3
0085  47 45 54                  "GET"
0088  7a 02                     Span.status (15), length 2     (0x7a = 01111 010) → Status
008a  18 01                     Status.code (3), VARINT = 1    (0x18 = 00011 000) → STATUS_CODE_OK
008c  —                         end of message (140 bytes)
```

## Length closure

```text
resource_spans length            137 = 140 − 1 (tag) − 2 (length varint)
  resource record            2 + 28 =  30
  scope_spans record         2 + 105 = 107
                                       137
ResourceSpans.resource length     28 = attributes[0] record (2 + 26)
  KeyValue length                 26 = key (2 + 12) + value (2 + 10)
    AnyValue length               10 = string_value (2 + 8)
ScopeSpans length                105 = scope (2 + 8) + spans[0] (2 + 93)
  InstrumentationScope length      8 = name (2 + 6)
Span length                       93 = trace_id 18 + span_id 10 + name 11 + kind 2
                                     + start 9 + end 9 + attributes 30 + status 4
```

The arithmetic is an invariant. If a nested length does not close, the parser state is wrong before any semantic interpretation is trusted.

## Reproduce

```bash
make venv
make specimens
sha256sum fixtures/trace.bin
make decode
```

The fixture builder and regression tests are the executable source of truth for this map.
