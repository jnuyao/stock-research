PY ?= .venv/bin/python

.PHONY: lint test arch arch-actual design design-check check demo

lint:        ; $(PY) -m ruff check src tests design/tools $(wildcard examples)
test:        ; $(PY) -m pytest
arch:        ; $(PY) design/tools/arch_check.py
arch-actual: ; $(PY) design/tools/arch_check.py --json design/generated/actual-deps.json && node design/tools/build.mjs --actual design/generated/actual-deps.json
design:      ; node design/tools/build.mjs
design-check:; node design/tools/build.mjs --check
check: lint test arch design-check
demo:        ; $(PY) -m stockdesk demo intc-q3-2026
