"""
actions/sheets_logger.py
=========================
Logs completed orders to a Google Sheet.

Each workflow run adds one row with:
  - Timestamp, Client Name, Priority, Volume, Budget
  - Feasibility, Approval Status, Margin
  - Pad diversion count
  - Production timeline
  - Links to PDFs (if hosted)

SETUP (one time):
  1. Go to console.cloud.google.com
  2. Create a project → Enable "Google Sheets API"
  3. Create a Service Account → Download JSON credentials
  4. Save as: credentials.json in this folder
  5. Create a Google Sheet → Share it with the service account email
  6. Copy the Sheet ID from the URL and set GOOGLE_SHEET_ID in .env

If credentials.json is missing, the logger runs in SIMULATION mode
and prints what it would have written instead.
"""

import os
import re
import json
from datetime import datetime
from pathlib import Path

CREDENTIALS_FILE = Path("credentials.json")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
SHEET_NAME = "Orders"


class SheetsLogger:
    """
    Logs order data to Google Sheets.
    Falls back to simulation mode if credentials are not configured.
    """

    def __init__(self):
        self.client   = None
        self.sheet    = None
        self.simulated = True
        self._try_connect()

    def _try_connect(self):
        """Attempt to connect to Google Sheets API."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            if not CREDENTIALS_FILE.exists():
                print("  [SHEETS] credentials.json not found — running in simulation mode")
                return
            if not SHEET_ID:
                print("  [SHEETS] GOOGLE_SHEET_ID not set — running in simulation mode")
                return

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds        = Credentials.from_service_account_file(
                str(CREDENTIALS_FILE), scopes=scopes
            )
            self.client   = gspread.authorize(creds)
            spreadsheet   = self.client.open_by_key(SHEET_ID)

            # Get or create the Orders sheet/tab
            try:
                self.sheet = spreadsheet.worksheet(SHEET_NAME)
            except Exception:
                self.sheet = spreadsheet.add_worksheet(
                    title=SHEET_NAME, rows=1000, cols=20
                )
                self._write_headers()

            self.simulated = False
            print("  [SHEETS] Connected to Google Sheets ✓")

        except ImportError:
            print("  [SHEETS] gspread not installed — simulation mode")
        except Exception as e:
            print(f"  [SHEETS] Connection failed ({e}) — simulation mode")

    def _write_headers(self):
        """Write column headers to a fresh sheet."""
        headers = [
            "Timestamp", "Run ID", "Client Name", "Location",
            "Priority", "Product Type", "Volume (units)", "Budget (CAD)",
            "Feasibility", "Finance Approval", "Margin Estimate",
            "Pads Diverted", "Timeline (weeks)", "Certifications",
            "Production Schedule Summary", "Status",
        ]
        self.sheet.insert_row(headers, index=1)
        # Bold the header row
        self.sheet.format("A1:P1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.18, "green": 0.48, "blue": 0.23},
        })

    def log_order(self, brief: str, timestamp: str, results: dict) -> str:
        """
        Parse agent outputs and write a row to Google Sheets.
        Returns the sheet URL (or a simulated URL).
        """
        row = self._build_row(brief, timestamp, results)

        if self.simulated:
            self._simulate_log(row)
            return f"https://docs.google.com/spreadsheets/d/SIMULATED/edit"

        try:
            self.sheet.append_row(list(row.values()))
            url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
            print(f"  [SHEETS] Row written → {url}")
            return url
        except Exception as e:
            print(f"  [SHEETS] Write failed: {e}")
            return ""

    def _build_row(self, brief: str, timestamp: str, results: dict) -> dict:
        """Extract structured data from agent outputs for the sheet row."""
        sales_out   = results.get("sales", "")
        design_out  = results.get("design", "")
        finance_out = results.get("finance", "")
        sustain_out = results.get("sustainability", "")
        ops_out     = results.get("operations", "")

        # Format timestamp nicely
        try:
            dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
            ts = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            ts = timestamp

        return {
            "Timestamp":              ts,
            "Run ID":                 f"LC-{timestamp}",
            "Client Name":            _extract(brief, r"client[:\s]+([A-Z][^\.]{3,40}?)(?:\s*[\(,\.])", "Unknown"),
            "Location":               _extract(brief, r"\(([^)]+(?:BC|ON|AB|QC|MB|SK|NS|NB|CA|USA)[^)]*)\)", ""),
            "Priority":               _extract_priority(sales_out),
            "Product Type":           _extract(brief, r"(rPET|PET|ocean.bound|Lucid Infinity|protein tray|produce tray)", "rPET Tray"),
            "Volume (units)":         _extract(brief, r"([\d,]+)\s*units", ""),
            "Budget (CAD)":           _extract(brief, r"\$?([\d,]+(?:\s*CAD)?)", ""),
            "Feasibility":            _extract(design_out, r"Feasibility[:\s]+([^\n]{5,60})", "See report"),
            "Finance Approval":       _extract_approval(finance_out),
            "Margin Estimate":        _extract(finance_out, r"(\d+[–\-]\d+%|\d+%)", ""),
            "Pads Diverted":          _extract(sustain_out, r"([\d,]+)\s*(?:pads|soaker pads)", ""),
            "Timeline (weeks)":       _extract(brief, r"(\d+)\s*weeks?", ""),
            "Certifications":         _extract_certs(sustain_out),
            "Production Summary":     _first_line(ops_out),
            "Status":                 "ORDER ACCEPTED",
        }

    def _simulate_log(self, row: dict):
        """Print what would have been written to the sheet."""
        print("  [SHEETS] Simulated row:")
        for k, v in row.items():
            if v:
                print(f"           {k:<28} {v}")


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _extract(text: str, pattern: str, default: str = "") -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else default


def _extract_priority(text: str) -> str:
    upper = text.upper()
    for p in ("HIGH", "MEDIUM", "LOW"):
        if p in upper:
            return p
    return "MEDIUM"


def _extract_approval(text: str) -> str:
    upper = text.upper()
    if "APPROVED" in upper and "CONDITIONAL" not in upper:
        return "APPROVED"
    if "CONDITIONAL" in upper:
        return "CONDITIONAL"
    if "DECLINED" in upper:
        return "DECLINED"
    return "PENDING"


def _extract_certs(text: str) -> str:
    certs = []
    if re.search(r"rinse.{0,10}recycle", text, re.IGNORECASE):
        certs.append("Rinse & Recycle")
    if re.search(r"ocean.bound", text, re.IGNORECASE):
        certs.append("Ocean-Bound")
    if re.search(r"EU|european", text, re.IGNORECASE):
        certs.append("EU Packaging")
    return ", ".join(certs) if certs else "rPET Recyclable"


def _first_line(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith(("→", "✓")):
            return s[:100]
    return ""
