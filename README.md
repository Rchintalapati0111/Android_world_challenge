# Android World LLM Agent Evaluation

This project provides a comprehensive framework for evaluating Android UI automation agents using multiple prompting strategies, reinforcement learning (RL) memory, and name-index prediction accuracy. It supports OpenAI, Anthropic (Claude), and Mistral models via function calling, and it generates detailed JSON rollouts for emulator replay.

## Features

Multi-Model Support: OpenAI (gpt-4), Anthropic (Claude), Mistral via OpenAI-compatible endpoint.

## Prompting Strategies:

1. Zero-Shot

2. Few-Shot

3. Self-Reflection

## Reinforcement Learning Memory:

1. Records action success patterns

2. Name-index mapping suggestions

3. Goal strategy learning

## Name-Index Prediction:

1. Precise selection of UI elements by name and index

2. Fuzzy matching for semantic accuracy

## JSON Rollout Generation:

1. Saves detailed per-step records

2. Compatible with scripts/emulator_run.py for replay

## Comprehensive Benchmarking:

1. Temperature variants (deterministic vs. balanced)

2. Step/semantic accuracy, hallucination rates, RL rewards

3. Failure analysis and learning progression

4. Dashboard Visualization (Streamlit + Plotly)

5. Performance trends over episodes

6. Memory system insights


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


### Running CLI Benchmark

```bash
# Basic evaluation
python scripts/part3.py

# Include emulator rollout extraction
python scripts/part3.py --with-emulator

# Streamlit dashboard
python scripts/part3.py --streamlit

# Replay a JSON rollout on emulator
python scripts/emulator_run.py \
  --json runs/llm_results/CameraTakePhoto_0__openai.json \
  --adb ~/Library/Android/sdk/platform-tools \
  --non-interactive --delay 3.0
``` 

## Contributing

Contributions are welcome! Please open issues or submit pull requests for bug fixes, new features, or documentation improvements.


