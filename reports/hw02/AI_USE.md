# AI Use Disclosure

## 1. How I used AI

I used ChatGPT to clarify the assignment requirements, suggest code organization, and help troubleshoot Docker, Git, FastAPI, and LangGraph issues. I implemented and adjusted the files in Cursor, ran the application and experiments locally, checked the outputs, and prepared the final screenshots.

## 2. One thing I independently verified

I verified that the correction loop and turn ceiling worked correctly. A normal successful run was not enough to test this because the Reviewer approved the Planner output on the first attempt.

## 3. How I verified it

I temporarily forced the Reviewer to always return an issue and ran the graph with a turn ceiling of 2. The stream output showed that the Supervisor sent the task back to the Planner and stopped the graph after two attempts.

## 4. What I changed

I added a controlled test option for forcing Reviewer issues. After confirming that the graph ended with an `abandoned` status at the ceiling, I returned the Reviewer to its normal behavior. This showed that the graph would not continue looping forever.