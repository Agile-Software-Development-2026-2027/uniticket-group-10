.PHONY: install test-local test-acceptance test-all clean

default: test-local

install:
	@echo "Installing dependencies..."
	python -m pip install --upgrade pip
	python -m pip install -r test_requirements.txt

test-local:
	@echo "Running Django tests in the uniticket container..."
	docker compose -f uniticket/docker-compose.yml run --rm -T uniticket python manage.py test chatbot_tests

clean:
	@echo "Cleaning temporary files..."
	rm -rf .pytest_cache
	find . -type d -name "__pycache__" -exec rm -r {} +
