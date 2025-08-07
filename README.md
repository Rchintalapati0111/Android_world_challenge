# Android World LLM Agent Evaluation

This project provides a comprehensive framework for evaluating Android UI automation agents using multiple prompting strategies, reinforcement learning (RL) memory, and name-index prediction accuracy. It supports OpenAI, Anthropic (Claude), and Mistral models via function calling, and it generates detailed JSON rollouts for emulator replay.

## Features

Multi-Model Support: OpenAI (gpt-4), Anthropic (Claude), Mistral via OpenAI-compatible endpoint.

## Prompting Strategies:

Zero-Shot

Few-Shot

Self-Reflection

## Reinforcement Learning Memory:

Records action success patterns

Name-index mapping suggestions

Goal strategy learning

## Name-Index Prediction:

Precise selection of UI elements by name and index

Fuzzy matching for semantic accuracy

## JSON Rollout Generation:

Saves detailed per-step records

Compatible with scripts/emulator_run.py for replay

## Comprehensive Benchmarking:

Temperature variants (deterministic vs. balanced)

Step/semantic accuracy, hallucination rates, RL rewards

Failure analysis and learning progression

Dashboard Visualization (Streamlit + Plotly)

Performance trends over episodes

Memory system insights

android-agent-evaluation/
├── enhanced_evaluation.py     # CLI entrypoint for benchmarking
├── name_index_evaluator.py   # Name-index RL evaluator module
├── scripts/
│   └── emulator_run.py       # Replays JSON rollouts on Android emulator
├── runs/
│   ├── llm_results/          # JSON outputs from CLI evaluations
│   ├── llm_rollouts_v2/      # Rollouts from RL-enhanced evaluator
│   └── run_TIMESTAMP/        # Original AndroidWorld episode files
├── evaluation_output/
│   ├── comprehensive_benchmark_TIMESTAMP.json
│   └── benchmark_summary_TIMESTAMP.csv
└── README.md


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


