import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler

from glow_api.odk_client import ODKClient
from glow_api.settings import settings
from pydantic import BaseModel

from glow_api.utils import log_duration

logger = logging.getLogger(__name__)


class DataFrameWithWhitelists(BaseModel):
    df: pd.DataFrame
    categorical_whitelist: List[str]
    numerical_whitelist: List[str]
    metadata: Dict[str, Dict[str, int]]

    model_config = {
        "arbitrary_types_allowed": True,
    }


class DataStore:
    """Thread-safe data store for the questionnaire DataFrame."""

    def __init__(
        self,
        odk_client: ODKClient,
        refresh_hours: int,
        cache_path: Optional[Path] = None,
    ) -> None:
        self._odk_client = odk_client
        self._refresh_hours = refresh_hours
        self._cache_path = cache_path
        self._df: pd.DataFrame = pd.DataFrame()
        self._metadata: Dict[str, Dict[str, int]] = {}
        self._etag: Optional[str] = None
        self._lock = threading.Lock()
        self._scheduler = BackgroundScheduler()
        self._categorical_whitelist: List[str] = []
        self._numerical_whitelist: List[str] = []

    def _load(self) -> pd.DataFrame:
        with log_duration("Load data from ODK Central") as log_data:
            # Fetch submissions from ODK Central
            df, new_etag = self._odk_client.fetch_submissions(etag=self._etag)
            
            # If ETAG matched (304), df will be empty - keep existing data
            if df.empty and self._etag is not None:
                logger.info("Data unchanged (ETAG match)")
                log_data["etag_matched"] = True
                return self._df
            
            # Update ETAG
            self._etag = new_etag
            
            # Fetch form metadata (min/max values)
            self._metadata = self._odk_client.get_form_metadata()
            
            log_data["row_count"] = len(df)
            log_data["original_col_count"] = len(df.columns)
            log_data["metadata_fields"] = len(self._metadata)
            
            # Pre-compute derived scores
            df = self._process_loaded_data(df)
            log_data["derived_col_count"] = len(df.columns) - log_data["original_col_count"]
            
            # Cache if configured
            if self._cache_path:
                self._save_cache(df, new_etag)
            
            return df

    def _process_loaded_data(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self._compute_derived_scores(df)
        self._extract_whitelists(df)
        return df

    def _extract_whitelists(self, df: pd.DataFrame) -> None:
        categorical: List[str] = [
            "yearGroup",
            "class",
            "sex",
            "d_sex",
            "ethnicity",
            "d_ethnicity",
            "d_age",
            "d_city",
            "d_country",
        ]
        numerical: List[str] = []
        for col in df.columns:
            split = col.split("_")
            if len(split) > 1 and split[0] in settings.DATA_PREFIXES:
                numerical.append(col)
        self._categorical_whitelist = categorical
        self._numerical_whitelist = numerical

    def _compute_derived_scores(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add derived score columns to the DataFrame.

        Computes subscale totals and scale totals for all BeeWell questionnaires
        where it makes sense to aggregate items.
        """
        # Define questionnaires that should have total scores computed and the items that comprise them
        questionnaires_for_totals: Dict[str, List[str]] = {}
        for prefix in settings.DATA_PREFIXES:
            pf = f"{prefix}_"
            cols = [col for col in df.columns if col.startswith(pf)]
            for c in cols:
                split = c.split("_")
                if len(split) < 2:
                    continue
                ss = "_".join(split[1:-1])
                subscale = f"{prefix}_{ss}_total"
                if subscale in questionnaires_for_totals:
                    questionnaires_for_totals[subscale].append(c)
                else:
                    questionnaires_for_totals[subscale] = [c]

        # Collect all computed subscale scores to avoid DataFrame fragmentation
        computed_scores = {}
        
        for subscale, columns in questionnaires_for_totals.items():
            # Only compute if the column doesn't already exist
            if subscale not in df.columns:
                computed_scores[subscale] = df[columns].sum(axis=1, skipna=True)
                logger.debug("Computed %s from %d columns", subscale, len(columns))
            else:
                logger.debug("Skipping %s - already exists in data", subscale)

        # Concatenate all computed scores at once instead of iteratively assigning
        if computed_scores:
            df = pd.concat([df, pd.DataFrame(computed_scores)], axis=1)
            logger.info(
                "Computed %d subscale/scale total scores", len(computed_scores)
            )
        else:
            logger.warning("No questionnaire columns found to compute total scores")

        return df

    def _save_cache(self, df: pd.DataFrame, etag: Optional[str]) -> None:
        """Save DataFrame and ETAG to cache."""
        if not self._cache_path:
            return
        
        try:
            cache_dir = self._cache_path.parent
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Save DataFrame
            df.to_parquet(self._cache_path)
            
            # Save ETAG alongside DataFrame
            if etag:
                etag_path = self._cache_path.with_suffix(".etag")
                etag_path.write_text(etag)
            
            logger.info("Cached data to %s", self._cache_path)
        except Exception:
            logger.exception("Failed to save cache")
    
    def _load_cache(self) -> Optional[Tuple[pd.DataFrame, Optional[str]]]:
        """Load DataFrame and ETAG from cache.
        
        Returns:
            Tuple of (DataFrame, ETAG) or None if cache doesn't exist
        """
        if not self._cache_path or not self._cache_path.exists():
            return None
        
        try:
            df = pd.read_parquet(self._cache_path)
            
            # Load ETAG if it exists
            etag_path = self._cache_path.with_suffix(".etag")
            etag = etag_path.read_text() if etag_path.exists() else None
            
            logger.info("Loaded cached data from %s", self._cache_path)
            return df, etag
        except Exception:
            logger.exception("Failed to load cache")
            return None

    def refresh(self) -> None:
        """Reload data from ODK Central, replacing the in-memory DataFrame."""
        logger.info("Refreshing data from ODK Central")
        try:
            df = self._load()
        except Exception:
            logger.exception(
                "Failed to load data from ODK Central — keeping previous data"
            )
            # Serve stale data on error (graceful degradation)
            return
        with self._lock:
            self._df = df
        logger.info("Data refreshed: %d rows, %d columns", len(df), len(df.columns))

    def to_frozen(self) -> DataFrameWithWhitelists:
        """Return a snapshot of the current DataFrame."""
        with self._lock:
            return DataFrameWithWhitelists(
                df=self._df.copy(),
                categorical_whitelist=self._categorical_whitelist,
                numerical_whitelist=self._numerical_whitelist,
                metadata=self._metadata.copy(),
            )

    def startup(self) -> None:
        """Initial load and schedule periodic refresh."""
        # Try loading from cache first
        cached = self._load_cache()
        if cached:
            df, etag = cached
            with self._lock:
                self._df = df
                self._etag = etag
            logger.info(
                "Loaded from cache: %d rows, %d columns", len(df), len(df.columns)
            )
        
        # Try to refresh on startup, but don't fail if ODK isn't ready yet
        try:
            self.refresh()
        except Exception:
            logger.warning(
                "Failed to refresh data from ODK Central on startup - will retry on schedule",
                exc_info=True
            )
            # If we have no cached data either, create empty DataFrame
            if cached is None:
                with self._lock:
                    self._df = pd.DataFrame()
                    self._metadata = {}
        
        if self._refresh_hours > 0:
            self._scheduler.add_job(
                self.refresh,
                trigger="interval",
                hours=self._refresh_hours,
                id="data_refresh",
            )
            self._scheduler.start()
            logger.info("Data refresh scheduled every %d hour(s)", self._refresh_hours)

    def shutdown(self) -> None:
        """Stop the background scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Data refresh scheduler stopped")


# Module-level singleton (lazy initialization)
_odk_client: Optional[ODKClient] = None
datastore: Optional[DataStore] = None


def _init_singleton():
    """Initialize the module-level singleton DataStore."""
    global _odk_client, datastore
    
    if datastore is not None:
        return
    
    _odk_client = ODKClient(
        base_url=settings.ODK_API_URL,
        username=settings.ODK_API_EMAIL,
        password=settings.ODK_API_PASSWORD,
        project_id=settings.ODK_PROJECT_ID,
        form_id=settings.ODK_FORM_ID,
        verify_ssl=os.getenv("GLOW_ODK_VERIFY_SSL", "true").lower() != "false",
    )

    datastore = DataStore(
        odk_client=_odk_client,
        refresh_hours=settings.DATA_REFRESH_HOURS,
        cache_path=Path(settings.DATA_CACHE_PATH) if settings.DATA_CACHE_PATH else None,
    )


def get_datastore() -> DataStore:
    """Dependency function that returns the current datastore instance.

    This allows tests to override the datastore by reassigning the module-level
    'datastore' variable, and the routers will pick up the new instance.
    """
    if datastore is None:
        _init_singleton()
    return datastore
