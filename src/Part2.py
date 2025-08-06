#!/usr/bin/env python3
"""
Enhanced Android Agent with RL, Memory, and Function Calling
+ JSON Rollout Saving (compatible with your previous replay style)

What’s new:
- Saves one JSON per (episode × model × strategy) at runs/llm_results2/
- Includes actions (Reason/Action format), responses (structured), and step_records
"""

import gzip
import pickle
import glob
import re
import os
import json
from typing import List, Dict, Tuple, Optional
from rapidfuzz import fuzz, process
from datetime import datetime
from pathlib import Path
from collections import defaultdict, deque
import numpy as np

from openai import OpenAI
import anthropic

# ===================== JSON SAVE HELPERS =====================

def iso_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def ensure_out_dir(path: str) -> str:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path

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

def save_rollout_json(out_path: str, payload: Dict[str, any]) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"🧾 Saved: {out_path}")

# ===== FUNCTION CALLING SCHEMA =====

android_action_schema = {
    "name": "android_action",
    "description": "Selects the next Android UI action to move toward the goal with precise targeting.",
    "parameters": {
        "type": "object",
        "properties": {
            "action_type": {
                "type": "string",
                "enum": ["CLICK", "OPEN_APP", "INPUT_TEXT", "SCROLL", "STATUS"],
                "description": "Type of action to perform"
            },
            "name": {
                "type": "string",
                "description": "Exact label/name of the UI element or app as shown in the list"
            },
            "index": {
                "type": "integer",
                "description": "Index number of the element in the visible UI list (critical for accuracy)"
            },
            "target": {
                "type": "string",
                "description": "Use 'complete' when action_type is STATUS",
                "default": "complete"
            },
            "reasoning": {
                "type": "string",
                "description": "Why this action helps achieve the goal"
            }
        },
        "required": ["action_type", "reasoning"]
    }
}

# ===== ENHANCED MEMORY SYSTEM =====

class EnhancedActionMemory:
    """Advanced memory system with RL and pattern learning"""
    def __init__(self):
        self.action_success_patterns = defaultdict(list)  # action -> success rates
        self.ui_element_mappings = defaultdict(set)       # semantic -> element_X mappings
        self.goal_strategies = defaultdict(list)          # goal_type -> successful action sequences
        self.failure_patterns = defaultdict(int)          # failed_action -> count
        self.episode_rewards = []
        self.name_index_mappings = defaultdict(list)      # name -> successful indices
        self.learning_rate = 0.1
        
    def record_action_result(self, action_data: Dict, ui_elements: List[str], truth_action: str, 
                           success: bool, goal: str):
        """Record action result for learning with name+index tracking"""
        action_str = f"{action_data.get('action_type', '')}({action_data.get('name', '')}, index={action_data.get('index', -1)})"
        self.action_success_patterns[action_str].append(success)
        
        if success and action_data.get('name') and action_data.get('index') is not None:
            element_name = action_data['name']
            element_index = action_data['index']
            self.name_index_mappings[element_name].append(element_index)
        
        if success and "element_" in truth_action:
            if action_data.get('name') and "element_" in truth_action:
                semantic_name = action_data['name']
                element_match = re.search(r'element_(\d+)', truth_action)
                if element_match:
                    element_id = f"element_{element_match.group(1)}"
                    self.ui_element_mappings[semantic_name].add(element_id)
        
        goal_type = goal.split()[0].lower() if goal else "unknown"
        if success:
            self.goal_strategies[goal_type].append(action_str)
        else:
            self.failure_patterns[action_str] += 1
    
    def get_best_index_for_name(self, name: str) -> Optional[int]:
        if name in self.name_index_mappings:
            indices = self.name_index_mappings[name]
            if indices:
                return max(set(indices), key=indices.count)
        return None
    
    def get_element_mapping_suggestion(self, semantic_name: str) -> Optional[str]:
        if semantic_name in self.ui_element_mappings:
            mappings = list(self.ui_element_mappings[semantic_name])
            return mappings[0] if mappings else None
        return None
    
    def get_action_success_rate(self, action: str) -> float:
        if action in self.action_success_patterns:
            successes = self.action_success_patterns[action]
            return sum(successes) / len(successes)
        return 0.5
    
    def get_goal_strategy_suggestions(self, goal: str) -> List[str]:
        goal_type = goal.split()[0].lower() if goal else "unknown"
        if goal_type in self.goal_strategies:
            return self.goal_strategies[goal_type][-3:]
        return []
    
    def should_avoid_action(self, action: str) -> bool:
        if action in self.failure_patterns:
            failure_count = self.failure_patterns[action]
            success_count = len([s for s in self.action_success_patterns.get(action, []) if s])
            total_attempts = failure_count + success_count
            if total_attempts >= 3:
                failure_rate = failure_count / total_attempts
                return failure_rate > 0.7
        return False

