# Lucid Corp — AI Workflow Web App
### Flask server with live agent output, PDF generation & Google Sheets logging

---

## What the manager sees

1. Opens your URL in any browser
2. Picks a scenario or types a custom order brief
3. Clicks **Run Workflow**
4. Watches 5 AI agents process the order live
5. Gets **Download Quote PDF** and **Download Sustainability PDF** buttons
6. Sees order automatically logged to a shared Google Sheet

---

## Quick start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your Anthropic API key
```bash
# Mac / Linux
export ANTHROPIC_API_KEY="sk-ant-..."

# Windows
set ANTHROPIC_API_KEY=sk-ant-...
```
Get your key at: https://console.anthropic.com

### 3. Run the server
```bash
python app.py
```
Open http://localhost:5000 — the app is running.

### 4. Share with the manager (via ngrok)
```bash
# Install ngrok from https://ngrok.com (free)
ngrok http 5000
```
Copy the URL it gives you (e.g. https://abc123.ngrok.io) and send it.

---

## Google Sheets setup (optional but impressive)

Without this, the app still works — it just shows "simulation mode" for the Sheets step.

### Step 1 — Create a Google Cloud project
1. Go to https://console.cloud.google.com
2. Create a new project (e.g. "Lucid Workflow")
3. Go to **APIs & Services** → **Enable APIs**
4. Enable **Google Sheets API** and **Google Drive API**

### Step 2 — Create a service account
1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **Service Account**
3. Give it a name (e.g. "lucid-workflow-bot")
4. Click Done, then click the service account you just created
5. Go to **Keys** tab → **Add Key** → **JSON**
6. Download the JSON file — rename it to `credentials.json`
7. Put `credentials.json` in the same folder as `app.py`

### Step 3 — Create and share the Google Sheet
1. Go to https://sheets.google.com
2. Create a new spreadsheet — name it "Lucid Corp Orders"
3. Copy the Sheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/edit`
4. Click **Share** → paste the service account email from credentials.json
5. Give it **Editor** access

### Step 4 — Set the Sheet ID
```bash
export GOOGLE_SHEET_ID="your_sheet_id_here"
```

Now every workflow run writes a real row to the sheet — the manager can
have it open and watch the order appear live.

---

## Deploy to Railway (permanent public URL)

Instead of ngrok (which needs your laptop on), deploy to Railway for a
permanent URL you can send anyone.

```bash
# Install Railway CLI
npm install -g @railway/cli

# From the lucid_flask folder:
railway login
railway init
railway up
```

Set environment variables in the Railway dashboard:
- `ANTHROPIC_API_KEY` = your key
- `GOOGLE_SHEET_ID`   = your sheet ID
- Upload `credentials.json` as a file or set contents as env var

---

## Project structure

```
lucid_flask/
├── app.py                  ← Flask server, run this
├── agents.py               ← 5 agent definitions + system prompts
├── requirements.txt
├── README.md
├── credentials.json        ← Google service account (you add this)
│
├── actions/
│   ├── pdf_generator.py    ← Quote + sustainability PDFs
│   └── sheets_logger.py    ← Google Sheets logging
│
├── templates/
│   └── index.html          ← The UI the manager sees
│
└── output/                 ← Generated PDFs saved here
    └── lucid_quote_*.pdf
    └── lucid_sustainability_*.pdf
```

---

*Built with Anthropic Claude API · lucidcorp.com*
