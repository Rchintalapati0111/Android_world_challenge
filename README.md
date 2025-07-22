# Evaluating LLM Agents in AndroidWorld

This project explores the use of Large Language Models (LLMs) like GPT-4 for controlling Android UIs using natural language. Evaluated different prompting strategies on tasks from the AndroidWorld benchmark and analyzed agent performance using step accuracy, success rate, and hallucination rate.

##  Prompting Strategies
- **Zero-Shot**: Only goal + UI context
- **Few-Shot**: Exemplar actions with history
- **Self-Reflection**: Agent reasons about its decisions


## Folder Structure
- `src/` — Python codebase for agent execution and evaluation
- `prompts/` — Prompt templates (PDF)
- `results.md` — Output logs of model predictions
- `report.md` — Summary of findings and insights