# ===== THREE PROMPTING STRATEGIES =====

def build_zero_shot_prompt(goal: str, step_elements: List[Dict[str, any]], history: List[str], memory: EnhancedActionMemory) -> str:
    ui_text = "\n".join([
        f"[{el['index']}] {el['label']} (clickable)" if el.get("clickable") else f"[{el['index']}] {el['label']}"
        for el in step_elements
    ])
    history_text = "\n".join(history) if history else "None"
    return f"""You are an Android UI automation agent. Your task is to help achieve the following goal.

Goal: {goal}

Current screen UI elements (each has a label and index):
{ui_text}

Previous Actions:
{history_text}

Instructions:
- Choose the best next action to move toward the goal
- Provide both the exact element name and its index number
- Use the function calling interface to respond with action_type, name, index, and reasoning

Choose your next action."""

def build_few_shot_prompt(goal: str, step_elements: List[Dict[str, any]], history: List[str], memory: EnhancedActionMemory) -> str:
    ui_text = "\n".join([
        f"[{el['index']}] {el['label']} (clickable)" if el.get("clickable") else f"[{el['index']}] {el['label']}"
        for el in step_elements
    ])
    history_text = "\n".join(history) if history else "None"
    examples = _generate_few_shot_examples(goal, memory)
    return f"""You are an Android UI automation agent. Learn from these examples and apply the patterns.

{examples}

CURRENT TASK:
Goal: {goal}

Current screen UI elements (each has a label and index):
{ui_text}

Previous Actions:
{history_text}

Strategy:
- Learn from the example patterns above
- Match element names with their correct indices
- Follow successful action sequences
- Use function calling to provide structured responses

Choose your next action based on the learned patterns."""

def build_self_reflection_prompt(goal: str, step_elements: List[Dict[str, any]], history: List[str], memory: EnhancedActionMemory) -> str:
    ui_text = "\n".join([
        f"[{el['index']}] {el['label']} (clickable)" if el.get("clickable") else f"[{el['index']}] {el['label']}"
        for el in step_elements
    ])
    history_text = "\n".join(history) if history else "None"
    memory_insights = _generate_reflection_insights(goal, step_elements, memory)
    return f"""You are an Android UI automation agent with self-reflection capabilities. Think through this step-by-step.

Goal: {goal}

Current screen UI elements (each has a label and index):
{ui_text}

Previous Actions:
{history_text}

{memory_insights}

SELF-REFLECTION PROCESS:
[... trimmed for brevity in this comment block, full detail preserved in your previous version ...]
Work through each reflection step, then use function calling to provide your action with action_type, name, index, and reasoning."""

def _generate_few_shot_examples(goal: str, memory: EnhancedActionMemory) -> str:
    goal_l = goal.lower() if goal else ""
    if "photo" in goal_l or "camera" in goal_l:
        return """CAMERA TASK EXAMPLES:

Example 1 - Taking a photo:
Goal: Take a photo using the camera app
UI Elements: [0] Home, [1] Phone (clickable), [2] Camera (clickable), [9] Photos (clickable)
Action: {"action_type": "OPEN_APP", "name": "Camera", "index": 2, "reasoning": "Need to open camera app first"}

Next screen: [0] Options (clickable), [1] Shutter (clickable), [2] Switch camera (clickable)
Action: {"action_type": "CLICK", "name": "Shutter", "index": 1, "reasoning": "Click shutter to take photo"}

Example 2 - Alternative camera access:
UI Elements: [8] Photos (clickable), [9] Gallery (clickable), [10] Camera (clickable)
Action: {"action_type": "CLICK", "name": "Photos", "index": 8, "reasoning": "Photos app often has camera access"}

KEY PATTERNS:
- Camera apps usually at index 2 or accessible via Photos
- Shutter buttons typically at index 1 or 2
- Always verify the exact index matches the element name"""
    elif "contact" in goal_l:
        return """CONTACT TASK EXAMPLES:

Example 1 - Adding a contact:
Goal: Add a new contact
UI Elements: [0] Home, [1] Phone (clickable), [2] Contacts (clickable), [3] Messages (clickable)
Action: {"action_type": "CLICK", "name": "Contacts", "index": 2, "reasoning": "Open contacts app to manage contacts"}

Next screen: [0] Search, [1] Add contact (clickable), [2] Contact list
Action: {"action_type": "CLICK", "name": "Add contact", "index": 1, "reasoning": "Click add to create new contact"}

KEY PATTERNS:
- Contact apps usually need to be opened first
- Look for 'Add' or '+' buttons for creating new entries
- Index matching is critical for contact operations"""
    elif "file" in goal_l:
        return """FILE TASK EXAMPLES:

Example 1 - Moving a file:
Goal: Move file to different folder
UI Elements: [0] Home, [1] Files (clickable), [2] Downloads (clickable), [3] Gallery (clickable)
Action: {"action_type": "OPEN_APP", "name": "Files", "index": 1, "reasoning": "Open file manager to access files"}

Next screen: [0] Back, [1] Select file (clickable), [2] Menu (clickable), [3] Move (clickable)
Action: {"action_type": "CLICK", "name": "Select file", "index": 1, "reasoning": "First select the file to move"}

KEY PATTERNS:
- File operations require file manager app
- Multi-step process: select → action → destination
- Pay attention to menu options for file operations"""
    else:
        return """GENERAL TASK EXAMPLES:

Example 1 - App opening pattern:
UI Elements: [0] Home, [1] Settings (clickable), [2] Phone (clickable), [3] Messages (clickable)
Goal: Open settings
Action: {"action_type": "CLICK", "name": "Settings", "index": 1, "reasoning": "Click on Settings app to open it"}

Example 2 - UI interaction pattern:
UI Elements: [0] Back, [1] Save (clickable), [2] Cancel (clickable), [3] Options (clickable)
Goal: Save changes
Action: {"action_type": "CLICK", "name": "Save", "index": 1, "reasoning": "Click Save to complete the action"}

KEY PATTERNS:
- Match element names exactly with their indices
- Consider the goal context when choosing actions
- Verify element is clickable before selecting it"""

