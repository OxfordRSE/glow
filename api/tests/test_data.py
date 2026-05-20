"""Tests for the DataStore class and derived score computation."""

import io
import tempfile
import threading
from pathlib import Path

import pandas as pd
import pytest

from glow_api.data import DataStore
from glow_api.settings import settings


class TestComputeDerivedScores:
    """Test the _compute_derived_scores method."""

    def test_single_subscale_with_three_items(self):
        """Test computing a single subscale total from three items."""
        # Create a DataFrame with three items in one subscale
        df = pd.DataFrame({
            'uid': ['S001', 'S002', 'S003'],
            'bw_wbeing_1': [3, 4, 2],
            'bw_wbeing_2': [4, 3, 3],
            'bw_wbeing_3': [2, 4, 3],
        })
        
        # Create a DataStore instance and compute derived scores
        ds = DataStore.__new__(DataStore)
        result = ds._compute_derived_scores(df)
        
        # Verify the total column was created
        assert 'bw_wbeing_total' in result.columns
        
        # Verify the totals are computed correctly
        assert result.loc[0, 'bw_wbeing_total'] == 9  # 3 + 4 + 2
        assert result.loc[1, 'bw_wbeing_total'] == 11  # 4 + 3 + 4
        assert result.loc[2, 'bw_wbeing_total'] == 8  # 2 + 3 + 3

    def test_multiple_subscales(self):
        """Test computing totals for multiple subscales."""
        df = pd.DataFrame({
            'uid': ['S001', 'S002'],
            'bw_wbeing_1': [3, 4],
            'bw_wbeing_2': [4, 3],
            'bw_stress_1': [2, 3],
            'bw_stress_2': [1, 2],
            'bw_stress_3': [3, 4],
        })
        
        ds = DataStore.__new__(DataStore)
        result = ds._compute_derived_scores(df)
        
        # Verify both total columns were created
        assert 'bw_wbeing_total' in result.columns
        assert 'bw_stress_total' in result.columns
        
        # Verify the totals
        assert result.loc[0, 'bw_wbeing_total'] == 7  # 3 + 4
        assert result.loc[1, 'bw_wbeing_total'] == 7  # 4 + 3
        assert result.loc[0, 'bw_stress_total'] == 6  # 2 + 1 + 3
        assert result.loc[1, 'bw_stress_total'] == 9  # 3 + 2 + 4

    def test_handles_missing_values(self):
        """Test that missing values are handled correctly with skipna=True."""
        df = pd.DataFrame({
            'uid': ['S001', 'S002', 'S003'],
            'bw_wbeing_1': [3, None, 2],
            'bw_wbeing_2': [4, 3, None],
            'bw_wbeing_3': [2, 4, 3],
        })
        
        ds = DataStore.__new__(DataStore)
        result = ds._compute_derived_scores(df)
        
        # Verify totals skip NaN values
        assert result.loc[0, 'bw_wbeing_total'] == 9  # 3 + 4 + 2
        assert result.loc[1, 'bw_wbeing_total'] == 7  # 0 (NaN) + 3 + 4
        assert result.loc[2, 'bw_wbeing_total'] == 5  # 2 + 0 (NaN) + 3

    def test_all_missing_values_returns_zero(self):
        """Test that all missing values in a row result in a total of 0."""
        df = pd.DataFrame({
            'uid': ['S001', 'S002'],
            'bw_wbeing_1': [3, None],
            'bw_wbeing_2': [4, None],
        })
        
        ds = DataStore.__new__(DataStore)
        result = ds._compute_derived_scores(df)
        
        assert result.loc[0, 'bw_wbeing_total'] == 7  # 3 + 4
        assert result.loc[1, 'bw_wbeing_total'] == 0  # NaN + NaN = 0 with skipna=True

    def test_preserves_original_columns(self):
        """Test that original columns are preserved after computing derived scores."""
        df = pd.DataFrame({
            'uid': ['S001', 'S002'],
            'wave': [1, 2],
            'bw_wbeing_1': [3, 4],
            'bw_wbeing_2': [4, 3],
        })
        
        ds = DataStore.__new__(DataStore)
        result = ds._compute_derived_scores(df)
        
        # Verify original columns still exist
        assert 'uid' in result.columns
        assert 'wave' in result.columns
        assert 'bw_wbeing_1' in result.columns
        assert 'bw_wbeing_2' in result.columns
        
        # Verify original data is unchanged
        assert list(result['uid']) == ['S001', 'S002']
        assert list(result['wave']) == [1, 2]

    def test_no_questionnaire_columns(self):
        """Test behavior when there are no questionnaire columns to process."""
        df = pd.DataFrame({
            'uid': ['S001', 'S002'],
            'wave': [1, 2],
            'school': ['School A', 'School B'],
        })
        
        ds = DataStore.__new__(DataStore)
        result = ds._compute_derived_scores(df)
        
        # Should return the original DataFrame unchanged
        assert list(result.columns) == ['uid', 'wave', 'school']
        assert len(result) == 2

    def test_different_prefix(self):
        """Test computing scores for a different prefix (if configured)."""
        # Temporarily modify settings to include another prefix
        original_prefixes = settings.DATA_PREFIXES.copy()
        settings.DATA_PREFIXES = ["bw", "test"]
        
        try:
            df = pd.DataFrame({
                'uid': ['S001', 'S002'],
                'test_anxiety_1': [3, 4],
                'test_anxiety_2': [2, 3],
                'bw_wbeing_1': [4, 5],
            })
            
            ds = DataStore.__new__(DataStore)
            result = ds._compute_derived_scores(df)
            
            # Verify both prefixes generate totals
            assert 'test_anxiety_total' in result.columns
            assert 'bw_wbeing_total' in result.columns
            
            assert result.loc[0, 'test_anxiety_total'] == 5  # 3 + 2
            assert result.loc[1, 'test_anxiety_total'] == 7  # 4 + 3
            assert result.loc[0, 'bw_wbeing_total'] == 4
            assert result.loc[1, 'bw_wbeing_total'] == 5
        finally:
            # Restore original settings
            settings.DATA_PREFIXES = original_prefixes

    def test_comprehensive_beewell_example(self):
        """Test with a realistic BeeWell dataset containing multiple subscales."""
        df = pd.DataFrame({
            'uid': ['S001', 'S002', 'S003'],
            'wave': [1, 1, 1],
            'school': ['School A', 'School A', 'School B'],
            # Well-being subscale
            'bw_wbeing_1': [3, 4, 2],
            'bw_wbeing_2': [4, 3, 3],
            'bw_wbeing_3': [2, 4, 3],
            # Stress subscale
            'bw_stress_1': [2, 3, 1],
            'bw_stress_2': [1, 2, 2],
            # Self-esteem subscale
            'bw_selfest_1': [4, 4, 3],
            'bw_selfest_2': [3, 3, 4],
            'bw_selfest_3': [4, 4, 3],
            'bw_selfest_4': [3, 3, 4],
        })
        
        ds = DataStore.__new__(DataStore)
        result = ds._compute_derived_scores(df)
        
        # Verify all subscale totals are created
        assert 'bw_wbeing_total' in result.columns
        assert 'bw_stress_total' in result.columns
        assert 'bw_selfest_total' in result.columns
        
        # Verify computations for first student
        assert result.loc[0, 'bw_wbeing_total'] == 9  # 3 + 4 + 2
        assert result.loc[0, 'bw_stress_total'] == 3  # 2 + 1
        assert result.loc[0, 'bw_selfest_total'] == 14  # 4 + 3 + 4 + 3
        
        # Verify computations for second student
        assert result.loc[1, 'bw_wbeing_total'] == 11  # 4 + 3 + 4
        assert result.loc[1, 'bw_stress_total'] == 5  # 3 + 2
        assert result.loc[1, 'bw_selfest_total'] == 14  # 4 + 3 + 4 + 3

    def test_floating_point_values(self):
        """Test that floating point values are summed correctly."""
        df = pd.DataFrame({
            'uid': ['S001', 'S002'],
            'bw_wbeing_1': [3.5, 4.2],
            'bw_wbeing_2': [2.7, 3.8],
        })
        
        ds = DataStore.__new__(DataStore)
        result = ds._compute_derived_scores(df)
        
        assert result.loc[0, 'bw_wbeing_total'] == pytest.approx(6.2)  # 3.5 + 2.7
        assert result.loc[1, 'bw_wbeing_total'] == pytest.approx(8.0)  # 4.2 + 3.8

    def test_zero_values(self):
        """Test that zero values are included in the sum."""
        df = pd.DataFrame({
            'uid': ['S001', 'S002'],
            'bw_wbeing_1': [0, 4],
            'bw_wbeing_2': [3, 0],
            'bw_wbeing_3': [0, 0],
        })
        
        ds = DataStore.__new__(DataStore)
        result = ds._compute_derived_scores(df)
        
        assert result.loc[0, 'bw_wbeing_total'] == 3  # 0 + 3 + 0
        assert result.loc[1, 'bw_wbeing_total'] == 4  # 4 + 0 + 0


