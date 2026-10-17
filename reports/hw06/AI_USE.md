# AI Use Statement

1  What I used an AI assistant for and what I did myself
I used Codex to assist with implementing and reviewing parts of the MongoDB and memory-system code and troubleshooting integration issues with the existing project. I ran the services locally, inspected the API and MongoDB results, executed the experiments, collected the screenshots, reviewed the reported metrics, and verified the final submission.

2  One output I independently verified
I independently verified whether the provided long-term-memory demo could be copied directly. The demo used Flask and a hosted OpenAI model, while HW6 required the existing FastAPI application and local Ollama adapter. I also found that the initial Uvicorn launch configuration could not import the root-level src package.

3  How I detected and verified the issue
I compared the demo architecture with the HW6 requirements and my existing project structure. I then ran the application locally and observed ModuleNotFoundError: No module named 'src'. After adjusting the launch environment, I confirmed the solution through the /health endpoint, API tests, MongoDB Compass, and the final 9/9 smoke verification.

4  What I changed and why it works
I retained FastAPI and the existing src/model_client.py local Ollama adapter, then integrated MongoDB-backed memory around that structure. I launched the application with PYTHONPATH set to both the repository root and the code directory. This preserved the existing architecture while allowing the HW6 routers and model adapter to load correctly.
