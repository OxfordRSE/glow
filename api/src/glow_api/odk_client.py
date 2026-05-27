"""
ODK Central client for fetching submissions and form metadata.

This module provides a wrapper around pyODK for fetching submissions from ODK Central
with ETAG-based caching and metadata extraction from XLSForms.
"""
import logging
import os
from datetime import datetime
from json import JSONDecodeError
from typing import Dict, Optional, Tuple
import re
from io import BytesIO

import pandas as pd
import requests
import urllib3

logger = logging.getLogger(__name__)

# Disable SSL warnings if SSL verification is disabled
if os.getenv("GLOW_ODK_VERIFY_SSL", "true").lower() == "false":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ODKClient:
    """Client for interacting with ODK Central."""
    
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        project_id: int,
        form_id: str,
        verify_ssl: bool = True,
    ):
        """Initialize ODK client.
        
        Args:
            base_url: ODK Central base URL (e.g., "http://service:8383")
            username: ODK Central username/email
            password: ODK Central password
            project_id: Default project ID
            form_id: Form ID to fetch submissions from
            verify_ssl: Whether to verify SSL certificates (default: True)
        """
        self.base_url = base_url
        self.username = username
        self.password = password
        self.project_id = project_id
        self.form_id = form_id
        self.verify_ssl = verify_ssl
        
        # For nginx virtual hosting, set Host header to match SSL cert
        self.default_headers = {}
        if "nginx" in base_url.lower():
            self.default_headers["Host"] = "odk.local"
        
        # Authenticate with ODK Central
        response = requests.post(
            f"{self.base_url}/v1/sessions",
            json={"email": self.username, "password": self.password},
            headers=self.default_headers,
            verify=self.verify_ssl
        )
        if response.status_code != 200:
            response.raise_for_status()
            raise ConnectionError(f"Failed to connect to ODK Central: {response.status_code}")
        try:
            data = response.json()
            self.access_token = data["token"]
            self.token_expires = datetime.fromisoformat(data["expiresAt"].replace("Z", "+00:00"))
        except (JSONDecodeError, KeyError):
            logger.warning(f"Unexpeted ODK Central response format: {response.content}")
            raise ValueError("ODK Central response did not match expected shape.")
        
    def get(self, *args, **kwargs):
        # Add SSL verification setting if not explicitly provided
        if 'verify' not in kwargs:
            kwargs['verify'] = self.verify_ssl
        
        # Merge default headers with provided headers
        headers = dict(self.default_headers)
        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
        kwargs['headers'] = headers
        
        request = requests.get(*args, auth=(self.username, self.password), **kwargs)
        request.raise_for_status()
        return request

    def fetch_submissions(self, etag: Optional[str] = None) -> Optional[Tuple[pd.DataFrame, Optional[str]]]:
        """Fetch submissions from ODK Central.
        
        Args:
            etag: Optional ETAG from previous request for caching
        
        Returns:
            Tuple of (DataFrame with submissions, new ETAG)
            If ETAG matches (304), returns (empty DataFrame, same ETAG)
        """
        logger.info(
            "Fetching submissions for project=%d, form=%s",
            self.project_id,
            self.form_id,
        )

        url = f"{self.base_url}/v1/projects/{self.project_id}/forms/{self.form_id}/submissions.csv"
        response = self.get(url, headers={"etag": etag})
        if response.status_code == 304:
            return None
        new_etag = response.headers.get("etag")
        csv_data = response.content
        df = pd.read_csv(BytesIO(csv_data))
        return df, new_etag
    
    def get_form_metadata(self) -> Dict[str, Dict[str, int]]:
        """Extract metadata (min/max values) from form definition.
        
        Returns:
            Dict mapping field names to {"min": int, "max": int}
        """
        logger.info("Fetching form metadata for form=%s", self.form_id)
        
        try:
            # Download XML form definition and extract metadata
            xml_content = self.download_form_xml()
            metadata = self.extract_metadata_from_xml(xml_content)
            
            logger.info("Extracted metadata for %d fields", len(metadata))
            
            return metadata
        
        except Exception:
            logger.exception("Failed to fetch form metadata")
            raise
    
    def download_form_xml(self) -> str:
        """Download XML form definition for metadata extraction.
        
        Returns:
            XML form definition as string
        """
        url = f"{self.base_url}/v1/projects/{self.project_id}/forms/{self.form_id}.xml"
        response = self.get(url)
        
        return response.text
    
    def extract_metadata_from_xml(self, xml_content: str) -> Dict[str, Dict[str, int]]:
        """Extract min/max metadata from XML form definition.
        
        Args:
            xml_content: XML form definition content
        
        Returns:
            Dict mapping field names to {"min": int, "max": int}
        """
        import xml.etree.ElementTree as ET
        
        metadata = {}
        
        # Parse XML
        root = ET.fromstring(xml_content)
        
        # Find all bind elements (they contain the constraints)
        # XForms uses namespaces, so we need to handle that
        # The bind elements are in the default namespace
        for bind in root.findall(".//{http://www.w3.org/2002/xforms}bind"):
            nodeset = bind.get("nodeset")
            constraint = bind.get("constraint", "")
            
            if not nodeset or not constraint:
                continue
            
            # Extract field name from nodeset (e.g., "/data/bw_migration_1" -> "bw_migration_1")
            field_name = nodeset.split("/")[-1]
            
            # Parse constraint to extract min/max
            # Constraints in XML are HTML-encoded: ". &gt;= 0 and . &lt;= 5"
            # We need to decode them first
            import html
            constraint_decoded = html.unescape(constraint)
            
            min_val = None
            max_val = None
            
            # Extract >= constraints
            ge_match = re.search(r"\.\s*>=\s*(\d+)", constraint_decoded)
            if ge_match:
                min_val = int(ge_match.group(1))
            
            # Extract <= constraints
            le_match = re.search(r"\.\s*<=\s*(\d+)", constraint_decoded)
            if le_match:
                max_val = int(le_match.group(1))
            
            if min_val is not None and max_val is not None:
                metadata[field_name] = {"min": min_val, "max": max_val}
            elif min_val is not None:
                # Only min constraint (e.g., age >= 0)
                metadata[field_name] = {"min": min_val}
            elif max_val is not None:
                # Only max constraint
                metadata[field_name] = {"max": max_val}
        
        return metadata
