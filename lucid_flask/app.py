import os
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
import requests

from agents import AGENTS
from actions.pdf_generator import generate_quote_pdf, generate_sustainability_pdf
from actions.sheets_logger import SheetsLogger

app        = Flask(__name__)
OUTPUT_DIR = Path("/tmp/output")
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

API_KEY        = os.environ.get("ANTHROPIC_API_KEY", "")
workflow_store = {}

print(f"STARTUP: API key {'SET (' + str(len(API_KEY)) + ' chars)' if API_KEY else 'MISSING'}")


def call_claude(system_prompt, user_message):
    print(f"[API] Calling Claude...")
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":         API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json={
            "model":    "claude-3-5-sonnet-20241022",
            "max_tokens": 1000,
            "system":   system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        },
        timeout=120,
    )
    print(f"[API] Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"[API] Error: {resp.text[:400]}")
    resp.raise_for_status()
    return "".join(b.get("text", "") for b in resp.json()["content"])


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run_workflow():
    data  = request.get_json()
    brief = (data or {}).get("brief", "").strip()
    if not brief:
        return jsonify({"error": "No brief provided"}), 400
    if not API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not set"}), 500

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    workflow_store[timestamp] = {
        "status": "running", "brief": brief,
        "timestamp": timestamp, "agents": {},
        "files": {}, "sheets_url": None, "error": None,
    }
    threading.Thread(
        target=_run_thread, args=(timestamp, brief, timestamp), daemon=True
    ).start()
    return jsonify({"run_id": timestamp})


@app.route("/status/<run_id>")
def get_status(run_id):
    store = workflow_store.get(run_id)
    if not store:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(store)


@app.route("/download/<run_id>/<file_type>")
def download_file(run_id, file_type):
    store = workflow_store.get(run_id)
    if not store:
        return jsonify({"error": "Run not found"}), 404
    path = store["files"].get(file_type)
    if not path or not Path(path).exists():
        return jsonify({"error": "File not ready"}), 404
    return send_file(path, as_attachment=True, download_name=Path(path).name)


def _run_thread(run_id, brief, timestamp):
    store   = workflow_store[run_id]
    results = {}
    context = f"CLIENT INQUIRY / ORDER BRIEF:\n{brief}"

    try:
        sheets = SheetsLogger()
    except Exception as e:
        print(f"[SHEETS] init error: {e}")
        sheets = None

    for agent in AGENTS:
        aid = agent["id"]
        print(f"[AGENT] Starting: {agent['name']}")
        store["agents"][aid] = {"status": "running", "output": None, "elapsed": None}

        if aid == "coordinator":
            context  = f"ORIGINAL CLIENT BRIEF:\n{brief}\n\n"
            context += "FULL PIPELINE OUTPUTS:\n" + "="*60 + "\n"
            for prev in AGENTS[:-1]:
                out = results.get(prev["id"], "")
                if out:
                    context += f"\n{prev['name'].upper()} OUTPUT:\n{out}\n\n"
            context += "="*60 + "\n\nProduce the full governance and coordination report."

        try:
            t0      = datetime.now()
            output  = call_claude(agent["system_prompt"], context)
            elapsed = round((datetime.now() - t0).total_seconds(), 1)
            results[aid] = output
            store["agents"][aid] = {"status": "done", "output": output, "elapsed": elapsed}
            print(f"[AGENT] Done: {agent['name']} ({elapsed}s)")

            if aid != "coordinator":
                context = f"ORIGINAL CLIENT BRIEF:\n{brief}\n\n{agent['name'].upper()} OUTPUT:\n{output}"

            if aid == "finance":
                try:
                    p = OUTPUT_DIR / f"lucid_quote_{timestamp}.pdf"
                    generate_quote_pdf(brief=brief, sales_output=results.get("sales",""),
                        design_output=results.get("design",""), finance_output=output, output_path=p)
                    store["files"]["quote"] = str(p)
                    print(f"[PDF] Quote saved: {p}")
                except Exception as e:
                    print(f"[PDF] Quote failed: {e}")

            if aid == "sustainability":
                try:
                    p = OUTPUT_DIR / f"lucid_sustainability_{timestamp}.pdf"
                    generate_sustainability_pdf(brief=brief, sustainability_output=output, output_path=p)
                    store["files"]["sustainability"] = str(p)
                    print(f"[PDF] Sustainability saved: {p}")
                except Exception as e:
                    print(f"[PDF] Sustainability failed: {e}")

            if aid == "operations" and sheets:
                try:
                    url = sheets.log_order(brief=brief, timestamp=timestamp, results=results)
                    store["sheets_url"] = url
                except Exception as e:
                    print(f"[SHEETS] Log failed: {e}")

        except Exception as e:
            import traceback
            err = f"{type(e).__name__}: {e}"
            print(f"[AGENT] FAILED: {agent['name']} — {err}")
            print(traceback.format_exc())
            store["agents"][aid] = {"status": "done", "output": f"Error: {err}", "elapsed": 0}
            store["status"] = "error"
            store["error"]  = err
            return

    store["status"] = "complete"
    print(f"[WORKFLOW] Complete: {run_id}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🌿 Lucid Corp Workflow — port {port}")
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
