import json
import re
import gzip
import pickle
import os
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path

from openai import OpenAI
import anthropic

# ─── AUTHENTICATION SETUP ─────────────────────────────────────────────────────
# export OPENAI_API_KEY="your-openai-key"
# export ANTHROPIC_API_KEY="your-anthropic-key"
# export MISTRALAI_API_KEY="your-mistral-key"

# ─── 1. REAL DATA LOADER ───────────────────────────────────────────────────────
def load_real_episode(episode_path: str) -> Dict[str, Any]:
    print(f"Loading real episode from: {episode_path}")
    with gzip.open(episode_path, "rb") as f:
        raw = pickle.load(f)
    return raw[0] if isinstance(raw, list) else raw

def extract_ui_elements_with_indices(episode_data: Dict) -> List[List[Dict[str, Any]]]:
    ui_steps = episode_data.get("episode_data", {}).get("before_element_list", [])
    indexed_steps = []
    for step in ui_steps:
        step_elements = []
        for idx, el in enumerate(step):
            label = getattr(el, 'text', '') or getattr(el, 'content_description', '') or f"<unknown {idx}>"
            if label.strip():
                step_elements.append({
                    "index": idx,
                    "label": label.strip(),
                    "clickable": getattr(el, 'is_clickable', False)
                })
        indexed_steps.append(step_elements)
    return indexed_steps

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def infer_task_from_path(episode_path: str) -> Dict[str, str]:
    """
    Best-effort task/trial inference from filename like 'CameraTakePhoto_0.pkl.gz'
    """
    name = Path(episode_path).name
    stem = name.replace(".pkl.gz", "").replace(".pkl", "")
    parts = stem.split("_")
    if len(parts) >= 2:
        return {"task_name": parts[0], "trial": parts[1]}
    return {"task_name": stem, "trial": ""}

def iso_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def ensure_out_dir(path: str) -> str:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path

def save_rollout_json(out_path: str, payload: Dict[str, Any]) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"🧾 Saved: {out_path}")

# ─── PROMPT CONSTRUCTION ──────────────────────────────────────────────────────
def build_prompt(goal: str, step_elements: List[Dict[str, Any]], history: List[str]) -> str:
    ui_text = "\n".join([
        f"[{el['index']}] {el['label']} (clickable)" if el["clickable"] else f"[{el['index']}] {el['label']}"
        for el in step_elements
    ])
    history_text = "\n".join(history) if history else "None"
    return f"""Goal: {goal}

Here is the current screen's list of visible UI elements (each element has a label and index):
{ui_text}

Previous Actions:
{history_text}

Rules:
1. Choose the best next action to move toward the goal.
2. Only CLICK elements marked as (clickable).
3. Respond in JSON format only, using this structure:
{{
  "action_type": "CLICK" | "OPEN_APP" | "INPUT_TEXT" | "SCROLL" | "STATUS",
  "name": "Label of element exactly as shown",
  "index": index of the element (e.g., 0, 1),
  "reasoning": "Why this action helps achieve the goal"
}}

Use "action_type": "STATUS" with "target": "complete" when the goal is fully achieved."""

def build_display_prompt(goal: str, step_elements: List[Dict[str, Any]], history: List[str]) -> str:
    ui_text = "\n".join([
        f"[{el['index']}] {el['label']} (clickable)" if el["clickable"] else f"[{el['index']}] {el['label']}"
        for el in step_elements
    ])
    history_text = "\n".join(history) if history else "None"
    return f"""Goal: {goal}

Here is the current screen's list of visible UI elements (each element has a label and index):
{ui_text}

Previous Actions:
{history_text}"""

# ─── FUNCTION SCHEMA ──────────────────────────────────────────────────────────
android_action_schema = {
    "name": "android_action",
    "description": "Selects the next Android UI action to move toward the goal.",
    "parameters": {
        "type": "object",
        "properties": {
            "action_type": {
                "type": "string",
                "enum": ["CLICK", "OPEN_APP", "INPUT_TEXT", "SCROLL", "STATUS"]
            },
            "name": {
                "type": "string",
                "description": "Exact label of the UI element or app"
            },
            "index": {
                "type": "integer",
                "description": "Index of the element in the visible list"
            },
            "target": {
                "type": "string",
                "description": "Use 'complete' if action_type is STATUS",
                "default": "complete"
            },
            "reasoning": {
                "type": "string",
                "description": "Why this action helps achieve the goal"
            }
        },
        "required": ["action_type"]
    }
}

# ─── JSON EXTRACTION FALLBACK ─────────────────────────────────────────────────
def safe_extract_json(text: str) -> Dict[str, Any]:
    patterns = [
        r'\{[^{}]*\}',
        r'\{[^{}]*\{[^{}]*\}[^{}]*\}',
        r'\{.*?\}',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
    return {"action_type": "STATUS", "target": "complete", "reasoning": "fallback due to parse failure"}

# ─── CALL MODEL WRAPPER ───────────────────────────────────────────────────────
def call_model(provider: str, messages: List[Dict], function_schema: Dict) -> Dict[str, Any]:
    if provider.lower() == "openai":
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4-1106-preview",
            messages=messages,
            functions=[function_schema],
            function_call={"name": function_schema["name"]}
        )
        return json.loads(response.choices[0].message.function_call.arguments)

    elif provider.lower() == "anthropic":
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        system_message = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                user_messages.append(msg)
        msg = client.messages.create(
            model="claude-3-haiku-20240307",
            system=system_message,
            messages=user_messages,
            tools=[{
                "name": function_schema["name"],
                "description": function_schema["description"],
                "input_schema": function_schema["parameters"]
            }],
            tool_choice={"type": "tool", "name": function_schema["name"]},
            max_tokens=1024
        )
        return msg.content[0].input

    elif provider.lower() == "mistral":
        client = OpenAI(
            api_key=os.getenv("MISTRALAI_API_KEY"),
            base_url="https://api.mistral.ai/v1"
        )
        response = client.chat.completions.create(
            model="mistral-large-latest",
            messages=messages,
            tools=[{
                "type": "function",
                "function": function_schema
            }],
            tool_choice="auto"
        )
        if (response.choices and
            len(response.choices) > 0 and
            response.choices[0].message.tool_calls):
            tool_call = response.choices[0].message.tool_calls[0]
            return json.loads(tool_call.function.arguments)
        else:
            content = response.choices[0].message.content or ""
            return safe_extract_json(content)
    else:
        raise ValueError(f"Unsupported provider: {provider}")

