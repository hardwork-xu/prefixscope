PYTHON ?= .venv/bin/python

.PHONY: install demo test check fetch benchmark analyze build verify
install:
	python3 -m venv .venv
	$(PYTHON) -m pip install --require-hashes -r requirements.lock
	$(PYTHON) -m pip install --no-build-isolation -e .
demo:
	$(PYTHON) -m prefixscope demo
test:
	$(PYTHON) -m pytest
check:
	$(PYTHON) -m ruff check src tests scripts benchmark.py
	$(PYTHON) -m ruff format --check src tests scripts benchmark.py
	$(PYTHON) -m mypy
	$(PYTHON) scripts/check_docs.py
fetch:
	$(PYTHON) scripts/fetch_traces.py
benchmark:
	$(PYTHON) benchmark.py --output results/benchmark.json
analyze:
	$(PYTHON) scripts/analyze_results.py results/benchmark.json
build:
	$(PYTHON) -m build --no-isolation
verify:
	$(PYTHON) scripts/acceptance.py
