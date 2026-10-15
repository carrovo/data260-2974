# AGENT.md Function Verification

Function checked: `normalize_listing_title` in `code/hw6_agent_compliant.py`.

- Project description: the function validates the primary title field of the rental-listing domain.
- Technology stack: it is implemented in Python and can be called by the existing FastAPI application.
- Coding conventions: it has type hints, a concise docstring, a single responsibility, and clear validation errors.
- Testing approach: `code/test_hw6_offline.py` checks normal, blank, non-string, and over-100-character inputs.
- Prohibited actions: it performs no network requests, reads no secrets, and sends no data to a hosted model.
