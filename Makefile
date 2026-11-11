.PHONY: test-ticket-events

test-ticket-events:
	docker compose -f uniticket/docker-compose.yml run --build --rm -T --no-deps uniticket python manage.py test ticket_events.tests --settings=ticket_events.test_settings
