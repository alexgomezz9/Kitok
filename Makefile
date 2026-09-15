.PHONY: setup test dry-run status check run plan
setup:
	bash scripts/bootstrap_wsl.sh
test:
	. .venv/bin/activate && pytest -q
dry-run:
	. .venv/bin/activate && python main.py --dry-run
status:
	. .venv/bin/activate && python main.py --status
check:
	. .venv/bin/activate && python main.py --check-mpt
run:
	. .venv/bin/activate && python main.py
plan:
	. .venv/bin/activate && python main.py --plan
