# HW7 Generative AI Use Disclosure

## 1. What did I use an AI assistant for, and what did I do myself?

I used an AI assistant to clarify parts of the assignment, review code, and
help troubleshoot errors. I ran the application and experiments locally,
checked the outputs, made implementation decisions, collected the screenshots,
and prepared the final submission.

## 2. What AI-produced output was wrong or unsuitable?

One early suggestion for the Part 4 correction process did not work reliably
with the local model. The correction messages were too similar, so the model
sometimes repeated the same response instead of continuing to the next
required tool.

## 3. How did I detect or independently verify the problem?

I found the problem by running the workflow with `qwen3:8b` on my Mac. Although
the offline tests passed, the real run stopped before completing all required
tools. I checked the safe diagnostics and repeated the test after making
changes.

## 4. What did I change, and why does it work now?

I made the correction messages more specific about the next required step and
kept the number of retries bounded. I then reran the offline tests and both
Part 4 scenarios. Both scenarios completed successfully and passed the
independent verification.
