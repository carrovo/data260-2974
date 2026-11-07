"""Shared configuration for DATA 260 Homework 9."""

import os

from dotenv import load_dotenv

load_dotenv()

SID4 = 2974
PORT_BASE = 8274
PREFIX = "s2974"
SEED = 2974
VERIFY_SEED = 262974
DOMAIN_ID = 6

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
VIEW_SYNC_INTERVAL = 10

STUDENT_NAME = os.getenv("HW9_STUDENT_NAME", "Xuanhua Li")