class TestDataStore:
    """Test the DataStore class functionality."""

    def test_init(self):
        """Test DataStore initialization."""
        ds = DataStore(data_path="test.csv", refresh_hours=24)
        
        assert ds._data_path == Path("test.csv")
        assert ds._refresh_hours == 24
        assert isinstance(ds._df, pd.DataFrame)
        assert ds._df.empty
        assert isinstance(ds._lock, type(threading.Lock()))

    def test_load_csv(self):
        """Test loading data from a CSV file."""
        # Create a temporary CSV file
        csv_data = """uid,wave,bw_wbeing_1,bw_wbeing_2
S001,1,3,4
S002,1,4,3
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_data)
            temp_path = f.name
        
        try:
            ds = DataStore(data_path=temp_path, refresh_hours=0)
            df = ds._load()
            
            # Verify data was loaded
            assert len(df) == 2
            assert 'uid' in df.columns
            assert 'bw_wbeing_1' in df.columns
            
            # Verify derived scores were computed
            assert 'bw_wbeing_total' in df.columns
            assert df.loc[0, 'bw_wbeing_total'] == 7  # 3 + 4
            assert df.loc[1, 'bw_wbeing_total'] == 7  # 4 + 3
        finally:
            Path(temp_path).unlink()

    def test_load_parquet(self):
        """Test loading data from a Parquet file."""
        # Create a temporary Parquet file
        df_original = pd.DataFrame({
            'uid': ['S001', 'S002'],
            'wave': [1, 1],
            'bw_wbeing_1': [3, 4],
            'bw_wbeing_2': [4, 3],
        })
        
        with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as f:
            temp_path = f.name
        
        try:
            df_original.to_parquet(temp_path)
            
            ds = DataStore(data_path=temp_path, refresh_hours=0)
            df = ds._load()
            
            # Verify data was loaded
            assert len(df) == 2
            assert 'uid' in df.columns
            assert 'bw_wbeing_1' in df.columns
            
            # Verify derived scores were computed
            assert 'bw_wbeing_total' in df.columns
            assert df.loc[0, 'bw_wbeing_total'] == 7  # 3 + 4
            assert df.loc[1, 'bw_wbeing_total'] == 7  # 4 + 3
        finally:
            Path(temp_path).unlink()

    def test_refresh(self):
        """Test refreshing data from disk."""
        # Create initial CSV
        csv_data = """uid,wave,bw_wbeing_1,bw_wbeing_2
