#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pandas", "requests", "tqdm", "urllib3"]
# requires-python = ">=3.12"
# ///
"""
Seed ODK Central with test data from data.csv

This script reads data.csv and submits each row as a submission to ODK Central.
It is idempotent - running it multiple times will not create duplicates.

Usage:
    python deploy/scripts/seed_odk_test_data.py \\
        --csv data/data.csv \\
        --odk-url http://localhost:8080 \\
        --email admin@example.com \\
        --password <password> \\
        --project-id 1 \\
        --form-id bewell_questionnaire \\
        [--limit 100]

Requirements:
    pip install pandas requests tqdm
"""
import argparse
import csv
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

import requests
from requests.auth import HTTPBasicAuth
from tqdm import tqdm


class ODKSeeder:
    """Seed ODK Central with test data."""
    
    def __init__(
        self,
        base_url: str,
        email: str,
        password: str,
        project_id: int,
        form_id: str,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth = HTTPBasicAuth(email, password)
        self.project_id = project_id
        self.form_id = form_id
        self.session = requests.Session()
        self.session.auth = self.auth
        
        # Disable SSL verification for local development with self-signed certs
        self.session.verify = False
        
        # Add Host header for ODK Central SNI (needed for local HTTPS)
        if "localhost" in base_url or "127.0.0.1" in base_url:
            self.session.headers.update({"Host": "odk.local"})
        
        # Suppress InsecureRequestWarning
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def get_existing_submissions(self) -> Set[str]:
        """Get set of existing submission instance IDs."""
        url = f"{self.base_url}/v1/projects/{self.project_id}/forms/{self.form_id}/submissions"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            submissions = response.json()
            instance_ids = {sub.get("instanceId", "").replace("uuid:", "") for sub in submissions}
            return instance_ids - {""}  # Remove empty strings
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"⚠️  Form '{self.form_id}' not found in project {self.project_id}")
                print(f"   Make sure the form has been uploaded to ODK Central first.")
                sys.exit(1)
            raise
    
    def create_submission_xml(self, row: Dict[str, str]) -> str:
        """Create ODK submission XML from a CSV row."""
        # Root element
        data = ET.Element("data", attrib={
            "id": self.form_id,
            "version": "1",
        })
        
        # Meta element with instanceID
        meta = ET.SubElement(data, "meta")
        instance_id = ET.SubElement(meta, "instanceID")
        uid = row.get("uid", "")
        instance_id.text = f"uuid:{uid}"
        
        # Add all fields from the row
        for field_name, value in row.items():
            if field_name and value:  # Skip empty fields
                # Clean field name (CSV might have BOM or whitespace)
                field_name = field_name.strip().strip('\ufeff')
                
                # Create element for this field
                element = ET.SubElement(data, field_name)
                element.text = str(value).strip()
        
        # Convert to XML string
        xml_str = ET.tostring(data, encoding="unicode", method="xml")
        
        # Add XML declaration
        return f'<?xml version="1.0"?>\n{xml_str}'
    
    def submit_submission(self, xml_data: str, instance_id: str) -> bool:
        """Submit a single submission to ODK Central."""
        url = f"{self.base_url}/v1/projects/{self.project_id}/forms/{self.form_id}/submissions"
        
        headers = {
            "Content-Type": "application/xml",
        }
        
        try:
            response = self.session.post(url, data=xml_data.encode("utf-8"), headers=headers)
            response.raise_for_status()
            return True
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 409:
                # Conflict - submission already exists (idempotency)
                return False
            else:
                print(f"\n❌ Failed to submit {instance_id}: {e}")
                print(f"   Response: {e.response.text}")
                return False
    
    def seed_from_csv(self, csv_path: Path, limit: int = None) -> Dict[str, int]:
        """Seed submissions from a CSV file."""
        print(f"📊 Reading CSV: {csv_path}")
        
        # Read CSV
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        total_rows = len(rows)
        if limit:
            rows = rows[:limit]
            print(f"   Limiting to first {limit} rows (total: {total_rows})")
        else:
            print(f"   Total rows: {total_rows}")
        
        # Get existing submissions
        print(f"\n🔍 Checking existing submissions in ODK Central...")
        existing_ids = self.get_existing_submissions()
        print(f"   Found {len(existing_ids)} existing submissions")
        
        # Filter rows to only new ones
        new_rows = []
        for row in rows:
            uid = row.get("uid", "").strip()
            if uid and uid not in existing_ids:
                new_rows.append(row)
        
        print(f"\n📤 {len(new_rows)} new submissions to upload ({len(rows) - len(new_rows)} already exist)")
        
        if not new_rows:
            print("✅ All submissions already exist - nothing to do!")
            return {"total": len(rows), "existing": len(rows), "submitted": 0, "failed": 0}
        
        # Submit new rows
        stats = {
            "total": len(rows),
            "existing": len(rows) - len(new_rows),
            "submitted": 0,
            "failed": 0,
        }
        
        print(f"\n⬆️  Uploading {len(new_rows)} submissions...")
        for row in tqdm(new_rows, desc="Submitting", unit="submission"):
            uid = row.get("uid", "").strip()
            
            # Create XML
            xml_data = self.create_submission_xml(row)
            
            # Submit
            success = self.submit_submission(xml_data, uid)
            
            if success:
                stats["submitted"] += 1
            else:
                stats["failed"] += 1
            
            # Rate limiting: small delay between submissions
            time.sleep(0.05)  # 50ms delay
        
        return stats


