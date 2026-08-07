PYTHON ?= python3

.PHONY: local-ci check-handoffs check-doc-metadata artifact-audit milestone-candidate daily-mainline

local-ci:
	$(PYTHON) -m py_compile app/*.py tests/*.py scripts/*.py
	$(PYTHON) -m unittest discover -s tests
	$(PYTHON) scripts/ui_static_check.py
	$(PYTHON) scripts/security_check.py .
	$(PYTHON) scripts/check_markdown_links.py
	$(PYTHON) scripts/check_handoffs.py
	$(PYTHON) scripts/check_doc_metadata.py

check-handoffs:
	$(PYTHON) scripts/check_handoffs.py

check-doc-metadata:
	$(PYTHON) scripts/check_doc_metadata.py

artifact-audit:
	$(PYTHON) scripts/local_artifact_retention.py --target all --output /tmp/ai-quant-artifact-audit.json

milestone-candidate:
	$(PYTHON) scripts/local_milestone_candidate.py

daily-mainline:
	$(PYTHON) scripts/daily_mainline_run.py