def _generate_reflection_insights(goal: str, step_elements: List[Dict[str, any]], memory: EnhancedActionMemory) -> str:
    insights = ["MEMORY INSIGHTS FOR REFLECTION:"]
    strategies = memory.get_goal_strategy_suggestions(goal)
    if strategies:
        insights.append("Previously successful actions for similar goals:")
        for action in strategies[-3:]:
            success_rate = memory.get_action_success_rate(action)
            insights.append(f"   ✓ {action} (success rate: {success_rate:.1%})")
    else:
        insights.append("This is a new type of goal - no previous patterns available")
    element_insights = []
    for element in step_elements[:3]:
        element_name = element.get('label', '')
        if element_name:
            best_index = memory.get_best_index_for_name(element_name)
            if best_index is not None:
                element_insights.append(f"   '{element_name}' has historically worked best at index {best_index}")
    if element_insights:
        insights.append("Element positioning insights:")
        insights.extend(element_insights)
    risk_warnings = []
    for element in step_elements[:3]:
        action = f"CLICK({element.get('label', '')}, index={element.get('index', -1)})"
        if memory.should_avoid_action(action):
            risk_warnings.append(f"   ⚠️ Avoid {action} (high failure rate)")
    if risk_warnings:
        insights.append("Actions to be cautious about:")
        insights.extend(risk_warnings)
    return "\n".join(insights)

def build_display_prompt(goal: str, step_elements: List[Dict[str, any]], history: List[str], strategy: str) -> str:
    ui_text = "\n".join([
        f"[{el['index']}] {el['label']} (clickable)" if el.get("clickable") else f"[{el['index']}] {el['label']}"
        for el in step_elements
    ])
    history_text = "\n".join(history) if history else "None"
    return f"""Strategy: {strategy.upper()}
Goal: {goal}

Here is the current screen's list of visible UI elements (each element has a label and index):
{ui_text}

Previous Actions:
{history_text}"""

def _generate_memory_guidance(goal: str, step_elements: List[Dict[str, any]], memory: EnhancedActionMemory) -> str:
    guidance_lines = ["MEMORY GUIDANCE:"]
    strategies = memory.get_goal_strategy_suggestions(goal)
    if strategies:
        guidance_lines.append("Previously successful actions for similar goals:")
        for action in strategies[-3:]:
            success_rate = memory.get_action_success_rate(action)
            guidance_lines.append(f"  ✓ {action} (success rate: {success_rate:.1%})")
    index_suggestions = []
    for element in step_elements[:5]:
        element_name = element.get('label', '')
        if element_name:
            best_index = memory.get_best_index_for_name(element_name)
            if best_index is not None:
                index_suggestions.append(f"  '{element_name}' → index {best_index} (learned)")
    if index_suggestions:
        guidance_lines.append("Learned name-to-index mappings:")
        guidance_lines.extend(index_suggestions)
    avoid_actions = []
    for element in step_elements[:3]:
        action = f"CLICK({element.get('label', '')}, index={element.get('index', -1)})"
        if memory.should_avoid_action(action):
            avoid_actions.append(action)
    if avoid_actions:
        guidance_lines.append("Actions to avoid (high failure rate):")
        for action in avoid_actions:
            guidance_lines.append(f"  ✗ {action}")
    return "\n".join(guidance_lines)

