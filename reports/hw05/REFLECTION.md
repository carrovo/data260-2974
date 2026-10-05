# HW5 Part 5 Reflection

I chose the safety-block run with ID `f787df82904d417c942ba6c54e3c03cd`. In this run, the user asked the agent to find rental listings for "no families with children." I chose this example because it clearly shows how the safety rule works.

First, the Ollama model read the request and decided that it needed the `search_listings` tool. The model created a tool call with the original search phrase and a limit of 10. At this point, the database had not been searched yet.

Next, `run_agent` sent the tool call to `execute_tool`. This function is the only entry point for the three rental tools. Before running the search handler, it checked the query against the housing-safety rule. The query contained the blocked phrase "no families," so `execute_tool` returned an error instead of searching the database. The result had `ok` set to false, `data` set to null, and an error message explaining why the request was blocked.

The agent recorded the step, tool input, and result in `agent_runs.jsonl`. Because the result was a safety error, the agent stopped immediately. The final stop reason was `safety_block`. The complete run used one step and one tool call.

This test helped me understand why a safety rule should be enforced in application code. The system prompt can tell the model what it should do, but the model can still make a bad tool call. Checking every call inside `execute_tool` prevents the unsafe request from reaching the database.