"""
push_to_sheets.py

Reads outputs/scored_<config_name>.json and upserts rows into today's tab
of the target Google Sheet, keyed by apply_link. Header row is bold, frozen,
filtered, and sorted by Match Score descending.

Usage:
    python scripts/push_to_sheets.py configs/harnoor.json

Requires:
    GOOGLE_APPLICATION_CREDENTIALS env var pointing to a service-account
    JSON key file, and SHEET_ID env var with the target sheet's ID.
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

COLUMNS = [
    "match_score", "source", "job_title", "company", "location",
    "experience_required", "seniority", "employment_type", "skills_matched",
    "posted", "applicants", "job_description", "apply_link", "fetched_at",
]

HEADER = [
    "Match Score", "Source", "Job Title", "Company", "Location",
    "Experience Required", "Seniority", "Employment Type", "Skills Matched",
    "Posted", "Applicants", "Job Description", "Apply Link", "Fetched At",
]


def load_scored_jobs(config_name: str) -> list:
    path = f"outputs/scored_{config_name}.json"
    if not Path(path).exists():
        raise FileNotFoundError(f"{path} not found — run score_jobs.py first.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_client() -> gspread.Client:
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not Path(creds_path).exists():
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS not set or file missing.")
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return gspread.authorize(creds)


def get_or_create_tab(spreadsheet, tab_name: str):
    try:
        return spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(HEADER))
        ws.append_row(HEADER)
        ws.format("A1:N1", {"textFormat": {"bold": True}})
        ws.freeze(rows=1)
        return ws


def upsert_rows(ws, new_rows: list[dict]):
    existing = ws.get_all_records()
    existing_header = ws.row_values(1)

    if existing_header != HEADER:
        # Schema drift — wipe and rewrite clean rather than half-stitching.
        ws.clear()
        ws.append_row(HEADER)
        ws.format("A1:N1", {"textFormat": {"bold": True}})
        ws.freeze(rows=1)
        existing = []

    by_apply_link = {row.get("Apply Link"): i + 2 for i, row in enumerate(existing)}

    for job in new_rows:
        row_values = [job[col] for col in COLUMNS]
        apply_link = job["apply_link"]
        if apply_link in by_apply_link:
            row_num = by_apply_link[apply_link]
            ws.update(f"A{row_num}:N{row_num}", [row_values])
        else:
            ws.append_row(row_values)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/push_to_sheets.py configs/<name>.json")
        sys.exit(1)

    config_path = sys.argv[1]
    config_name = Path(config_path).stem

    scored_jobs = load_scored_jobs(config_name)
    print(f"Pushing {len(scored_jobs)} scored postings to Google Sheets...")

    sheet_id = os.environ.get("SHEET_ID")
    if not sheet_id:
        raise RuntimeError("SHEET_ID is not set. Check your .env or repo secrets.")

    client = get_client()
    spreadsheet = client.open_by_key(sheet_id)

    tab_name = date.today().isoformat()
    ws = get_or_create_tab(spreadsheet, tab_name)
    upsert_rows(ws, scored_jobs)

    # Re-sort by Match Score descending after upserts.
    ws.sort((1, "des"), range=f"A2:N{ws.row_count}")

    print(f"Done. View at: https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={ws.id}")


if __name__ == "__main__":
    main()
