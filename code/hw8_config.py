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
