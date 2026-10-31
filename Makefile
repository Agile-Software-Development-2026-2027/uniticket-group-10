.PHONY: install test-local test-acceptance test-all test-django-docker clean

default: test-local

install:
	@echo "Installazione delle dipendenze in corso..."
	python -m pip install --upgrade pip
	python -m pip install -r test_requirements.txt

# Obiettivo per i test veloci (Unit & Integration)
test-local:
	@echo "Esecuzione test Unit e Integration (Locali)..."
	python -m pytest ticket-retrival/tests/ -v

# Obiettivo per i test lenti (Acceptance)
test-acceptance:
	@echo "Esecuzione test di Accettazione (CI/CD)..."
	python -m pytest ticket-retrival/tests/ -v

# Obiettivo per runnarli tutti 
test-all:
	@echo "Esecuzione di tutti i test..."
	python -m pytest ticket-retrival/tests/ -v

test-django-docker:
	@echo "Esecuzione del solo smoke test Django nel container uniticket..."
	docker compose -f uniticket/docker-compose.yml run --build --rm uniticket python manage.py test chatbot_tests.test_smoke.DjangoSetupSmokeTest.test_django_apps_are_ready

clean:
	@echo "Pulizia dei file temporanei..."
	rm -rf .pytest_cache
	find . -type d -name "__pycache__" -exec rm -r {} +
