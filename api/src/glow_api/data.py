import logging
import threading
from pathlib import Path
from typing import Dict, List

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler

from glow_api.settings import settings
from pydantic import BaseModel

from glow_api.utils import log_duration

logger = logging.getLogger(__name__)


class DataFrameWithWhitelists(BaseModel):
    df: pd.DataFrame
    categorical_whitelist: List[str]
    numerical_whitelist: List[str]

    model_config = {
        "arbitrary_types_allowed": True,
    }


class DataStore:
    """Thread-safe data store for the questionnaire DataFrame."""

    def __init__(self, data_path: str, refresh_hours: int) -> None:
        self._data_path = Path(data_path)
        self._refresh_hours = refresh_hours
        self._df: pd.DataFrame = pd.DataFrame()
        self._lock = threading.Lock()
        self._scheduler = BackgroundScheduler()
        self._categorical_whitelist: List[str] = []
        self._numerical_whitelist: List[str] = []

    def _load(self) -> pd.DataFrame:
        with log_duration("Load data") as log_data:
            path = self._data_path
            if path.suffix.lower() in {".parquet", ".pq"}:
                df = pd.read_parquet(path)
            else:
                df = pd.read_csv(path, dtype_backend="numpy_nullable")

            # Pre-compute derived scores
            log_data["path"] = path
            log_data["original_col_count"] = len(df.columns)
            log_data["row_count"] = len(df)
            df = self._process_loaded_data(df)
            log_data["derived_col_count"] = len(df) - log_data["original_col_count"]
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

        total_scores_computed = 0

        for subscale, columns in questionnaires_for_totals.items():
            df[subscale] = df[columns].sum(axis=1, skipna=True)
            total_scores_computed += 1
            logger.debug("Computed %s from %d columns", subscale, len(columns))

        if total_scores_computed > 0:
            logger.info(
                "Computed %d subscale/scale total scores", total_scores_computed
            )
        else:
            logger.warning("No questionnaire columns found to compute total scores")

        return df

    def refresh(self) -> None:
        """Reload data from disk, replacing the in-memory DataFrame."""
        logger.info("Refreshing data from %s", self._data_path)
        try:
            df = self._load()
        except FileNotFoundError:
            logger.warning(
                "Data file not found: %s — keeping previous data", self._data_path
            )
            return
        except Exception:
            logger.exception(
                "Failed to load data from %s — keeping previous data", self._data_path
            )
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
            )

    def startup(self) -> None:
        """Initial load and schedule periodic refresh."""
        self.refresh()
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


# Module-level singleton
datastore = DataStore(
    data_path=settings.DATA_PATH,
    refresh_hours=settings.DATA_REFRESH_HOURS,
)


def get_datastore() -> DataStore:
    """Dependency function that returns the current datastore instance.

    This allows tests to override the datastore by reassigning the module-level
    'datastore' variable, and the routers will pick up the new instance.
    """
    return datastore
