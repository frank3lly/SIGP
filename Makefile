.PHONY: build up down restart logs test benchmark simulate shell clean

COMPOSE ?= docker-compose

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d server

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart server

logs:
	$(COMPOSE) logs -f server

test:
	$(COMPOSE) run --rm server test

benchmark:
	$(COMPOSE) run --rm server benchmark --frames 50

simulate:
	$(COMPOSE) run --rm server simulate --server-url http://server:8000

shell:
	$(COMPOSE) run --rm server bash

clean:
	$(COMPOSE) down -v
	rm -rf tests/output/* test/reports/* tests/reports/*
