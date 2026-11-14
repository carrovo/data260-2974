.PHONY: mongo-up mongo-down test-hw06 experiment-hw06 verify-hw06 verify-hw08 test-hw10-freeze freeze-hw10-cases install-hw10 test-hw10-judge run-hw10-judge test-hw10-part2 run-hw10-part2 test-hw10-part4 run-hw10-part4-examples run-hw10-part4-experiment

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

install-hw10:
	python3 -m venv .venv-hw10
	.venv-hw10/bin/python -m pip install --upgrade pip
	.venv-hw10/bin/python -m pip install -r requirements-hw10.txt

test-hw10-judge:
	PYTHONPATH=code .venv-hw10/bin/python code/test_hw10_judge_offline.py

run-hw10-judge:
	PYTHONPATH=code .venv-hw10/bin/python code/hw10_judge.py

test-hw10-part2:
	PYTHONPATH=code .venv-hw10/bin/python code/test_hw10_part2_offline.py

run-hw10-part2:
	PYTHONPATH=code .venv-hw10/bin/python code/hw10_part2_evaluator.py

test-hw10-part4:
	PYTHONPATH=code .venv-hw10/bin/python code/test_hw10_part4_offline.py

run-hw10-part4-examples:
	PYTHONPATH=code .venv-hw10/bin/python code/hw10_part4_observability.py examples

run-hw10-part4-experiment:
	PYTHONPATH=code .venv-hw10/bin/python code/hw10_part4_observability.py experiment
