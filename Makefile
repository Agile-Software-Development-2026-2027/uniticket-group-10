.PHONY: install test-local test-agent test-acceptance test-all clean

default: test-local

test-agent:
	@echo "Running agent tests..."
	cd agent && python -m pytest

# Usa il DB temporaneo dei test e non avvia il servizio agent.
test-local:
	@echo "Running Django tests in the uniticket container..."
	docker compose -f ./docker-compose.yml run --build --rm -T --no-deps uniticket python manage.py test chatbot_tests ticket_events.tests --settings=ticket_events.test_settings --noinput

clean:
	@echo "Cleaning temporary files..."
	rm -rf .pytest_cache
	find . -type d -name "__pycache__" -exec rm -r {} +
