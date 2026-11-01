"""Shared configuration for the DATA 260 HW8 Kafka services."""

import os

SID4 = 2974
PORT_BASE = 8274
PREFIX = "s2974"
SEED = 2974
VERIFY_SEED = 262974
DOMAIN_ID = 6

KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:9092",
)
REQUEST_TOPIC = f"{PREFIX}_entity_requests"
RESPONSE_TOPIC = f"{PREFIX}_entity_responses"
WORKER_GROUP_ID = f"{PREFIX}_listing_worker"
API_RESPONSE_GROUP_ID = f"{PREFIX}_api_responses"
RPC_TIMEOUT_SECONDS = float(os.getenv("HW8_RPC_TIMEOUT_SECONDS", "10"))

INBOX_TOPIC = f"{PREFIX}_inbox"
TASKS_TOPIC = f"{PREFIX}_tasks"
DRAFTS_TOPIC = f"{PREFIX}_drafts"
FINAL_TOPIC = f"{PREFIX}_final"
PLANNER_GROUP_ID = f"{PREFIX}_planner"
WRITER_GROUP_ID = f"{PREFIX}_writer"
REVIEWER_GROUP_ID = f"{PREFIX}_reviewer"

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
AGENT_TIMEOUT_SECONDS = float(os.getenv("HW8_AGENT_TIMEOUT_SECONDS", "180"))