S001,1,3,4
S002,1,4,3
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_data)
            temp_path = f.name
        
        try:
            ds = DataStore(data_path=temp_path, refresh_hours=0)
            ds.refresh()
            
            # Verify initial data
            df = ds.to_frozen().df
            assert len(df) == 2
            assert df.loc[0, 'bw_wbeing_total'] == 7
            
            # Update the CSV file
            new_csv_data = """uid,wave,bw_wbeing_1,bw_wbeing_2
S001,1,5,5
S002,1,6,6
S003,1,7,7
"""
            with open(temp_path, 'w') as f:
                f.write(new_csv_data)
            
            # Refresh and verify new data
            ds.refresh()
            df = ds.to_frozen().df
            assert len(df) == 3
            assert df.loc[0, 'bw_wbeing_total'] == 10  # 5 + 5
            assert df.loc[1, 'bw_wbeing_total'] == 12  # 6 + 6
            assert df.loc[2, 'bw_wbeing_total'] == 14  # 7 + 7
        finally:
            Path(temp_path).unlink()

    def test_refresh_file_not_found(self):
        """Test that refresh handles missing file gracefully."""
        ds = DataStore(data_path="nonexistent.csv", refresh_hours=0)
        # Set initial data
        ds._df = pd.DataFrame({'uid': ['S001']})
        
        # Refresh should not crash and should keep existing data
        ds.refresh()
        df = ds.to_frozen().df
        assert len(df) == 1
        assert 'uid' in df.columns

    def test_get_dataframe_returns_copy(self):
        """Test that get_dataframe returns a copy, not the original."""
        ds = DataStore(data_path="test.csv", refresh_hours=0)
        ds._df = pd.DataFrame({
            'uid': ['S001', 'S002'],
            'bw_wbeing_1': [3, 4],
        })
        
        # Get dataframe and modify it
        df1 = ds.to_frozen().df
        df1.loc[0, 'bw_wbeing_1'] = 999
        
        # Get dataframe again and verify original is unchanged
        df2 = ds.to_frozen().df
        assert df2.loc[0, 'bw_wbeing_1'] == 3

    def test_thread_safety(self):
        """Test that DataStore is thread-safe."""
        import time
        
        csv_data = """uid,wave,bw_wbeing_1,bw_wbeing_2
S001,1,3,4
S002,1,4,3
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_data)
            temp_path = f.name
        
        try:
            ds = DataStore(data_path=temp_path, refresh_hours=0)
            ds.startup()
            
            results = []
            errors = []
            
            def read_data():
                try:
                    for _ in range(10):
                        df = ds.to_frozen().df
                        results.append(len(df))
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(e)
            
            # Start multiple threads reading simultaneously
            threads = [threading.Thread(target=read_data) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            
            # Verify no errors occurred
            assert len(errors) == 0
            # Verify all reads returned consistent data
            assert all(r == 2 for r in results)
        finally:
            ds.shutdown()
            Path(temp_path).unlink()

    def test_startup_and_shutdown(self):
        """Test startup and shutdown methods."""
        csv_data = """uid,wave,bw_wbeing_1
