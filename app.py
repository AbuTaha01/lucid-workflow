"""
app.py — Lucid Corp AI Workflow Server
=======================================
Run with:
    python app.py

Then open: http://localhost:5000
For public sharing: run ngrok http 5000
"""

import os
import json
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
import requests

try:
    from agents import AGENTS
    print("  agents import OK")
except Exception as e:
    print(f"  agents import FAILED: {e}")

try:
    from actions.pdf_generator import generate_quote_pdf, generate_sustainability_pdf
    print("  pdf_generator import OK")
except Exception as e:
    print(f"  pdf_generator import FAILED: {e}")

try:
    from actions.sheets_logger import SheetsLogger
    print("  sheets_logger import OK")
except Exception as e:
    print(f"  sheets_logger import FAILED: {e}")

app = Flask(__name__)
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
print(f"  API KEY STATUS: {'SET (' + str(len(API_KEY)) + ' chars)' if API_KEY else 'NOT SET - MISSING'}")

# Store active workflow results in memory
workflow_store = {}


def call_claude(system_prompt: str, user_message: str) -> str:
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }
    print(f"  Calling Claude API... model: {payload['model']}")
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers, json=payload, timeout=60,
    )
    print(f"  Response status: {resp.status_code}")
    print(f"  Response body: {resp.text[:300]}")
    resp.raise_for_status()
    data = resp.json()
    return "".join(b.get("text", "") for b in data["content"])


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run_workflow():
    """Start the workflow in a background thread, return a run_id."""
    data  = request.get_json()
    brief = data.get("brief", "").strip()
    if not brief:
        return jsonify({"error": "No brief provided"}), 400
    if not API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not set on server"}), 500

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id    = timestamp

    workflow_store[run_id] = {
        "status":    "running",
        "brief":     brief,
        "timestamp": timestamp,
        "agents":    {},
        "files":     {},
        "sheets_url": None,
        "error":     None,
    }

    thread = threading.Thread(
        target=_run_workflow_thread,
        args=(run_id, brief, timestamp),
        daemon=True,
    )
    thread.start()
    return jsonify({"run_id": run_id})


@app.route("/status/<run_id>")
def get_status(run_id):
    """Poll this endpoint to get live workflow progress."""
    store = workflow_store.get(run_id)
    if not store:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(store)


@app.route("/download/<run_id>/<file_type>")
def download_file(run_id, file_type):
    """Download a generated file."""
    store = workflow_store.get(run_id)
    if not store:
        return jsonify({"error": "Run not found"}), 404

    path = store["files"].get(file_type)
    if not path or not Path(path).exists():
        return jsonify({"error": "File not ready"}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name=Path(path).name,
    )


def _run_workflow_thread(run_id: str, brief: str, timestamp: str):
    """Background thread that runs all agents sequentially."""
    store   = workflow_store[run_id]
    results = {}
    context = f"CLIENT INQUIRY / ORDER BRIEF:\n{brief}"
    sheets  = SheetsLogger()

    try:
        for agent in AGENTS:
            # Mark agent as running
            store["agents"][agent["id"]] = {
                "status": "running",
                "output": None,
                "elapsed": None,
            }

            # Coordinator agent gets ALL previous outputs as full context
            if agent["id"] == "coordinator":
                context  = f"ORIGINAL CLIENT BRIEF:\n{brief}\n\n"
                context += "FULL PIPELINE OUTPUTS:\n" + "="*60 + "\n"
                for prev in AGENTS[:-1]:
                    prev_out = results.get(prev["id"], "")
                    if prev_out:
                        context += f"\n{prev['name'].upper()} OUTPUT:\n{prev_out}\n\n"
                context += "="*60
                context += "\n\nYour task: produce the full governance and coordination report."

            t0     = datetime.now()
            output = call_claude(agent["system_prompt"], context)
            elapsed = (datetime.now() - t0).total_seconds()

            results[agent["id"]] = output
            store["agents"][agent["id"]] = {
                "status":  "done",
                "output":  output,
                "elapsed": round(elapsed, 1),
            }

            # Update context for next agent (standard chain handoff)
            if agent["id"] != "coordinator":
                context = (
                    f"ORIGINAL CLIENT BRIEF:\n{brief}\n\n"
                    f"{agent['name'].upper()} OUTPUT:\n{output}"
                )

            # ── Actions after each agent ──────────────────────────────────
            if agent["id"] == "finance":
                # Generate quote PDF
                quote_path = OUTPUT_DIR / f"lucid_quote_{timestamp}.pdf"
                generate_quote_pdf(
                    brief=brief,
                    sales_output=results.get("sales", ""),
                    design_output=results.get("design", ""),
                    finance_output=output,
                    output_path=quote_path,
                )
                store["files"]["quote"] = str(quote_path)

            if agent["id"] == "sustainability":
                # Generate sustainability PDF
                sustain_path = OUTPUT_DIR / f"lucid_sustainability_{timestamp}.pdf"
                generate_sustainability_pdf(
                    brief=brief,
                    sustainability_output=output,
                    output_path=sustain_path,
                )
                store["files"]["sustainability"] = str(sustain_path)

            if agent["id"] == "operations":
                # Log full order to Google Sheets
                sheets_url = sheets.log_order(
                    brief=brief,
                    timestamp=timestamp,
                    results=results,
                )
                store["sheets_url"] = sheets_url

        store["status"] = "complete"

    except Exception as e:
        store["status"] = "error"
        store["error"]  = str(e)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("\n  🌿 Lucid Corp AI Workflow Server")
    print(f"  Running on port {port}")
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
