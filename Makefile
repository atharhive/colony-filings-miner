PY ?= python3

.PHONY: help install test run smoke

help:
	@echo "make test   run the offline suite"
	@echo "make run    serve on :8099"
	@echo "make smoke  ask the live SEC endpoints three questions"

install:
	$(PY) -m pip install -q pytest

test:
	$(PY) -m pytest tests -q

run:
	$(PY) -m src.server --host 0.0.0.0 --port 8099

smoke:
	$(PY) smoke.py