S001,1,3
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_data)
            temp_path = f.name
        
        try:
            ds = DataStore(data_path=temp_path, refresh_hours=1)
            
            # Verify data is not loaded yet
            assert ds._df.empty
            
            # Startup should load data
            ds.startup()
            assert not ds._df.empty
            assert len(ds._df) == 1
            
            # Shutdown should stop scheduler
            ds.shutdown()
            assert not ds._scheduler.running
        finally:
            Path(temp_path).unlink()

    def test_startup_with_zero_refresh_hours(self):
        """Test that scheduler is not started when refresh_hours is 0."""
        csv_data = """uid,wave,bw_wbeing_1
S001,1,3
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_data)
            temp_path = f.name
        
        try:
            ds = DataStore(data_path=temp_path, refresh_hours=0)
            ds.startup()
            
            # Verify data is loaded
            assert not ds._df.empty
            
            # Verify scheduler is not running
            assert not ds._scheduler.running
        finally:
            Path(temp_path).unlink()


class TestDataStoreIntegration:
    """Integration tests using the sample_df fixture from conftest."""

    def test_sample_df_has_derived_scores(self, sample_df):
        """Test that the sample_df fixture includes computed derived scores."""
        assert 'bw_wbeing_total' in sample_df.columns
        
        # Verify a few totals manually
        # First row: S001, wave 1, bw_wbeing values: 3, 4, 2
        first_row = sample_df[
            (sample_df['uid'] == 'S001') & (sample_df['wave'] == 1)
        ].iloc[0]
        assert first_row['bw_wbeing_total'] == 9  # 3 + 4 + 2

    def test_multiple_waves_preserved(self, sample_df):
        """Test that derived scores work correctly across multiple waves."""
        # Get both waves for student S001
        s001_data = sample_df[sample_df['uid'] == 'S001'].sort_values('wave')
        
        assert len(s001_data) == 2
        
        # Wave 1: bw_wbeing values are 3, 4, 2
        assert s001_data.iloc[0]['bw_wbeing_total'] == 9  # 3 + 4 + 2
        
        # Wave 2: bw_wbeing values are 4, 3, 3
        assert s001_data.iloc[1]['bw_wbeing_total'] == 10  # 4 + 3 + 3