def main():
    parser = argparse.ArgumentParser(
        description="Seed ODK Central with test data from CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Seed all rows
  python deploy/scripts/seed_odk_test_data.py \\
      --csv data/data.csv \\
      --odk-url http://localhost:8080 \\
      --email admin@example.com \\
      --password secret \\
      --project-id 1

  # Seed first 100 rows only
  python deploy/scripts/seed_odk_test_data.py \\
      --csv data/data.csv \\
      --odk-url http://localhost:8080 \\
      --email admin@example.com \\
      --password secret \\
      --project-id 1 \\
      --limit 100
        """,
    )
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to CSV file with test data",
    )
    parser.add_argument(
        "--odk-url",
        type=str,
        required=True,
        help="ODK Central base URL (e.g., http://localhost:8080)",
    )
    parser.add_argument(
        "--email",
        type=str,
        required=True,
        help="ODK Central admin email",
    )
    parser.add_argument(
        "--password",
        type=str,
        required=True,
        help="ODK Central admin password",
    )
    parser.add_argument(
        "--project-id",
        type=int,
        required=True,
        help="ODK Central project ID",
    )
    parser.add_argument(
        "--form-id",
        type=str,
        default="bewell_questionnaire",
        help="Form ID (default: bewell_questionnaire)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of rows to seed (for testing)",
    )
    
    args = parser.parse_args()
    
    # Validate CSV exists
    if not args.csv.exists():
        print(f"❌ CSV file not found: {args.csv}")
        sys.exit(1)
    
    # Create seeder
    seeder = ODKSeeder(
        base_url=args.odk_url,
        email=args.email,
        password=args.password,
        project_id=args.project_id,
        form_id=args.form_id,
    )
    
    # Seed data
    start_time = datetime.now()
    stats = seeder.seed_from_csv(args.csv, limit=args.limit)
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Print summary
    print(f"\n{'=' * 60}")
    print(f"✅ Seeding complete!")
    print(f"{'=' * 60}")
    print(f"   Total rows:        {stats['total']}")
    print(f"   Already existed:   {stats['existing']}")
    print(f"   Newly submitted:   {stats['submitted']}")
    print(f"   Failed:            {stats['failed']}")
    print(f"   Time elapsed:      {elapsed:.1f}s")
    print(f"{'=' * 60}")
    
    if stats["failed"] > 0:
        print(f"\n⚠️  {stats['failed']} submissions failed - check logs above")
        sys.exit(1)


if __name__ == "__main__":
    main()
