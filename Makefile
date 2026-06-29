.PHONY: local-ci check-handoffs

local-ci:
	python3 -m py_compile app/*.py tests/*.py scripts/*.py
	python3 -m unittest discover -s tests
	python3 scripts/ui_static_check.py
	python3 scripts/security_check.py .
	python3 scripts/check_markdown_links.py
	python3 scripts/check_handoffs.py

check-handoffs:
	python3 scripts/check_handoffs.py
