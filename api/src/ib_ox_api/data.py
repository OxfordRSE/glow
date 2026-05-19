import logging
import threading
from pathlib import Path

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler

from ib_ox_api.settings import settings

logger = logging.getLogger(__name__)


class DataStore:
    """Thread-safe data store for the questionnaire DataFrame."""

    def __init__(self, data_path: str, refresh_hours: int) -> None:
        self._data_path = Path(data_path)
        self._refresh_hours = refresh_hours
        self._df: pd.DataFrame = pd.DataFrame()
        self._lock = threading.Lock()
        self._scheduler = BackgroundScheduler()

    def _load(self) -> pd.DataFrame:
        path = self._data_path
        if path.suffix.lower() in {".parquet", ".pq"}:
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path, dtype_backend="numpy_nullable")
        
        # Pre-compute derived scores
        df = self._compute_derived_scores(df)
        return df
    
    def _compute_derived_scores(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add derived score columns to the DataFrame.
        
        Computes subscale totals and scale totals for all BeeWell questionnaires
        where it makes sense to aggregate items.
        """
        # Define questionnaires that should have total scores computed
        # Format: (prefix, number_of_items)
        questionnaires_for_totals = [
            ("bw_migration", 3),
            ("bw_wbeing", 7),  # SWEMWBS wellbeing scale
            ("bw_selfest", 5),  # Self-esteem
            ("bw_emoreg", 3),  # Emotional regulation
            ("bw_stress", 2),
            ("bw_coping", 2),
            ("bw_emodies", 10),  # Emotional difficulties
            ("bw_behav", 6),  # Behavioral difficulties
            ("bw_unhealthy", 4),  # Unhealthy food
            ("bw_socmtype", 2),  # Social media type
            ("bw_activ", 11),  # Activities
            ("bw_staffrel", 4),  # Staff relationships
            ("bw_localenv", 4),  # Local environment
            ("bw_future", 7),  # Future optimism
            ("bw_plans", 8),  # Future plans
            ("bw_gmacs", 2),  # GM active choices
            ("bw_parentsrel", 4),  # Parent relationships
            ("bw_friends", 4),  # Friendship quality
            ("bw_discrim", 5),  # Discrimination
            ("bw_discloc", 7),  # Discrimination location
            ("bw_bullying", 3),  # Bullying
            ("bw_mhcontact", 6),  # Mental health contact
        ]
        
        total_scores_computed = 0
        
        for prefix, n_items in questionnaires_for_totals:
            item_cols = [f"{prefix}_{i}" for i in range(1, n_items + 1)]
            existing_cols = [col for col in item_cols if col in df.columns]
            
            if existing_cols:
                total_col = f"{prefix}_total"
                df[total_col] = df[existing_cols].sum(axis=1, skipna=True)
                total_scores_computed += 1
                logger.debug("Computed %s from %d columns", total_col, len(existing_cols))
        
        if total_scores_computed > 0:
            logger.info("Computed %d subscale/scale total scores", total_scores_computed)
        else:
            logger.warning("No questionnaire columns found to compute total scores")
        
        return df

    def refresh(self) -> None:
        """Reload data from disk, replacing the in-memory DataFrame."""
        logger.info("Refreshing data from %s", self._data_path)
        try:
            df = self._load()
        except FileNotFoundError:
            logger.warning("Data file not found: %s — keeping previous data", self._data_path)
            return
        except Exception:
            logger.exception("Failed to load data from %s — keeping previous data", self._data_path)
            return
        with self._lock:
            self._df = df
        logger.info("Data refreshed: %d rows, %d columns", len(df), len(df.columns))

    def get_dataframe(self) -> pd.DataFrame:
        """Return a snapshot of the current DataFrame."""
        with self._lock:
            return self._df.copy()

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