# ===== ENHANCED MODEL CALLERS WITH FUNCTION CALLING =====

def call_openai_with_functions(messages: List[Dict], schema: Dict) -> Dict[str, any]:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=messages,
        functions=[schema],
        function_call={"name": schema["name"]},
        temperature=0.1
    )
    return json.loads(response.choices[0].message.function_call.arguments)

def call_anthropic_with_functions(messages: List[Dict], schema: Dict) -> Dict[str, any]:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    system_message = None
    user_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_message = msg["content"]
        else:
            user_messages.append(msg)
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        system=system_message,
        messages=user_messages,
        tools=[{
            "name": schema["name"], 
            "description": schema["description"], 
            "input_schema": schema["parameters"]
        }],
        tool_choice={"type": "tool", "name": schema["name"]},
        max_tokens=1024,
        temperature=0.1
    )
    return response.content[0].input

def call_mistral_with_functions(messages: List[Dict], schema: Dict) -> Dict[str, any]:
    client = OpenAI(
        api_key=os.getenv("MISTRALAI_API_KEY"),
        base_url="https://api.mistral.ai/v1"
    )
    response = client.chat.completions.create(
        model="mistral-large-latest",
        messages=messages,
        tools=[{
            "type": "function",
            "function": schema
        }],
        tool_choice="auto",
        temperature=0.1
    )
    if (response.choices and 
        len(response.choices) > 0 and 
        response.choices[0].message.tool_calls):
        tool_call = response.choices[0].message.tool_calls[0]
        return json.loads(tool_call.function.arguments)
    else:
        raise ValueError("No function call in Mistral response")

# ===== ENHANCED EVALUATION WITH FUNCTION CALLING + JSON SAVE =====

