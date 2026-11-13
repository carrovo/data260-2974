.PHONY: mongo-up mongo-down test-hw06 experiment-hw06 verify-hw06 verify-hw08 test-hw10-freeze freeze-hw10-cases

mongo-up:
	docker compose -f docker-compose.hw6.yml up -d

mongo-down:
	docker compose -f docker-compose.hw6.yml down

test-hw06:
	python code/test_hw6_offline.py
	python code/hw6_memory_experiment.py --dry-run

experiment-hw06:
	python code/hw6_memory_experiment.py

verify-hw06:
	python code/verify_hw6.py

verify-hw08:
	PYTHONPATH=code .venv/bin/python code/verify_hw8.py

test-hw10-freeze:
	PYTHONPATH=code .venv/bin/python code/test_hw10_freeze_offline.py

freeze-hw10-cases:
	PYTHONPATH=code .venv/bin/python code/hw10_freeze_cases.py
