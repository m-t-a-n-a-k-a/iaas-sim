.PHONY: prepare up down reset logs verify backend-verify frontend-verify smoke-test .env

.env:
	cp -n .env.example .env 2>/dev/null || true

prepare: .env

up: .env
	docker compose up --build -d

down:
	docker compose down

reset:
	docker compose down -v --remove-orphans
	docker compose up --build -d

logs:
	docker compose logs -f

smoke-test: prepare
	docker compose up -d vcsim
	docker compose run --rm --no-deps \
		-e PYVMOMI_SMOKE=1 \
		-e VSPHERE_HOST=vcsim \
		-e VSPHERE_PORT=8989 \
		-e VSPHERE_SCHEME=https \
		-e VSPHERE_USERNAME=user \
		-e VSPHERE_PASSWORD=pass \
		-v "$(CURDIR)/backend/tests/test_vcsim_smoke.py:/tmp/test_vcsim_smoke.py:ro" \
		-w /app \
		iaas-sim bash -lc '. .venv/bin/activate && PYTHONPATH=/app/src pytest -q /tmp/test_vcsim_smoke.py'

backend-verify: prepare
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
	docker compose config > /dev/null
