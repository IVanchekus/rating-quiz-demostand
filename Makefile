COMPOSE := docker compose --profile telegram

.PHONY: up restart stop logs

# Build and start the complete stack, including the Telegram bot profile.
up:
	$(COMPOSE) up -d --build --wait

# Recreate every service to apply the latest images and configuration.
restart:
	$(COMPOSE) up -d --build --force-recreate --wait

# Stop and remove containers and the Compose network. Persistent database volume is kept.
stop:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100