# ─── AGENT LOOP (NOW RETURNS DATA TO SAVE) ────────────────────────────────────
def run_real_agent(goal: str, ui_steps: List[List[Dict[str, Any]]], provider: str, max_steps: int = 5):
    history: List[str] = []
    actions: List[str] = []
    responses: List[Dict[str, Any]] = []
    step_records: List[Dict[str, Any]] = []

    print(f"\n{'='*60}\nRUNNING {provider.upper()} AGENT\nGoal: {goal}\n{'='*60}")

    for step in range(min(max_steps, len(ui_steps))):
        step_elements = ui_steps[step]

        full_prompt = build_prompt(goal, step_elements, history)
        display_prompt = build_display_prompt(goal, step_elements, history)
        messages = [
            {"role": "system", "content": "You are an Android UI automation agent."},
            {"role": "user", "content": full_prompt}
        ]

        print(f"\n--- Step {step+1} ---\n{display_prompt}")

        try:
            response = call_model(provider, messages, android_action_schema)
            print(f"Response: {response}")
            # Build a readable action string
            action_str = f'{response.get("action_type")}' \
                         f'({response.get("name","")}, index={response.get("index", -1)})'
            # Append collections
            history.append(action_str)
            actions.append(action_str)
            responses.append(response)

            # Per-step record (nice for later analysis)
            step_records.append({
                "step": step + 1,
                "ui_elements": step_elements,     # already JSON-serializable
                "display_prompt": display_prompt,
                "full_prompt": full_prompt,
                "response": response,
                "action_str": action_str
            })

            # Stop if STATUS complete
            if response.get("action_type") == "STATUS" and response.get("target") == "complete":
                print("\n✅ Goal Completed\n")
                break

        except Exception as e:
            print(f"❌ Error during model call: {e}")
            history.append("STATUS(complete)")
            actions.append("STATUS(complete)")
            responses.append({"action_type": "STATUS", "target": "complete", "error": str(e)})
            step_records.append({
                "step": step + 1,
                "ui_elements": step_elements,
                "display_prompt": display_prompt,
                "full_prompt": full_prompt,
                "response": {"action_type": "STATUS", "target": "complete", "error": str(e)},
                "action_str": "STATUS(complete)"
            })
            break

    return {
        "actions": actions,
        "responses": responses,
        "step_records": step_records,
        "steps": len(step_records),
        "provider": provider
    }

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    # Detect available providers by API keys
    api_keys = {
        "OPENAI_API_KEY": ("OpenAI", "openai"),
        "ANTHROPIC_API_KEY": ("Anthropic", "anthropic"),
        "MISTRALAI_API_KEY": ("Mistral AI", "mistral")
    }
    available_providers = []
    missing_keys = []
    for key, (provider_name, provider_code) in api_keys.items():
        if os.getenv(key):
            available_providers.append(provider_code)
        else:
            missing_keys.append(f"{key} (for {provider_name})")
    if missing_keys:
        print("⚠️  Missing API keys:")
        for key in missing_keys:
            print(f"   - {key}")
        print("\nWill only run available providers.")
        if not available_providers:
            print("No API keys found. Please set at least one.")
            print("Example: export OPENAI_API_KEY='your-key-here'")
            return

    # Inputs (you can make these argparse if you want)
    episode_path = "runs/run_20250720T123202422603/CameraTakePhoto_0.pkl.gz"
    out_dir = ensure_out_dir("runs/llm_results")  # where JSONs will be saved

    if not os.path.exists(episode_path):
        print(f"❌ Episode file not found: {episode_path}")
        return

    episode_data = load_real_episode(episode_path)
    ui_steps = extract_ui_elements_with_indices(episode_data)
    goal = "Take a photo using the camera app"
    meta = infer_task_from_path(episode_path)
    task_name = meta["task_name"]
    trial = meta["trial"]

    print(f" Loaded real Android episode with {len(ui_steps)} UI steps")
    print(f" Goal: {goal}")
    print(f" Available providers: {', '.join(available_providers)}")

    for provider in available_providers:
        result = run_real_agent(goal, ui_steps, provider)

        # Build a single JSON payload per provider
        payload = {
            "task_name": task_name,
            "trial": trial,
            "goal": goal,
            "provider": provider,
            "episode_path": episode_path,
            "created_at": iso_now(),
            "steps": result["steps"],
            "actions": result["actions"],
            "responses": result["responses"],        # raw dict outputs from the LLM/tool call
            "step_records": result["step_records"]   # detailed per-step info
        }

        # Save file like: runs/llm_rollouts/CameraTakePhoto_0__openai.json
        filename = f"{task_name}_{trial}__{provider}.json" if trial else f"{task_name}__{provider}.json"
        out_path = str(Path(out_dir) / filename)
        save_rollout_json(out_path, payload)

if __name__ == "__main__":
    main()
