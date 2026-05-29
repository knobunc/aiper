.PHONY: test lint typecheck check

test:
	python -m pytest tests/ -v

lint:
	ruff check custom_components/ tests/

typecheck:
	mypy custom_components/aiper/ --ignore-missing-imports

check: lint typecheck test