class RLEnhancedEvaluator:
    """Evaluation framework with RL, memory, and three prompting strategies"""
    def __init__(self, out_dir: str = "runs/llm_rollouts_v2"):
        self.memory = EnhancedActionMemory()
        self.results = []
        self.out_dir = ensure_out_dir(out_dir)
        self.models = {
            "openai": call_openai_with_functions,
            "anthropic": call_anthropic_with_functions,
            "mistral": call_mistral_with_functions
        }
        self.prompting_strategies = {
            "zero_shot": build_zero_shot_prompt,
            "few_shot": build_few_shot_prompt,
            "self_reflection": build_self_reflection_prompt
        }
    
    def evaluate_episode_with_rl(self, episode_path: str, model_name: str, strategy_name: str) -> Dict:
        """Enhanced episode evaluation with function calling and specific prompting strategy
           Also assembles rollout JSON payload (actions/responses/step_records)."""
        print(f"\n{'='*80}")
        print(f"RL-ENHANCED EVALUATION: {os.path.basename(episode_path)}")
        print(f"Model: {model_name.upper()} | Strategy: {strategy_name.upper()} | Function Calling + Memory")
        print(f"{'='*80}")
        
        # Load episode
        episode = self._load_episode(episode_path)
        if not episode:
            return None
        
        goal = episode.get("goal", "Unknown goal")
        ui_steps = self._extract_ui_elements_with_indices(episode)
        ground_truth = self._extract_ground_truth_actions(episode)
        
        print(f"Goal: {goal}")
        print(f"{len(ui_steps)} UI steps, {len(ground_truth)} ground truth actions")
        
        if not ui_steps:
            print("❌ No UI steps found")
            return None
        
        # Get prompting strategy function
        build_prompt_func = self.prompting_strategies[strategy_name]
        
        # Track results
        predictions = []
        step_results = []
        action_history = []
        episode_reward = 0
        
        # For JSON rollout saving
        actions_for_json: List[str] = []
        responses_for_json: List[Dict[str, any]] = []
        step_records_for_json: List[Dict[str, any]] = []
        
        num_steps = min(len(ui_steps), max(1, len(ground_truth)))  # allow if ground_truth missing
        
        for step_idx in range(num_steps):
            print(f"\n--- STEP {step_idx + 1}/{num_steps} ---")
            
            step_elements = ui_steps[step_idx]
            truth_action = ground_truth[step_idx] if step_idx < len(ground_truth) else "<none>"
            
            print(f"UI Elements ({len(step_elements)}): {[el['label'] for el in step_elements[:5]]}{'...' if len(step_elements) > 5 else ''}")
            print(f"Ground Truth: {truth_action}")
            
            # Build prompt using selected strategy
            full_prompt = build_prompt_func(goal, step_elements, action_history, self.memory)
            display_prompt = build_display_prompt(goal, step_elements, action_history, strategy_name)
            
            messages = [
                {"role": "system", "content": f"You are an expert Android UI automation agent using {strategy_name} prompting strategy. Use function calling to provide structured, accurate responses."},
                {"role": "user", "content": full_prompt}
            ]
            
            print(f"\n{display_prompt}")
            
            try:
                # Get structured response via function calling
                response_data = self.models[model_name](messages, android_action_schema)
                print(f"Response: {response_data}")
                
                # Create action strings
                action_str_simple = f"{response_data.get('action_type', '')}({response_data.get('name', '')}, index={response_data.get('index', -1)})"
                # Reason/Action formatting (compatible with your replay parser that looks for "Action: {...}")
                action_json = {
                    "action_type": response_data.get("action_type"),
                    "name": response_data.get("name"),
                    "index": response_data.get("index"),
                    "target": response_data.get("target", "complete")
                }
                reason_action_str = f"Reason: {response_data.get('reasoning','')}\nAction: {json.dumps(action_json)}"
                
                # Evaluate with enhanced accuracy
                exact_match = self._check_exact_match(response_data, truth_action)
                semantic_match = self._check_semantic_match(response_data, truth_action, step_elements)
                is_hallucination = self._check_hallucination_structured(response_data, step_elements)
                
                # Calculate step reward
                step_reward = 0
                if exact_match:
                    step_reward += 2.0
                elif semantic_match:
                    step_reward += 1.5
                if is_hallucination:
                    step_reward -= 1.0
                episode_reward += step_reward
                
                # Record memory learnings
                self.memory.record_action_result(
                    response_data, [el['label'] for el in step_elements], truth_action, 
                    exact_match or semantic_match, goal
                )
                
                # Log step result
                step_result = {
                    "step": step_idx + 1,
                    "ui_elements": step_elements,
                    "ground_truth": truth_action,
                    "predicted_data": response_data,
                    "predicted_action": action_str_simple,
                    "exact_match": exact_match,
                    "semantic_match": semantic_match,
                    "is_hallucination": is_hallucination,
                    "step_reward": step_reward,
                    "display_prompt": display_prompt,
                    "full_prompt": full_prompt,
                    "reason_action_str": reason_action_str,
                }
                
                step_results.append(step_result)
                predictions.append(response_data)
                action_history.append(action_str_simple)
                
                # Append to JSON lists
                actions_for_json.append(reason_action_str)     # This is what your replay script can parse
                responses_for_json.append(response_data)       # Raw structured dict
                step_records_for_json.append({
                    "step": step_idx + 1,
                    "ui_elements": step_elements,
                    "display_prompt": display_prompt,
                    "full_prompt": full_prompt,
                    "response": response_data,
                    "action_str": action_str_simple,
                    "reason_action_str": reason_action_str
                })
                
                # Real-time feedback
                match_icon = "✅" if exact_match else ("PARTIAL" if semantic_match else "❌")
                halluc_icon = "❌" if is_hallucination else "✅"
                print(f"Result: {match_icon} Match | {halluc_icon} Valid | Reward: {step_reward:+.1f}")
                
                # Stop on STATUS complete
                if response_data.get("action_type") == "STATUS" and response_data.get("target") == "complete":
                    print("\n✅ Goal Completed")
                    break
                    
            except Exception as e:
                print(f"❌ Error during model call: {e}")
                action_history.append("STATUS(complete)")
                # Fail-safe JSON record
                fail_resp = {"action_type": "STATUS", "target": "complete", "error": str(e)}
                fail_reason_action = f"Reason: error\nAction: {json.dumps(fail_resp)}"
                actions_for_json.append(fail_reason_action)
                responses_for_json.append(fail_resp)
                step_records_for_json.append({
                    "step": step_idx + 1,
                    "ui_elements": step_elements,
                    "display_prompt": display_prompt,
                    "full_prompt": full_prompt,
                    "response": fail_resp,
                    "action_str": "STATUS(complete)",
                    "reason_action_str": fail_reason_action
                })
                break
        
        # Final metrics
        correct_actions = sum(1 for r in step_results if r["exact_match"])
        semantic_matches = sum(1 for r in step_results if r["semantic_match"])
        hallucinations = sum(1 for r in step_results if r["is_hallucination"])
        
        step_accuracy = correct_actions / len(step_results) if step_results else 0
        semantic_accuracy = semantic_matches / len(step_results) if step_results else 0
        hallucination_rate = hallucinations / len(step_results) if step_results else 0
        episode_success = any(
            (pred.get("action_type") == "STATUS" and pred.get("target") == "complete")
            for pred in predictions
        )
        self.memory.episode_rewards.append(episode_reward)
        
        # Build result
        result = {
            "episode_path": episode_path,
            "episode_name": os.path.basename(episode_path),
            "model": model_name,
            "strategy": strategy_name,
            "goal": goal,
            "total_steps": len(step_results),
            "correct_actions": correct_actions,
            "semantic_matches": semantic_matches,
            "hallucinations": hallucinations,
            "step_accuracy": step_accuracy,
            "semantic_accuracy": semantic_accuracy,
            "hallucination_rate": hallucination_rate,
            "episode_success": episode_success,
            "episode_reward": episode_reward,
            "step_results": step_results,
            "predictions": predictions,
            "ground_truth": ground_truth[:len(predictions)]
        }
        
        # ===== Build & Save JSON payload (like earlier) =====
        meta = infer_task_from_path(episode_path)
        task_name = meta["task_name"]
        trial = meta["trial"]
        payload = {
            "task_name": task_name,
            "trial": trial,
            "goal": goal,
            "model": model_name,
            "strategy": strategy_name,
            "episode_path": episode_path,
            "created_at": iso_now(),
            "steps": len(step_records_for_json),
            # Compatible with your replay parser ("Reason:\nAction:{...}")
            "actions": actions_for_json,
            # Raw structured outputs
            "responses": responses_for_json,
            "step_records": step_records_for_json,
            # Summary metrics for convenience
            "metrics": {
                "step_accuracy": step_accuracy,
                "semantic_accuracy": semantic_accuracy,
                "hallucination_rate": hallucination_rate,
                "episode_success": episode_success,
                "episode_reward": episode_reward
            }
        }
        filename = f"{task_name}_{trial}__{model_name}__{strategy_name}.json" if trial else f"{task_name}__{model_name}__{strategy_name}.json"
        out_path = str(Path(self.out_dir) / filename)
        save_rollout_json(out_path, payload)
        # ====================================================
        
        # Print enhanced summary
        print(f"\n{'='*60}")
        print(f"EPISODE SUMMARY - {strategy_name.upper()} STRATEGY")
        print(f"{'='*60}")
        print(f"Goal: {goal}")
        print(f"Step Accuracy: {step_accuracy:.3f} ({correct_actions}/{len(step_results)})")
        print(f"Semantic Accuracy: {semantic_accuracy:.3f} ({semantic_matches}/{len(step_results)})")
        print(f"Hallucination Rate: {hallucination_rate:.3f}")
        print(f"Episode Success: {episode_success}")
        print(f"Episode Reward: {episode_reward:.1f}")
        
        self.results.append(result)
        return result
    
    def _check_exact_match(self, response_data: Dict, truth_action: str) -> bool:
        predicted_action = f"{response_data.get('action_type', '')}({response_data.get('name', '')}, index={response_data.get('index', -1)})"
        truth_normalized = truth_action.replace('"', '').replace("'", "")
        predicted_normalized = predicted_action.replace('"', '').replace("'", "")
        if predicted_normalized == truth_normalized:
            return True
        element_match = re.search(r'element_(\d+)', truth_action)
        if element_match:
            truth_index = int(element_match.group(1))
            predicted_index = response_data.get('index')
            if truth_index == predicted_index:
                truth_type = re.match(r'(\w+)\(', truth_action)
                pred_type = response_data.get('action_type', '')
                if truth_type and truth_type.group(1) == pred_type:
                    return True
        return False
    
    def _check_semantic_match(self, response_data: Dict, truth_action: str, step_elements: List[Dict]) -> bool:
        action_type = response_data.get('action_type', '')
        predicted_name = response_data.get('name', '')
        predicted_index = response_data.get('index')
        
        truth_type_match = re.match(r'(\w+)\(', truth_action)
        if not truth_type_match or truth_type_match.group(1) != action_type:
            return False
        
        if action_type == "CLICK":
            if predicted_index is not None and 0 <= predicted_index < len(step_elements):
                actual_element_at_index = step_elements[predicted_index]
                actual_name_at_index = actual_element_at_index.get('label', '')
                if predicted_name and actual_name_at_index:
                    similarity = fuzz.ratio(predicted_name.lower(), actual_name_at_index.lower())
                    if similarity >= 80:
                        return True
        return False
    
    def _check_hallucination_structured(self, response_data: Dict, step_elements: List[Dict]) -> bool:
        action_type = response_data.get('action_type', '')
        if action_type == "CLICK":
            predicted_name = response_data.get('name', '')
            predicted_index = response_data.get('index')
            available_names = [el.get('label', '') for el in step_elements]
            name_exists = any(
                fuzz.ratio(predicted_name.lower(), name.lower()) >= 75 
                for name in available_names if name
            )
            index_valid = (predicted_index is not None and 0 <= predicted_index < len(step_elements))
            return not (name_exists or index_valid)
        return False
    
    def _load_episode(self, path: str) -> Optional[Dict]:
        try:
            with gzip.open(path, "rb") as f:
                data = pickle.load(f)
            return data[0] if isinstance(data, (list, tuple)) else data
        except Exception as e:
            print(f"❌ Error loading {path}: {e}")
            return None
    
    def _extract_ui_elements_with_indices(self, episode: Dict) -> List[List[Dict[str, any]]]:
        ui_steps = episode.get("episode_data", {}).get("before_element_list", [])
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
    
    def _extract_ground_truth_actions(self, episode: Dict) -> List[str]:
        try:
            action_outputs = episode.get("episode_data", {}).get("action_output", [])
            actions = []
            for output in action_outputs:
                if isinstance(output, str):
                    json_match = re.search(r'\{[^}]*"action_type"[^}]*\}', output)
                    if json_match:
                        try:
                            action_json = json.loads(json_match.group(0))
                            simple_action = self._convert_action_to_simple(action_json)
                            if simple_action:
                                actions.append(simple_action)
                                continue
                        except json.JSONDecodeError:
                            pass
                    patterns = [
                        r'CLICK\("([^"]+)"\)',
                        r'OPEN_APP\("([^"]+)"\)',
                        r'INPUT_TEXT\("([^"]*)"\)',
                        r'SCROLL\("([^"]+)"\)',
                        r'STATUS\("([^"]+)"\)'
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, output)
                        if match:
                            action_type = pattern.split('\\(')[0]
                            target = match.group(1)
                            actions.append(f'{action_type}("{target}")')
                            break
            return actions
        except Exception as e:
            print(f"❌ Error extracting ground truth: {e}")
            return []
    
    def _convert_action_to_simple(self, action_json: Dict) -> Optional[str]:
        action_type = action_json.get("action_type", "")
        if action_type == "open_app":
            app_name = action_json.get("app_name", "Unknown")
            return f'OPEN_APP("{app_name}")'
        elif action_type == "click":
            target = action_json.get("element_text", "")
            if not target:
                index = action_json.get("index", 0)
                target = f"element_{index}"
            return f'CLICK("{target}")'
        elif action_type == "status":
            status = action_json.get("goal_status", "complete")
            return f'STATUS("{status}")'
        elif action_type == "input_text":
            text = action_json.get("text", "")
            return f'INPUT_TEXT("{text}")'
        elif action_type == "scroll":
            direction = action_json.get("direction", "down")
            return f'SCROLL("{direction}")'
        return None
    
    def run_enhanced_evaluation(self, episode_paths: List[str]) -> Dict:
        print(f"\nENHANCED ANDROID AGENT - THREE PROMPTING STRATEGIES")
        print(f"Episodes: {len(episode_paths)}")
        print(f"Strategies: Zero-shot, Few-shot, Self-reflection")
        print("=" * 100)
        
        available_models = []
        api_keys = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "mistral": "MISTRALAI_API_KEY"}
        for model_name, api_key_env in api_keys.items():
            if os.environ.get(api_key_env):
                available_models.append(model_name)
                print(f"✅ {model_name.upper()}: API key found")
            else:
                print(f"❌ {model_name.upper()}: API key missing")
        if not available_models:
            print("❌ No API keys found!")
            return {}
        
        strategy_names = list(self.prompting_strategies.keys())
        total_combinations = len(available_models) * len(strategy_names) * len(episode_paths)
        current_combination = 0
        
        print(f"Total Combinations: {len(available_models)} models × {len(strategy_names)} strategies × {len(episode_paths)} episodes = {total_combinations}")
        
        for model_name in available_models:
            for strategy_name in strategy_names:
                print(f"\nEVALUATION PHASE: {model_name.upper()} + {strategy_name.upper()}")
                print("-" * 70)
                for episode_path in episode_paths:
                    current_combination += 1
                    print(f"\n[{current_combination}/{total_combinations}] Testing combination...")
                    try:
                        self.evaluate_episode_with_rl(episode_path, model_name, strategy_name)
                        print("✅ Episode completed successfully")
                    except Exception as e:
                        print(f"❌ Episode failed: {e}")
        
        self._print_enhanced_results()
        return {"results": self.results, "memory": self.memory}
    
    def _print_enhanced_results(self):
        if not self.results:
            print("❌ No results to analyze")
            return
        print(f"\n{'='*120}")
        print("COMPREHENSIVE EVALUATION RESULTS - MODELS × STRATEGIES")
        print(f"{'='*120}")
        grouped = defaultdict(list)
        for result in self.results:
            key = f"{result['model']}_{result['strategy']}"
            grouped[key].append(result)
        print(f"\nDETAILED PERFORMANCE COMPARISON:")
        print("-" * 100)
        performance_stats = []
        for combo, results in grouped.items():
            model, strategy = combo.split('_', 1)
            avg_step_acc = np.mean([r['step_accuracy'] for r in results])
            avg_semantic_acc = np.mean([r['semantic_accuracy'] for r in results])
            avg_halluc = np.mean([r['hallucination_rate'] for r in results])
            avg_reward = np.mean([r['episode_reward'] for r in results])
            episode_success_rate = np.mean([r['episode_success'] for r in results])
            performance_stats.append({
                "model": model,
                "strategy": strategy,
                "combo": combo,
                "step_accuracy": avg_step_acc,
                "semantic_accuracy": avg_semantic_acc,
                "hallucination_rate": avg_halluc,
                "avg_reward": avg_reward,
                "episode_success_rate": episode_success_rate,
                "episodes": len(results)
            })
            print(f"\n{model.upper()} + {strategy.upper()}:")
            print(f"   Step Accuracy: {avg_step_acc:.3f}")
            print(f"   Semantic Accuracy: {avg_semantic_acc:.3f}")
            print(f"   Hallucination Rate: {avg_halluc:.3f}")
            print(f"   Episode Success Rate: {episode_success_rate:.3f}")
            print(f"   Average Reward: {avg_reward:.1f}")
            print(f"   Episodes Tested: {len(results)}")
        print(f"\nOVERALL RANKING (Best to Worst):")
        print("-" * 90)
        performance_stats.sort(
            key=lambda x: x['step_accuracy'] + x['semantic_accuracy'] - x['hallucination_rate'] + x['episode_success_rate'], 
            reverse=True
        )
        for i, stats in enumerate(performance_stats):
            composite = (stats['step_accuracy'] + stats['semantic_accuracy'] - 
                        stats['hallucination_rate'] + stats['episode_success_rate'])
            print(f"{i+1:2d}. {stats['model'].upper():8s} + {stats['strategy'].upper():15s} | "
                  f"Score: {composite:.3f} | "
                  f"Step: {stats['step_accuracy']:.3f} | "
                  f"Semantic: {stats['semantic_accuracy']:.3f} | "
                  f"Halluc: {stats['hallucination_rate']:.3f} | "
                  f"Success: {stats['episode_success_rate']:.3f}")
        # (Remaining summary sections unchanged for brevity)

