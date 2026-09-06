.PHONY: venv specimens failures bench decode walk test captures clean

PY := $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)

venv:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

specimens:
	$(PY) tools/build_specimens.py

failures: specimens
	$(PY) tools/make_failures.py

bench:
	$(PY) tools/bench_batch.py

decode:
	$(PY) tools/rawdecode.py fixtures/trace.bin

walk:
	$(PY) tools/wirewalk.py captures/trace-grpc-h2c.pcap --protobuf

test:
	$(PY) -m pytest -q tests

captures:
	sudo $(PY) tools/capture_lab.py

clean:
	rm -rf .venv .pytest_cache tests/__pycache__ tools/__pycache__
