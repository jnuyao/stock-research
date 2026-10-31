PY ?= .venv/bin/python

.PHONY: lint test arch arch-actual design design-check check demo zones

lint:        ; $(PY) -m ruff check src tests design/tools $(wildcard examples)
test:        ; $(PY) -m pytest
arch:        ; $(PY) design/tools/arch_check.py
arch-actual: ; $(PY) design/tools/arch_check.py --json design/generated/actual-deps.json && node design/tools/build.mjs --actual design/generated/actual-deps.json
design:      ; node design/tools/build.mjs
design-check:; node design/tools/build.mjs --check
check: lint test arch design-check
demo:        ; $(PY) -m stockdesk demo intc-q3-2026
zones:       ; $(PY) -m stockdesk zones INTC --replay intc-q3-2026 --eps 1.75 --pe 38-45 && $(PY) -m stockdesk zones 0992.HK --replay lenovo-2026-10-29 --eps 2.7 --pe 8-11
