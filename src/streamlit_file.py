import streamlit as st
import json
import pandas as pd
import plotly.express as px
import os


# --- Load JSON ---
JSON_PATH = "evaluation_output/comprehensive_benchmark_20250731_221427.json"

st.write("Looking for JSON at:", JSON_PATH)
st.write("Exists:", os.path.exists(JSON_PATH))


if not os.path.exists(JSON_PATH):
    st.error(f"JSON file not found at {JSON_PATH}")
    st.stop()

with open(JSON_PATH, "r") as f:
    report = json.load(f)

# --- Sidebar filters ---
st.sidebar.title("Filters")
models = sorted({r["model"] for r in report["raw_results"]})
variants = sorted({r["variant"] for r in report["raw_results"]})
temps = sorted({r.get("temperature_variant", f"T={r.get('temperature', 0.0):.1f}") for r in report["raw_results"]})

selected_models = st.sidebar.multiselect("Model", models, default=models)
selected_variants = st.sidebar.multiselect("Prompt Strategy", variants, default=variants)
selected_temps = st.sidebar.multiselect("Temperature Variant", temps, default=temps)

# --- Summary metrics ---
st.title("Android Agent Benchmark Dashboard")
st.subheader("Overall Metrics")
overall = report["overall_metrics"]
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Step Accuracy", f"{overall['average_step_accuracy']:.3f}")
col2.metric("Name-Index Accuracy", f"{overall['average_name_index_accuracy']:.3f}")
col3.metric("Episode Success Rate", f"{overall['episode_success_rate']:.3f}")
col4.metric("Hallucination Rate", f"{overall['hallucination_rate']:.3f}")
col5.metric("Avg Reward", f"{overall['average_reward']:.1f}")

# --- Convert raw results to DataFrame ---
df = pd.json_normalize(report["raw_results"])

# Normalize temperature variant field for consistency
df["temperature_variant"] = df.apply(
    lambda r: r.get("temperature_variant", f"T={r.get('temperature', 0.0):.1f}"), axis=1
)

# Apply filters
filtered = df[
    df["model"].isin(selected_models) &
    df["variant"].isin(selected_variants) &
    df["temperature_variant"].isin(selected_temps)
]

st.markdown(f"**Showing {len(filtered)} episode variants (filtered)**")

# --- Model comparison plot ---
st.subheader("Model Comparison")
model_perf = filtered.groupby("model").agg(
    step_accuracy=("step_accuracy", "mean"),
    name_index_accuracy=("name_index_accuracy", "mean"),
    episode_success=("episode_success", "mean"),
    hallucination_rate=("hallucination_rate", "mean"),
    average_reward=("episode_reward", "mean"),
    count=("episode", "count")
).reset_index()

fig_models = px.bar(
    model_perf.melt(id_vars="model", value_vars=["step_accuracy", "name_index_accuracy"]),
    x="model", y="value", color="variable",
    barmode="group",
    labels={"value": "Accuracy", "variable": "Metric"},
    title="Step vs Name-Index Accuracy by Model"
)
st.plotly_chart(fig_models, use_container_width=True)

# --- Strategy comparison ---
st.subheader("Prompt Strategy Comparison")
strategy_perf = filtered.groupby("variant").agg(
    step_accuracy=("step_accuracy", "mean"),
    name_index_accuracy=("name_index_accuracy", "mean"),
    success_rate=("episode_success", "mean")
).reset_index()

fig_strat = px.bar(
    strategy_perf.melt(id_vars="variant", value_vars=["step_accuracy", "name_index_accuracy"]),
    x="variant", y="value", color="variable",
    barmode="group",
    labels={"value": "Accuracy", "variable": "Metric"},
    title="Accuracy by Prompt Strategy"
)
st.plotly_chart(fig_strat, use_container_width=True)

# --- Temperature variant comparison ---
st.subheader("Temperature Variant Comparison")
temp_perf = filtered.groupby("temperature_variant").agg(
    step_accuracy=("step_accuracy", "mean"),
    name_index_accuracy=("name_index_accuracy", "mean"),
    success_rate=("episode_success", "mean")
).reset_index()

fig_temp = px.bar(
    temp_perf.melt(id_vars="temperature_variant", value_vars=["step_accuracy", "name_index_accuracy"]),
    x="temperature_variant", y="value", color="variable",
    barmode="group",
    labels={"value": "Accuracy", "variable": "Metric"},
    title="Accuracy by Temperature Variant"
)
st.plotly_chart(fig_temp, use_container_width=True)

# --- Detailed episode table ---
st.subheader("Episode-Level Details")
display_cols = [
    "episode", "model", "variant", "temperature_variant", "goal",
    "step_accuracy", "name_index_accuracy", "episode_success", "hallucination_rate", "episode_reward"
]
st.dataframe(filtered[display_cols].sort_values(by="step_accuracy", ascending=False), use_container_width=True)

# --- Download filtered results ---
st.subheader("Download")
csv = filtered[display_cols].to_csv(index=False)
st.download_button("Download Filtered CSV", csv, "filtered_benchmark.csv", "text/csv")
st.download_button("Download Full JSON Report", json.dumps(report, indent=2), "full_report.json", "application/json")
