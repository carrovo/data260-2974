.PHONY: mongo-up mongo-down test-hw06 experiment-hw06 verify-hw06

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
