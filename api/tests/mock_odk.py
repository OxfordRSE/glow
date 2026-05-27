"""Mock ODK Client for testing."""

from typing import Dict, Optional, Tuple

import pandas as pd


class MockODKClient:
    """Mock ODK Client that returns predefined test data."""
    
    def __init__(
        self,
        submissions_df: Optional[pd.DataFrame] = None,
        metadata: Optional[Dict[str, Dict[str, int]]] = None,
        etag: Optional[str] = None,
    ):
        """Initialize mock ODK client.
        
        Args:
            submissions_df: DataFrame to return from fetch_submissions()
            metadata: Metadata dict to return from get_form_metadata()
            etag: ETAG to return (None means no ETAG support)
        """
        self.submissions_df = submissions_df if submissions_df is not None else pd.DataFrame()
        self.metadata = metadata if metadata is not None else {}
        self.etag = etag
        self.fetch_count = 0
        self.metadata_fetch_count = 0
    
    def fetch_submissions(self, etag: Optional[str] = None) -> Tuple[pd.DataFrame, Optional[str]]:
        """Mock fetch_submissions that returns predefined DataFrame.
        
        Args:
            etag: ETAG from previous request
            
        Returns:
            Tuple of (DataFrame, ETAG)
        """
        self.fetch_count += 1
        
        # If ETAG matches, return empty DataFrame
        if etag and self.etag and etag == self.etag:
            return pd.DataFrame(), self.etag
        
        return self.submissions_df.copy(), self.etag
    
    def get_form_metadata(self) -> Dict[str, Dict[str, int]]:
        """Mock get_form_metadata that returns predefined metadata.
        
        Returns:
            Dict mapping field names to {"min": int, "max": int}
        """
        self.metadata_fetch_count += 1
        return self.metadata.copy()
    
    def download_xlsform(self) -> bytes:
        """Mock download_xlsform (not used in tests)."""
        raise NotImplementedError("Mock download_xlsform not implemented")
    
    def extract_metadata_from_xlsform(self, xlsform_bytes: bytes) -> Dict[str, Dict[str, int]]:
        """Mock extract_metadata_from_xlsform (not used in tests)."""
        raise NotImplementedError("Mock extract_metadata_from_xlsform not implemented")
