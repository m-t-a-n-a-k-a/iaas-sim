.PHONY: up down reset logs verify backend-verify frontend-verify smoke-test

up:
	docker compose up --build -d

down:
	docker compose down

reset:
	docker compose down -v --remove-orphans
	docker compose up --build -d

logs:
	docker compose logs -f

smoke-test:
	docker compose up -d vcsim
	cd backend && PYVMOMI_SMOKE=1 VSPHERE_HOST=127.0.0.1 VSPHERE_PORT=8989 VSPHERE_USERNAME=user VSPHERE_PASSWORD=pass ~/.local/bin/uv run pytest tests/test_vcsim_smoke.py

backend-verify:
	cd backend && ~/.local/bin/uv sync --locked --all-extras
	cd backend && ~/.local/bin/uv run pyright
	cd backend && ~/.local/bin/uv run ruff check .
	cd backend && ~/.local/bin/uv run ruff format --check .
	cd backend && ~/.local/bin/uv run import-linter lint --config pyproject.toml
	cd backend && ~/.local/bin/uv run pytest

frontend-verify:
	cd frontend && npm install
	cd frontend && npx svelte-check --tsconfig ./tsconfig.json
	cd frontend && npm run build

verify: backend-verify frontend-verify smoke-test
	cp -n .env.example .env 2>/dev/null || true
	docker compose config > /dev/null
