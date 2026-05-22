.PHONY: run agent test lint docker-build

run:
	uvicorn oracle.api:app --reload --host 127.0.0.1 --port 8000

agent:
	python3 scripts/run_agent.py --snapshot

test:
	python3 -m unittest discover -s tests -p "test_*.py"

lint:
	ruff check oracle scripts tests

docker-build:
	docker build -t mandarin-market-oracle .
