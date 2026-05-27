"""
ODK Central client for fetching submissions and form metadata.

This module provides a wrapper around pyODK for fetching submissions from ODK Central
with ETAG-based caching and metadata extraction from XLSForms.
"""
import logging
from typing import Dict, Optional, Tuple
import re

import pandas as pd
import requests
from pyodk.client import Client as PyODKClient
from pyodk._utils.session import Session

logger = logging.getLogger(__name__)


class ODKClient:
    """Client for interacting with ODK Central."""
    
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        project_id: int,
        form_id: str,
    ):
        """Initialize ODK client.
        
        Args:
            base_url: ODK Central base URL (e.g., "http://service:8383")
            username: ODK Central username/email
            password: ODK Central password
            project_id: Default project ID
            form_id: Form ID to fetch submissions from
        """
        self.base_url = base_url
        self.username = username
        self.password = password
        self.project_id = project_id
        self.form_id = form_id
        
        # Initialize pyODK client
        self.client = PyODKClient(config_path=None)
        self.client.session = Session(
            base_url=base_url,
            username=username,
            password=password,
        )
        self.client.projects.default_project_id = project_id
        self.client.forms.default_form_id = form_id
    
    def fetch_submissions(self, etag: Optional[str] = None) -> Tuple[pd.DataFrame, Optional[str]]:
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
        
        try:
            # Use pyODK to fetch submissions as a table
            # This returns a pandas DataFrame
            df = self.client.submissions.get_table(
                form_id=self.form_id,
                project_id=self.project_id,
            )
            
            # pyODK doesn't expose ETAG directly, so we'll implement our own caching
            # For now, always return data (we'll add ETAG support separately)
            new_etag = None  # TODO: Implement ETAG support
            
            logger.info("Fetched %d submissions", len(df))
            
            return df, new_etag
        
        except Exception as e:
            logger.exception("Failed to fetch submissions from ODK Central")
            raise
    
    def get_form_metadata(self) -> Dict[str, Dict[str, int]]:
        """Extract metadata (min/max values) from form definition.
        
        Returns:
            Dict mapping field names to {"min": int, "max": int}
        """
        logger.info("Fetching form metadata for form=%s", self.form_id)
        
        try:
            # Download XLSForm and extract metadata
            xlsform_bytes = self.download_xlsform()
            metadata = self.extract_metadata_from_xlsform(xlsform_bytes)
            
            logger.info("Extracted metadata for %d fields", len(metadata))
            
            return metadata
        
        except Exception as e:
            logger.exception("Failed to fetch form metadata")
            raise
    
    def download_xlsform(self) -> bytes:
        """Download XLSForm definition for metadata extraction.
        
        Returns:
            XLSForm file content as bytes
        """
        # Use raw HTTP request since pyODK doesn't expose XLSForm download
        url = f"{self.base_url}/v1/projects/{self.project_id}/forms/{self.form_id}.xlsx"
        
        response = requests.get(
            url,
            auth=(self.username, self.password),
        )
        response.raise_for_status()
        
        return response.content
    
    def extract_metadata_from_xlsform(self, xlsform_bytes: bytes) -> Dict[str, Dict[str, int]]:
        """Extract min/max metadata from XLSForm.
        
        Args:
            xlsform_bytes: XLSForm file content
        
        Returns:
            Dict mapping field names to {"min": int, "max": int}
        """
        from io import BytesIO
        
        # Read XLSForm with pandas
        xl = pd.ExcelFile(BytesIO(xlsform_bytes))
        survey = pd.read_excel(xl, "survey")
        
        metadata = {}
        
        for _, row in survey.iterrows():
            field_name = row.get("name")
            constraint = row.get("constraint", "")
            
            if not field_name or not constraint:
                continue
            
            # Parse constraint to extract min/max
            # Constraints look like: ". >= 0 and . <= 5"
            min_val = None
            max_val = None
            
            # Extract >= constraints
            ge_match = re.search(r"\.\s*>=\s*(\d+)", str(constraint))
            if ge_match:
                min_val = int(ge_match.group(1))
            
            # Extract <= constraints
            le_match = re.search(r"\.\s*<=\s*(\d+)", str(constraint))
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
