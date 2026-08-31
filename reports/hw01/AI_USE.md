## 1. What I Used an AI Assistant For and What I Did Myself

I used an AI coding assistant throughout the development process for requirement interpretation, implementation support, code explanations, debugging assistance, and documentation feedback.

My work involved adapting and integrating the project code for my assigned rental-housing domain and personal configuration. I connected the HTML form and JavaScript behavior, configured and tested the Docker application, set up the local Ollama environment, integrated the agent pipeline and reusable model client, configured the experiment runner, and organized the required source code and report artifacts.

I reviewed and modified the implementation during testing. I diagnosed empty model responses, adjusted the reasoning and output settings, strengthened the agent instructions, verified the browser and console behavior, ran the 40-run experiment, examined incorrect model responses, and recorded the resulting logs, token counts, metrics, and screenshots.

I was responsible for testing the completed system against the homework requirements and deciding which changes and results were included in the final submission.

## 2. One AI-Produced Output That Was Wrong or Unsuitable

The AI assistant suggested enabling reasoning mode in the interactive model client to improve the quality of the model's code reviews. This suggestion was unsuitable for my local configuration. With reasoning enabled, the model consumed the complete output allowance but produced no visible final response. Increasing the output limit from 400 to 1024 tokens did not solve the problem.

## 3. How I Detected or Verified the Problem

I did not assume that the suggested setting was correct. I ran the interactive client and tested it with multiple code-review prompts. The terminal showed an empty `Model>` section, an output-token count exactly equal to the configured limit, and `Bullet-only check: FAIL`.

I repeated the test after increasing the output limit from 400 to 1024 tokens. The same problem occurred, which confirmed that simply increasing the limit was not an effective solution.

## 4. What I Changed and Why It Works Now

I changed the interactive client from `reasoning=True` to `reasoning=False`. I then restarted the client and tested it again. The model produced a visible bullet-point response, and the automatic bullet-only check passed.

I used the revised configuration for the formal five-turn conversation. All five turns produced visible responses and passed the required format check. Disabling reasoning worked because the model no longer spent its entire output allowance on hidden reasoning before producing the final response.

I still reviewed the visible responses manually because passing the format check did not guarantee that every code-review statement was factually correct.