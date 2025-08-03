# Android World LLM Agent Evaluation

Lightweight framework for evaluating LLMs (OpenAI GPT-4, Anthropic Claude, Mistral) as agents navigating Android UI tasks using the `android_world` benchmark. Supports multi-strategy prompting (zero-shot, few-shot, self-reflection), memory-enhanced name-index reasoning, structured function calling, and temperature variants.

## Features

- Episode loader for Android UI goals (e.g., take photo, move file, add contact).  
- Prompting strategies: Zero-shot, Few-shot (adaptive examples), Self-reflection.  
- Enhanced memory: name-index mappings, failure patterns, goal strategies.  
- Function-calling / structured outputs to reduce parsing errors.  
- Multi-model support: OpenAI, Anthropic/Claude, Mistral.  
- Evaluation metrics: step accuracy, semantic/name-index accuracy, hallucination detection, episode success, RL-style reward.  
- Temperature variants (deterministic vs balanced) for robustness.  
- Report generation (Markdown/JSON) with failure analysis and illustrative examples.  

## Prerequisites

- Python 3.8+  
- API keys (set as environment variables):  
  - `OPENAI_API_KEY` (for GPT-4 / Mistral if using OpenAI-compatible endpoint)  
  - `ANTHROPIC_API_KEY` (for Claude)  
  - `MISTRALAI_API_KEY` (if using Mistral via its endpoint) 


## Folder Structure
- `src/` — Python codebase for agent execution and evaluation
- `prompts/` — Prompt templates (PDF)
- `results.md` — Output logs of model predictions
- `report.md` — Summary of findings and insights


