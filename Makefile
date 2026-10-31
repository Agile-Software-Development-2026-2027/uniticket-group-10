.PHONY: install test-local test-acceptance test-all clean

default: test-local

install:
	@echo "Installazione delle dipendenze in corso..."
	python -m pip install --upgrade pip
	python -m pip install -r test_requirements.txt

test-local:
	@echo "Esecuzione del solo smoke test Django nel container uniticket..."
	docker compose -f uniticket/docker-compose.yml run --rm -T uniticket python manage.py test chatbot_tests

clean:
	@echo "Pulizia dei file temporanei..."
	rm -rf .pytest_cache
	find . -type d -name "__pycache__" -exec rm -r {} +
