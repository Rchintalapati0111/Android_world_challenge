#!/usr/bin/env python3
"""
Replay LLM rollout JSON files on the Android emulator (AndroidWorld).
Works with the JSON you saved in runs/llm_rollouts/*.json.

Usage:
  python scripts/replay_llm_rollout.py --json runs/llm_rollouts/CameraTakePhoto_0__openai.json \
    --non-interactive --delay 1.0
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Make sure android_world is importable when you run this from repo root
sys.path.insert(0, os.path.abspath("."))

from android_world import registry
from android_world.env import env_launcher, json_action


def find_adb_directory(adb_arg: Optional[str]) -> str:
    """
    Return the full path to the adb binary.
    Accepts either a directory (platform-tools) or a direct path to adb.
    """
    if adb_arg:
        p = Path(adb_arg).expanduser().resolve()
        if p.is_file() and p.name == "adb":
            return str(p)
        if p.is_dir():
            # If user passed the directory, append adb
            print(" You passed a directory to --adb; using <dir>/adb automatically.")
            return str(p / "adb")
        raise FileNotFoundError(f"--adb path not found: {adb_arg}")

    # Default macOS path; change if yours is different
    default_dir = Path("~/Library/Android/sdk/platform-tools").expanduser()
    adb_path = default_dir / "adb"
    return str(adb_path)


def load_rollout(json_path: str) -> Dict[str, Any]:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_env_and_task(task_name: str, goal: Optional[str], adb_path: str):
    # Get task class from registry and create a task instance (random params)
    task_registry = registry.TaskRegistry().get_registry(
        registry.TaskRegistry.ANDROID_WORLD_FAMILY
    )
    if task_name not in task_registry:
        raise ValueError(f"Task '{task_name}' not found in AndroidWorld registry")
    task_cls = task_registry[task_name]
    task = task_cls(task_cls.generate_random_params())
    if goal:
        # Show goal to user; task.goal is still used by AndroidWorld for success check
        print(f"🎯 Goal: {goal}")

    # Launch environment
    env = env_launcher.load_and_setup_env(console_port=5554, adb_path=adb_path)
    env.reset(go_home=True)

    # Initialize the task in the environment
    task.initialize_task(env)
    return env, task


def response_to_json_action(resp: Dict[str, Any]) -> Optional[json_action.JSONAction]:
    """
    Convert your saved 'response' dict into AndroidWorld JSONAction.
    We keep this conservative and handle the common actions you used.
    """
    if not resp:
        return None

    t = (resp.get("action_type") or "").lower()

    try:
        if t == "open_app":
            # Use 'name' as the app_name
            return json_action.JSONAction(action_type="open_app",
                                          app_name=resp.get("name", ""))

        elif t == "click":
            # Click by index (your JSON has index)
            idx = int(resp.get("index", -1))
            return json_action.JSONAction(action_type="click", index=idx)

        elif t == "input_text":
            # If your responses ever include text, pass it through
            text = resp.get("text") or resp.get("name") or ""
            idx = resp.get("index")
            if idx is None:
                return json_action.JSONAction(action_type="input_text", text=text)
            else:
                return json_action.JSONAction(action_type="input_text",
                                              text=text, index=int(idx))

        elif t == "scroll":
            # Default to down if not specified
            direction = resp.get("direction", "down")
            return json_action.JSONAction(action_type="scroll",
                                          direction=direction)

        elif t == "status":
            return json_action.JSONAction(action_type="status",
                                          goal_status=resp.get("target", "complete"))

        # Unknown action types -> skip
        return None

    except Exception:
        return None


def replay(json_path: str, interactive: bool, delay: float, adb: Optional[str]):
    print(f" Loading rollout: {json_path}")
    data = load_rollout(json_path)

    task_name = data.get("task_name") or "UnknownTask"
    goal = data.get("goal") or ""
    provider = data.get("provider") or "unknown"

    print(f" Task: {task_name}")
    print(f" Provider: {provider}")
    if goal:
        print(f"🎯 Goal: {goal}")

    adb_path = find_adb_directory(adb)
    print(f" Using adb: {adb_path}")

    # Bring up AndroidWorld and initialize the task
    env, task = setup_env_and_task(task_name, goal, adb_path)

    # We prefer 'responses' because they include structured fields
    responses = data.get("responses", [])
    actions_str = data.get("actions", [])

    if not responses and not actions_str:
        print("⚠️ No responses/actions found in this JSON. Nothing to replay.")
        env.close()
        return

    total = max(len(responses), len(actions_str))
    print(f"\n Starting replay of {total} steps"
          f" {'(interactive)' if interactive else f'(delay={delay}s)'}\n")

    for i in range(total):
        # Pretty header
        print(f"═══ Step {i+1} ═══")

        # Show what the LLM said (if present)
        if i < len(responses) and isinstance(responses[i], dict):
            r = responses[i]
            print(f" LLM Response: {r}")
            action_obj = response_to_json_action(r)
        else:
            # Fallback: parse string like "CLICK(Shutter, index=2)" if needed
            s = actions_str[i] if i < len(actions_str) else ""
            print(f"LLM Action String: {s}")
            action_obj = None  # you could add a regex parser here if ever needed

        if not action_obj:
            print(" Could not convert this step to a JSONAction. Skipping.\n")
            continue

        # Execute
        try:
            print(f"⚡ Executing: {action_obj}")
            env.execute_action(action_obj)
            print("✅ Done\n")
        except Exception as e:
            print(f"❌ Execution failed: {e}\n")

        # If STATUS was used, stop
        if action_obj.action_type == "status":
            print(f" Encountered STATUS: {getattr(action_obj, 'goal_status', '')}. Stopping.")
            break

        # Pause
        if interactive:
            user = input("Press Enter for next step, 'q' to quit, 's' to auto-run: ").strip().lower()
            if user == "q":
                print(" Stopped by user.")
                break
            if user == "s":
                interactive = False
        else:
            if delay > 0:
                time.sleep(delay)

    # Optional success check
    try:
        success = (task.is_successful(env) == 1)
        print(f"\n Task success now: {'✅ YES' if success else '❌ NO'}")
    except Exception as e:
        print(f"\n Could not evaluate success: {e}")

    env.close()
    print(" Replay finished!")
    

def main():
    p = argparse.ArgumentParser(description="Replay LLM rollout JSON on emulator")
    p.add_argument("--json", required=True, help="Path to your rollout JSON (runs/llm_rollouts/*.json)")
    p.add_argument("--adb", default=None, help="Path to adb or its platform-tools directory")
    p.add_argument("--non-interactive", action="store_true", help="Do not pause between steps")
    p.add_argument("--delay", type=float, default=1.0, help="Delay between steps if non-interactive")
    args = p.parse_args()

    replay(
        json_path=args.json,
        interactive=not args.non_interactive,
        delay=args.delay,
        adb=args.adb,
    )


if __name__ == "__main__":
    main()
