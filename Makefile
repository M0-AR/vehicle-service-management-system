.PHONY: up down logs migrate seed test-backend build-frontend lint compose-check

up:            ## build & start the full stack (http://localhost)
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

migrate:       ## run alembic + seed demo tenants inside the backend container
	docker compose exec backend alembic upgrade head
	docker compose exec backend python -m app.seed

seed:
	docker compose exec backend python -m app.seed

test-backend:  ## run backend tests against a throwaway postgres (needs docker)
	cd backend && python -m pytest -q

build-frontend:
	cd frontend && npm run build

lint:
	cd backend && python -m ruff check app 2>/dev/null || true
	cd frontend && npm run lint

compose-check:
	docker compose config --quiet && echo "compose OK"
