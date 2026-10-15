# AI Use Statement

I used Codex to help implement and review the HW6 MongoDB and memory-system code, create test and experiment scripts, and identify integration issues with the existing project. I kept the existing application structure and will run the services, inspect the outputs, collect screenshots, and verify the final submission myself.

One item I independently verified was whether the provided long-term-memory demo could be copied directly. It used Flask and a hosted OpenAI model, while HW6 requires the existing FastAPI application and local Ollama adapter. I therefore kept FastAPI and `src/model_client.py`, then added the required MongoDB memory logic around them.
