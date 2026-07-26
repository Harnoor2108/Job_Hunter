"""
score_jobs.py

Reads outputs/raw_<config_name>.json, scores each posting 0-100 against the
config's weighted skills and title-match rules, drops anything below
min_match_score, and writes outputs/scored_<config_name>.json ranked
descending by score.

Usage:
    python scripts/score_jobs.py configs/harnoor.json
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_raw_jobs(config_name: str) -> list:
    path = f"outputs/raw_{config_name}.json"
    if not Path(path).exists():
        raise FileNotFoundError(f"{path} not found — run fetch_jobs.py first.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def text_of(job: dict) -> str:
    parts = [
        job.get("title", ""),
        job.get("descriptionText", "") or job.get("description", ""),
    ]
    return " ".join(parts).lower()


def title_of(job: dict) -> str:
    return (job.get("title") or "").lower()


def is_excluded(job: dict, config: dict) -> bool:
    title = title_of(job)
    return any(term.lower() in title for term in config.get("exclude_title_terms", []))


def score_job(job: dict, config: dict) -> tuple[int, list[str]]:
    body = text_of(job)
    title = title_of(job)
    skills = config.get("core_skills", {})

    total_weight = sum(s["weight"] for s in skills.values())
    matched_weight = 0
    matched_skills = []

    for skill_name, spec in skills.items():
        if any(variant.lower() in body for variant in spec["variants"]):
            matched_weight += spec["weight"]
            matched_skills.append(skill_name)

    title_bonus = config.get("title_match_bonus", 6)
    title_hit = any(role.lower() in title for role in config.get("target_roles", []))
    bonus = title_bonus if title_hit else 0

    if config.get("require_title_match", False) and not title_hit:
        return 0, matched_skills

    # Experience penalty: crude heuristic based on years mentioned near "years"
    penalty = 0
    years_required = extract_years_required(body)
    candidate_years = config.get("experience_years", 0)
    if years_required is not None and years_required > candidate_years:
        gap = years_required - candidate_years
        penalty = min(gap, config.get("max_experience_years_penalty", 5))

    denominator = total_weight + title_bonus
    raw_score = ((matched_weight + bonus - penalty) / denominator) * 100 if denominator else 0
    score = max(0, min(100, round(raw_score)))

    return score, matched_skills


def extract_years_required(body: str) -> int | None:
    match = re.search(r"(\d+)\+?\s*(?:to\s*\d+\s*)?years?", body)
    if match:
        return int(match.group(1))
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/score_jobs.py configs/<name>.json")
        sys.exit(1)

    config_path = sys.argv[1]
    config = load_config(config_path)
    config_name = Path(config_path).stem

    raw_jobs = load_raw_jobs(config_name)
    print(f"Scoring {len(raw_jobs)} postings for {config_name}...")

    rows = []
    now = datetime.now(timezone.utc).isoformat()

    for job in raw_jobs:
        if is_excluded(job, config):
            continue

        score, matched_skills = score_job(job, config)
        if score < config.get("min_match_score", 50):
            continue

        rows.append({
            "match_score": score,
            "source": "LinkedIn",
            "job_title": job.get("title", "Not listed"),
            "company": job.get("companyName", "Not listed"),
            "location": job.get("location", "Not listed"),
            "experience_required": "Not listed",
            "seniority": job.get("seniorityLevel", "Not listed"),
            "employment_type": job.get("employmentType", "Not listed"),
            "skills_matched": ", ".join(matched_skills) if matched_skills else "None",
            "posted": job.get("postedAt", "Not listed"),
            "applicants": job.get("applicantsCount", "Not listed"),
            "job_description": (job.get("descriptionText") or job.get("description") or "")[:500],
            "apply_link": job.get("jobUrl") or job.get("link") or "Not listed",
            "fetched_at": now,
        })

    df = pd.DataFrame(rows).sort_values("match_score", ascending=False)

    Path("outputs").mkdir(exist_ok=True)
    out_path = f"outputs/scored_{config_name}.json"
    df.to_json(out_path, orient="records", indent=2)

    print(f"{len(df)} postings scored >= {config.get('min_match_score', 50)}. Saved to {out_path}")


if __name__ == "__main__":
    main()
