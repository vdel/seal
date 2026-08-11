.PHONY: test unit-tests

test: lint
	uv run pytest tests/

unit-tests:
	uv run pytest --cov=. --cov-report=xml:tests-results/coverage.xml --junit-xml=tests-results/junit.xml tests/

lint:
	uv run flake8

migrations:
	uv run python src/manage.py makemigrations
	uv run python src/manage.py migrate
