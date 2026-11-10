.PHONY: install test-local test-agent test-acceptance test-all clean

default: test-local

test-agent:
	@echo "Running agent tests..."
	cd agent && python -m pytest

test-local:
	@echo "Running Django tests in the uniticket container..."
	docker compose -f ./docker-compose.yml run --build --rm -T uniticket python manage.py test chatbot_tests

clean:
	@echo "Cleaning temporary files..."
	rm -rf .pytest_cache
	find . -type d -name "__pycache__" -exec rm -r {} +
