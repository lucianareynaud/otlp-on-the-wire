# v1.0.0 — public evidence release

Initial public release of the `otlp-on-the-wire` evidence repository.

## Included

- deterministic trace, metrics, logs, and warm-up OTLP specimens;
- eight deliberately broken protocol/payload cases;
- four packet captures from real HTTP/gRPC/SDK implementations;
- schema-less Protobuf record walker;
- HTTP/2 + gRPC + Protobuf capture walker;
- OTLP/JSON normalization/validation layer over ProtoJSON;
- reproducible batch-size/compression benchmark;
- 41-test regression suite and GitHub Actions workflow;
- public offset-by-offset map of the canonical trace fixture.

The full guided book manuscript is intentionally not included in the public repository.

## Fixture SHA-256

```text
45fce92afc28ae539a28368a8b325f59ecda59f5b1bf4ffd84913172804f3028  fixtures/logs.bin
634b6f36ca2371d1239b5a31bf596d692b630170c68a5eaac5695194267e5f86  fixtures/metrics.bin
ab3caadd338bbee547e68ffee2e9f0f324999a459001662ac0bae928a7dd2e11  fixtures/trace.bin
0238be035ce430364004196e8f16296937f0984d79fa239ef8287a686c1339ea  fixtures/warmup/minimal_trace.grpc.bin
8bec03a38493bffe618c301cb49a32eb2209800d536ecbca89bc75b56f077bc5  fixtures/warmup/minimal_trace.otlp.bin
```

## Verification

```bash
make venv
make test
make specimens
make failures
make bench
git diff --exit-code
```

Expected test count: **41 passed**.

## Licensing

- Code, tests, workflows, and generated test artifacts: Apache-2.0.
- Original public documentation: CC BY 4.0.
- Separately distributed book manuscript: not part of this repository.
