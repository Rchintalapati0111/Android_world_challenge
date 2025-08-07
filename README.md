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

├── enhanced_evaluation.py     # CLI entrypoint for benchmarking
├── name_index_evaluator.py   # Name-index RL evaluator module
├── scripts/
│   └── emulator_run.py       # Replays JSON rollouts on Android emulator
├── runs/
│   ├── llm_results/          # JSON outputs from CLI evaluations
│   ├── llm_rollouts_v2/      # Rollouts from RL-enhanced evaluator
│   └── run_/      # Original AndroidWorld episode files
├── evaluation_output/
│   ├── comprehensive_benchmark_.json
│   └── benchmark_summary_.csv
└──


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


