.PHONY: setup test dry-run status check run plan
setup:
	bash scripts/bootstrap_wsl.sh
test:
	. .venv/bin/activate && pytest -q
dry-run:
	. .venv/bin/activate && python main.py --dry-run
status:
	. .venv/bin/activate && python main.py --status
check: studio-check
run:
	. .venv/bin/activate && python main.py
plan:
	. .venv/bin/activate && python main.py --plan

.PHONY: studio studio-check studio-setup
studio:
	bash scripts/studio.sh
studio-check:
	bash scripts/studio.sh --check
studio-setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"
	PATH="$(CURDIR)/.tools/node/bin:$$PATH" npm --prefix frontend ci

.PHONY: cinema-setup
cinema-setup:
	PLAYWRIGHT_BROWSERS_PATH="$(CURDIR)/.tools/browsers" frontend/node_modules/.bin/playwright install chromium --only-shell

.PHONY: verify verify-browser
verify:
	.venv/bin/python scripts/verify.py
verify-browser:
	.venv/bin/python scripts/verify.py --e2e

.PHONY: docs-check
docs-check:
	.venv/bin/python scripts/check_documentation.py
