Evaluating LLM Agents in AndroidWorld Project: Prompting, Performance, and their Limitations 

1. Approach to Prompting and Evaluation: 

I implemented three prompting strategies to guide a GPT-4 agent in navigating Android UI tasks:

A. Zero-shot prompting: The LLM is only provided the goal and current UI elements.

B. Few-shot prompting: Includes exemplar agent behaviors from similar tasks to improve grounding.

C. Self-reflection prompting: Encourages the agent to reflect on progress, verify actions, and reason before acting.

The agent loop loads episodes from the AndroidWorld benchmark, generates prompts based on the current UI screen, and queries GPT-4 to predict the next best action. Prompts were made configurable and reusable across episodes.

2. Summary of the Performance Metrics: 

I evaluated 10 episodes (5 unique × 2 variants) using all three prompt styles, collecting step-by-step logs and metrics.

(In the third part of the question, I selected 5 unique tasks from the AndroidWorld benchmark and evaluated 2 different episode variants for each task, making a total of 10 episodes. Each episode was run separately using all three prompting strategies: zero-shot, few-shot, and self-reflection—while logging the agent's step-by-step predictions. The predicted actions were then compared against ground-truth to compute step accuracy, success rate, and hallucination rate)

The following table has the information - 

Prompt Variant	Step Accuracy	Episode Success Rate	Hallucination Rate
Zero-Shot	       10.9%	            0.0%	               1.5%
Few-Shot	       25.6%	           40.0%	               4.0%
Self-Reflection	 18.4%	           40.0%	               5.3%

Where, 

A. Step Accuracy: Percentage of individual actions correctly predicted compared to ground truth steps
B. Episode Success Rate: Proportion of episodes where the agent fully completed the task goal
C. Hallucination Rate: Frequency of actions involving UI elements that were not present in the given observation

3. Example Episodes: 

A. CameraTakePhoto: 

Goal: Take one photo.

Few-Shot Prompt:

Step 1: OPEN_APP("Camera") ✅

Step 2: CLICK("Shutter") ❌ (expected: CLICK("element_2"))

Step 3: STATUS("complete") ✅

Success: ✅

B. ContactsAddContact: 

Goal: Add Hugo Pereira, +13920741751

Few-Shot Prompt:

Correct input fields: Hugo, Pereira, +13920741751

Incorrect: Clicked "Save" instead of index-based element

Success: ✅

C. FilesMoveFile: 

Goal: Move file from Podcasts → DCIM

All Prompts:

Major failures due to complex multi-step navigation

Hallucinations: "Move here", "DCIM"

Success: ❌

4. Failure Analysis: 

A. Where LLMs Fail ?

- When complex multi-step tasks are involved (e.g., FilesMoveFile)

- Mapping semantic labels to element indices (e.g., "Save" vs element_2)

- Forgetting previous actions in long tasks

B. Why LLMs Fail ? 

- Format mismatch: LLM uses visible text; ground truth uses index-based actions

- Limited memory: LLM can't fully recall UI progress or app states

- Goal misunderstanding: Partial completion or wrong app

- Hallucination: Generates plausible but invalid UI elements which causes the issue of hallucination

5. Interesting Behaviors Observed in the Project: 

- Hallucinations: The agent predicts actions involving UI elements like "Move here" or "Paste" that don't actually exist in the current screen.

- Overgeneralization: The model applies the same action (like clicking "Shutter") across tasks without checking if it's contextually appropriate.

- Self-Reflection Benefits: Encouraging the agent to reflect improves decision-making, but it still struggles with following the exact action format (e.g., using labels instead of indices).

6. Recommendations for Improving Agent Behavior: 

- Integrate short-term memory buffer to retain action and observation history

- Add UI index-to-label mapping to align predicted vs ground-truth actions

- Implement search + verification sub-agents to validate UI presence before acting

- Try tool-augmented prompting (e.g., function calling) for stricter outputs

Learnings: 

This project was one of the most exciting explorations I’ve participated in - prompting and evaluating Android-based LLM agents. I learned how even small changes in prompt design, like providing few-shot examples or asking the model to self-reflect, can significantly impact an agent’s reasoning and performance. Implementing fuzzy matching (RapidFuzz) taught me how to bridge the gap between model predictions and ground-truth data. I understood the limitations of LLMs in real-life applications, like the tendency to hallucinate, forgetting past steps, or misinterpreting UI semantics. 










