PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup lint fmt test run clean

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -e ".[dev]"

fmt:
	.venv/bin/ruff format src scripts tests

lint:
	.venv/bin/ruff check src scripts tests --fix
	.venv/bin/mypy src

test:
	.venv/bin/pytest

run:
	$(PY) -m android_auto

clean:
	rm -rf output/xml/* output/screenshots/* output/logs/*
