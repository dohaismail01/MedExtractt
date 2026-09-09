# MedExtract AI — common tasks.
# On Windows without `make`, run the underlying command shown for each target.
# Use the project venv interpreter: .venv/Scripts/python (Win) or .venv/bin/python (POSIX).

PY ?= python

.PHONY: serve ui eval eval-cached test mcp data help

help:
	@echo "serve       - run the FastAPI backend on :8000"
	@echo "ui          - run the React frontend on :5173"
	@echo "eval        - run the evaluation sweep (live model calls, cached)"
	@echo "eval-cached - regenerate the metrics table from cache, no network"
	@echo "test        - run the pytest suite"
	@echo "mcp         - run the icd10_mcp server standalone (for MCP Inspector)"
	@echo "data        - download the Kaggle dataset into ./data"

serve:
	$(PY) -m uvicorn app.api:app --reload --port 8000

ui:
	cd frontend && npm run dev

eval:
	$(PY) -m eval.run_eval

eval-cached:
	$(PY) -m eval.run_eval --from-cache

test:
	$(PY) -m pytest -q

mcp:
	$(PY) -m mcp_servers.icd10_mcp.server

data:
	$(PY) -m scripts.download_data