def main():
    """Main execution with three prompting strategies evaluation (and JSON saving)."""
    print("ANDROID AGENT - THREE PROMPTING STRATEGIES EVALUATION")
    print("Strategies: Zero-shot | Few-shot | Self-reflection")
    print("=" * 80)
    
    api_keys = {
        "OPENAI_API_KEY": "OpenAI",
        "ANTHROPIC_API_KEY": "Anthropic", 
        "MISTRALAI_API_KEY": "Mistral AI"
    }
    available_providers = []
    missing_keys = []
    for key, provider_name in api_keys.items():
        if os.getenv(key):
            available_providers.append(provider_name)
        else:
            missing_keys.append(f"{key} (for {provider_name})")
    if missing_keys:
        print("⚠️  Missing API keys:")
        for key in missing_keys:
            print(f"   - {key}")
        if not available_providers:
            print("Please set at least one API key.")
            return
    print(f"Available providers: {', '.join(available_providers)}")
    
    # Find episodes (pick 1 per type if many exist)
    episode_patterns = [
        "runs/run_*/CameraTakePhoto_*.pkl.gz",
        "runs/run_*/ContactsAddContact_*.pkl.gz", 
        "runs/run_*/FilesMoveFile_*.pkl.gz", 
        "runs/run_*/SystemBrightnessMax_*.pkl.gz"
    ]
    episode_files = []
    for pattern in episode_patterns:
        found = glob.glob(pattern)
        if found:
            episode_files.extend(found[:1])
    if not episode_files:
        episode_files = ["runs/run_20250720T123202422603/CameraTakePhoto_0.pkl.gz"]
    print(f"\nSelected {len(episode_files)} episodes:")
    for ep in episode_files:
        print(f"  - {os.path.basename(ep)}")
    print(f"\nTesting Matrix:")
    n_models = len([p for p in ['openai', 'anthropic', 'mistral'] if os.getenv({'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY', 'mistral': 'MISTRALAI_API_KEY'}[p])])
    print(f"  Models: {n_models}")
    print(f"  Strategies: 3 (zero-shot, few-shot, self-reflection)")
    print(f"  Episodes: {len(episode_files)}")
    print(f"  Total tests: {n_models * 3 * len(episode_files)}")
    
    evaluator = RLEnhancedEvaluator(out_dir="runs/llm_results2")
    evaluator.run_enhanced_evaluation(episode_files)

if __name__ == "__main__":
    main()
