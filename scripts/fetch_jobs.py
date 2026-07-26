"""
fetch_jobs.py

Calls Apify's LinkedIn Jobs Scraper actor with search terms built from a
config file, then verifies each returned posting is still accepting
applications before saving results to outputs/raw_<config_name>.json.

Usage:
    python scripts/fetch_jobs.py configs/harnoor.json
"""

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
# Curious Coder's LinkedIn Jobs Scraper (apify.com/curious_coder/linkedin-jobs-scraper).
# Verified against its real input schema: it takes an array of LinkedIn jobs
# search URLs, not flat title/location fields.
ACTOR_ID = "curious_coder~linkedin-jobs-scraper"
APIFY_RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"

LINKEDIN_VERIFY_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

# Country ISO2 -> LinkedIn geoId used in jobs search URLs.
COUNTRY_GEO_IDS = {
    "Canada": "101174742",
    "United States": "103644278",
}


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_search_url(keywords: str, config: dict) -> str:
    location = config["location"]
    location_str = f"{location['city']}, {location['region']}, {location['country']}"

    params = {
        "keywords": keywords,
        "location": location_str,
        "f_TPR": "r86400",  # last 24 hours
    }
    geo_id = COUNTRY_GEO_IDS.get(location["country"])
    if geo_id:
        params["geoId"] = geo_id

    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


def build_actor_input(config: dict) -> dict:
    # One search URL per target role keeps each query focused — LinkedIn's
    # own OR-matching across many titles in one string is unreliable.
    search_urls = [
        build_search_url(role, config) for role in config["target_roles"]
    ]

    return {
        "urls": search_urls,
        "scrapeCompany": False,  # set True if you want employer metadata too (slower, more expensive)
        "count": config.get("results_per_search", 50),
        "useIncognitoMode": True,
        "splitByLocation": False,
    }


def call_apify_actor(actor_input: dict) -> list:
    if not APIFY_TOKEN:
        raise RuntimeError("APIFY_TOKEN is not set. Check your .env or repo secrets.")

    resp = requests.post(
        APIFY_RUN_SYNC_URL,
        params={"token": APIFY_TOKEN},
        json=actor_input,
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


def verify_listing_still_open(job_id: str) -> bool:
    """
    LinkedIn's guest job-posting endpoint still returns a page for expired
    postings, but the Apply button markup disappears. We treat its absence
    as "closed" and drop the listing.
    """
    try:
        resp = requests.get(
            LINKEDIN_VERIFY_URL.format(job_id=job_id),
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if resp.status_code != 200:
            return False
        return "top-card-layout__cta--primary" in resp.text
    except requests.RequestException:
        # Network hiccup — don't silently drop a possibly-good listing.
        return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/fetch_jobs.py configs/<name>.json")
        sys.exit(1)

    config_path = sys.argv[1]
    config = load_config(config_path)
    config_name = Path(config_path).stem

    print(f"Fetching jobs for config: {config_name}")
    actor_input = build_actor_input(config)
    raw_results = call_apify_actor(actor_input)
    print(f"Apify returned {len(raw_results)} raw postings.")

    if config.get("verify_listings", True):
        verified = []
        for i, job in enumerate(raw_results):
            job_id = job.get("jobPostingId") or job.get("id")
            if not job_id:
                verified.append(job)
                continue
            if verify_listing_still_open(str(job_id)):
                verified.append(job)
            time.sleep(1)  # stay under LinkedIn's guest rate limit
            if (i + 1) % 25 == 0:
                print(f"  verified {i + 1}/{len(raw_results)}...")
        print(f"{len(verified)}/{len(raw_results)} postings still open.")
        raw_results = verified

    Path("outputs").mkdir(exist_ok=True)
    out_path = f"outputs/raw_{config_name}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(raw_results, f, indent=2)

    print(f"Saved {len(raw_results)} postings to {out_path}")


if __name__ == "__main__":
    main()
