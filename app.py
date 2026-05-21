import os
import sys
import traceback
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
import requests

# ── Imports with error catching ───────────────────────────────────────────────
try:
    from agents import AGENTS
except Exception as e:
    print(f"FATAL: could not import agents: {e}")
    sys.exit(1)

try:
    from actions.pdf_generator import generate_quote_pdf, generate_sustainability_pdf
except Exception as e:
    print(f"FATAL: could not import pdf_generator: {e}")
    sys.exit(1)

try:
    from actions.sheets_logger import SheetsLogger
except Exception as e:
    print(f"FATAL: could not import sheets_logger: {e}")
    sys.exit(1)

# ── App setup ─────────────────────────────────────────────────────────────────
app        = Flask(__name__)
OUTPUT_DIR = Path("/tmp/output")
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
print(f"  API KEY: {'SET (' + str(len(API_KEY)) + ' chars)' if API_KEY else 'MISSING'}")

workflow_store = {}


# ── Claude API call ───────────────────────────────────────────────────────────
def call_claude(system_prompt: str, user_message: str) -> str:
    headers = {
        "x-api-key":         API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    payload = {
        "model":      "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "system":     system_prompt,
        "messages":   [{"role": "user", "content": user_message}],
    }
    print(f"  [API] POST /v1/messages — agent context length: {len(user_message)}")
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=headers,
        json=payload,
        timeout=120,
    )
    print(f"  [API] Response: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  [API] Error body: {resp.text[:500]}")
        resp.raise_for_status()
    data = resp.json()
    return "".join(b.get("text", "") for b in data["content"])


# ── Routes ────────────────────────────────────────────────────────────────────
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
        return jsonify({"error": "ANTHROPIC_API_KEY not set on server"}), 500

    # Test Claude API directly before starting thread
    try:
        print("  [TEST] Testing Claude API call directly...")
        test_result = call_claude("You are a test.", "Say OK")
        print(f"  [TEST] Claude API works: {test_result[:50]}")
    except Exception as e:
        print(f"  [TEST] Claude API failed: {e}")
        return jsonify({"error": f"Claude API error: {e}"}), 500

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id    = timestamp

    workflow_store[run_id] = {
        "status":     "running",
        "brief":      brief,
        "timestamp":  timestamp,
        "agents":     {},
        "files":      {},
        "sheets_url": None,
        "error":      None,
    }

    t = threading.Thread(
        target=_run_thread,
        args=(run_id, brief, timestamp),
        daemon=True,
    )
    t.start()
    return jsonify({"run_id": run_id})


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


# ── Workflow thread ───────────────────────────────────────────────────────────
def _run_thread(run_id: str, brief: str, timestamp: str):
    store   = workflow_store[run_id]
    results = {}
    context = f"CLIENT INQUIRY / ORDER BRIEF:\n{brief}"

    try:
        sheets = SheetsLogger()
    except Exception as e:
        print(f"  [SHEETS] init failed: {e}")
        sheets = None

    for agent in AGENTS:
        agent_id = agent["id"]
        print(f"  [AGENT] Starting: {agent['name']}")

        store["agents"][agent_id] = {
            "status":  "running",
            "output":  None,
            "elapsed": None,
        }

        # Coordinator sees all previous outputs
        if agent_id == "coordinator":
            context  = f"ORIGINAL CLIENT BRIEF:\n{brief}\n\n"
            context += "FULL PIPELINE OUTPUTS:\n" + "=" * 60 + "\n"
            for prev in AGENTS[:-1]:
                prev_out = results.get(prev["id"], "")
                if prev_out:
                    context += f"\n{prev['name'].upper()} OUTPUT:\n{prev_out}\n\n"
            context += "=" * 60
            context += "\n\nProduce the full governance and coordination report."

        try:
            t0      = datetime.now()
            output  = call_claude(agent["system_prompt"], context)
            elapsed = round((datetime.now() - t0).total_seconds(), 1)

            results[agent_id] = output
            store["agents"][agent_id] = {
                "status":  "done",
                "output":  output,
                "elapsed": elapsed,
            }
            print(f"  [AGENT] Done: {agent['name']} ({elapsed}s)")

            # Chain context to next agent
            if agent_id != "coordinator":
                context = (
                    f"ORIGINAL CLIENT BRIEF:\n{brief}\n\n"
                    f"{agent['name'].upper()} OUTPUT:\n{output}"
                )

            # ── Post-agent actions ─────────────────────────────────────────
            if agent_id == "finance":
                try:
                    qp = OUTPUT_DIR / f"lucid_quote_{timestamp}.pdf"
                    generate_quote_pdf(
                        brief=brief,
                        sales_output=results.get("sales", ""),
                        design_output=results.get("design", ""),
                        finance_output=output,
                        output_path=qp,
                    )
                    store["files"]["quote"] = str(qp)
                    print(f"  [PDF] Quote generated: {qp}")
                except Exception as e:
                    print(f"  [PDF] Quote failed: {e}\n{traceback.format_exc()}")

            if agent_id == "sustainability":
                try:
                    sp = OUTPUT_DIR / f"lucid_sustainability_{timestamp}.pdf"
                    generate_sustainability_pdf(
                        brief=brief,
                        sustainability_output=output,
                        output_path=sp,
                    )
                    store["files"]["sustainability"] = str(sp)
                    print(f"  [PDF] Sustainability sheet generated: {sp}")
                except Exception as e:
                    print(f"  [PDF] Sustainability failed: {e}\n{traceback.format_exc()}")

            if agent_id == "operations" and sheets:
                try:
                    url = sheets.log_order(
                        brief=brief,
                        timestamp=timestamp,
                        results=results,
                    )
                    store["sheets_url"] = url
                    print(f"  [SHEETS] Logged: {url}")
                except Exception as e:
                    print(f"  [SHEETS] Log failed: {e}")

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print(f"  [AGENT] FAILED: {agent['name']} — {err}")
            print(traceback.format_exc())
            store["agents"][agent_id] = {
                "status":  "done",
                "output":  f"Agent error: {err}",
                "elapsed": 0,
            }
            store["status"] = "error"
            store["error"]  = err
            return

    store["status"] = "complete"
    print(f"  [WORKFLOW] Complete — run_id: {run_id}")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"LUCID STARTUP v3: port={port} key={'SET' if API_KEY else 'MISSING'}")
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
