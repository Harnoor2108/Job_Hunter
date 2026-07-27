"""
send_email.py

Reads outputs/scored_<config_name>.json. If it contains at least one job,
sends a summary email (top matches + a link to the full Sheet). Sends
nothing if the file is empty, so you don't get emailed on days with zero
matches.

Usage:
    python scripts/send_email.py configs/harnoor.json

Requires env vars:
    EMAIL_ADDRESS      - sender Gmail address
    EMAIL_APP_PASSWORD - Gmail App Password (not your regular password —
                          generate one at https://myaccount.google.com/apppasswords)
    EMAIL_TO           - recipient address(es). Comma-separated for multiple,
                          e.g. "first@gmail.com, second@gmail.com"
    SHEET_ID           - used to link back to the full sheet
"""

import json
import os
import smtplib
import sys
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
TOP_N_IN_EMAIL = 10


def load_scored_jobs(config_name: str) -> list:
    path = f"outputs/scored_{config_name}.json"
    if not Path(path).exists():
        raise FileNotFoundError(f"{path} not found — run score_jobs.py first.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_email_body(jobs: list, sheet_url: str) -> str:
    lines = [
        f"{len(jobs)} new job match(es) found today.",
        f"Full ranked list: {sheet_url}",
        "",
        f"Top {min(TOP_N_IN_EMAIL, len(jobs))} matches:",
        "",
    ]
    for job in jobs[:TOP_N_IN_EMAIL]:
        lines.append(f"{job['job_title']} — {job['company']} ({job['location']})")
        lines.append(f"{job['apply_link']}")
        lines.append("")
    return "\n".join(lines)


def send_email(subject: str, body: str):
    sender = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("EMAIL_APP_PASSWORD")
    recipient = os.environ.get("EMAIL_TO")

    missing = [name for name, val in [
        ("EMAIL_ADDRESS", sender),
        ("EMAIL_APP_PASSWORD", password),
        ("EMAIL_TO", recipient),
    ] if not val]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    recipients = [r.strip() for r in recipient.split(",")]

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/send_email.py configs/<name>.json")
        sys.exit(1)

    config_path = sys.argv[1]
    config_name = Path(config_path).stem

    jobs = load_scored_jobs(config_name)

    if not jobs:
        print("No scored jobs found today — skipping email.")
        return

    sheet_id = os.environ.get("SHEET_ID", "")
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

    subject = f"Job Hunter: {len(jobs)} match(es) for {date.today().isoformat()}"
    body = build_email_body(jobs, sheet_url)

    send_email(subject, body)
    print(f"Email sent: {len(jobs)} job(s) reported.")


if __name__ == "__main__":
    main()