#!/usr/bin/env python3
"""Seed a minimal set of PHQ-9 submissions into ODK Central for compose-smoke.

Unlike seed_odk_test_data.py, this does not go through transform_mock_data.py's
manifest/multi-form pipeline (which requires >=20 schools and 3 waves of source
data). testdata/demo_data.csv already matches phq9_questionnaire's fields
1:1 (uid, school, phq9_1, phq9_2, phq9_3), so rows are submitted directly.

Only a single wave is seeded - "wave" is not a form field, and representing
multiple waves properly requires backdating submission timestamps in ODK's
Postgres (see rewrite_odk_submission_timestamps.py), which is unnecessary for
a smoke test.
"""

import argparse
import csv
import ssl
import sys
import urllib.error
import urllib.request
from base64 import b64encode
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

FIELDS = ("uid", "school", "phq9_1", "phq9_2", "phq9_3")


def request(method: str, url: str, email: str, password: str, data: bytes | None = None, content_type: str | None = None):
    headers = {
        "Authorization": "Basic " + b64encode(f"{email}:{password}".encode()).decode(),
        "Host": "odk.local",
    }
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl._create_unverified_context()
    return urllib.request.urlopen(req, context=ctx)


def existing_instance_ids(base_url: str, project_id: str, form_id: str, email: str, password: str) -> set[str]:
    url = f"{base_url}/v1/projects/{project_id}/forms/{form_id}/submissions"
    try:
        with request("GET", url, email, password) as resp:
            import json

            submissions = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"Form '{form_id}' not found in project {project_id}; upload it first.", file=sys.stderr)
            sys.exit(1)
        raise
    return {sub["instanceId"] for sub in submissions if sub.get("instanceId")}


def build_submission_xml(row: dict, form_id: str, form_version: str, instance_id: str) -> bytes:
    data = Element("data", attrib={"id": form_id, "version": form_version})
    for field in FIELDS:
        value = row.get(field, "")
        if value == "":
            continue
        el = SubElement(data, field)
        el.text = value
    meta = SubElement(data, "meta")
    instance_el = SubElement(meta, "instanceID")
    instance_el.text = instance_id
    return b'<?xml version="1.0"?>\n' + tostring(data, encoding="unicode").encode()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed minimal PHQ-9 submissions for compose-smoke")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--odk-url", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--form-id", default="phq9_questionnaire")
    parser.add_argument("--form-version", default="1")
    parser.add_argument("--wave", default="1")
    args = parser.parse_args()

    base_url = args.odk_url.rstrip("/")

    existing = existing_instance_ids(base_url, args.project_id, args.form_id, args.email, args.password)

    with args.csv.open(newline="", encoding="utf-8") as f:
        rows = [row for row in csv.DictReader(f) if row.get("wave") == args.wave]

    submitted = existing_count = failed = 0
    for row in rows:
        instance_id = f"uuid:smoke-{row['uid']}"
        if instance_id in existing:
            existing_count += 1
            continue

        xml_body = build_submission_xml(row, args.form_id, args.form_version, instance_id)
        url = f"{base_url}/v1/projects/{args.project_id}/forms/{args.form_id}/submissions"
        try:
            with request("POST", url, args.email, args.password, data=xml_body, content_type="application/xml"):
                submitted += 1
        except urllib.error.HTTPError as e:
            if e.code == 409:
                existing_count += 1
                continue
            print(f"Failed to submit {instance_id}: {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
            failed += 1

    print(f"PHQ-9 seed: {submitted} submitted, {existing_count} already existed, {failed} failed (of {len(rows)} wave={args.wave} rows)")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
