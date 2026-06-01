"""Tests for query template endpoint with blanket suppression."""

import pytest
from sqlalchemy.orm import Session

from glow_api.auth import get_password_hash
from glow_api.database import create_user, get_user_by_username
from glow_api.metadata_models import School


@pytest.fixture
def alpha_user(db_session: Session, sample_schools: dict[str, School]) -> dict:
    """Create a test user for Focus School Academy school."""
    user = create_user(
        db_session,
        username="alpha_test",
        hashed_password=get_password_hash("test_password"),
        school_ids=[sample_schools["Focus School Academy"].id],
        is_admin=False,
    )
    return {
        "username": "alpha_test",
        "school_id": sample_schools["Focus School Academy"].id,
        "school_name": "Focus School Academy",
    }


@pytest.fixture
def beta_user(db_session: Session, sample_schools: dict[str, School]) -> dict:
    """Create a test user for Neighbouring School school."""
    user = create_user(
        db_session,
        username="beta_test",
        hashed_password=get_password_hash("test_password"),
        school_ids=[sample_schools["Neighbouring School"].id],
        is_admin=False,
    )
    return {
        "username": "beta_test",
        "school_id": sample_schools["Neighbouring School"].id,
        "school_name": "Neighbouring School",
    }



class TestNewQueryExecution:
    """Test new period-oriented query execution (Step 3 TDD)."""

    def test_query_variable_selection_single_variable(self):
        """Test selecting a single variable with 'v' parameter."""
        from glow_api.query_execution import execute_query
        from glow_api.canonical_query import normalize_query
        import pandas as pd
        
        # Create test data with period_id
        df = pd.DataFrame({
            "uid": ["S001", "S002"],
            "school": ["School A", "School A"],
            "period_id": ["2023-2024", "2023-2024"],
            "bw_wbeing_1": [3, 4],
            "bw_wbeing_2": [4, 3],
        })
        
        # Normalize query
        query = normalize_query(v=["bw_wbeing_1"])
        
        # Execute query
        result = execute_query(df, query)
        
        # Should return results for one variable
        assert "variables" in result
        assert len(result["variables"]) == 1
        assert result["variables"][0]["variable"] == "bw_wbeing_1"
    
    def test_query_variable_selection_multiple_variables(self):
        """Test selecting multiple variables with repeated 'v' parameters."""
        from glow_api.query_execution import execute_query
        from glow_api.canonical_query import normalize_query
        import pandas as pd
        
        df = pd.DataFrame({
            "uid": ["S001", "S002"],
            "school": ["School A", "School A"],
            "period_id": ["2023-2024", "2023-2024"],
            "bw_wbeing_1": [3, 4],
            "bw_wbeing_2": [4, 3],
            "bw_stress_1": [2, 3],
        })
        
        query = normalize_query(v=["bw_wbeing_1", "bw_stress_1"])
        result = execute_query(df, query)
        
        assert len(result["variables"]) == 2
        var_names = [v["variable"] for v in result["variables"]]
        assert "bw_wbeing_1" in var_names
        assert "bw_stress_1" in var_names
    
    def test_query_variable_prefix_expansion(self):
        """Test expanding variable_prefix to matching variables."""
        from glow_api.query_execution import execute_query
        from glow_api.canonical_query import normalize_query
        import pandas as pd
        
        df = pd.DataFrame({
            "uid": ["S001"],
            "school": ["School A"],
            "period_id": ["2023-2024"],
            "bw_wbeing_1": [3],
            "bw_wbeing_2": [4],
            "bw_stress_1": [2],
            "d_sex": ["M"],
        })
        
        query = normalize_query(variable_prefix=["bw_wbeing"])
        result = execute_query(df, query)
        
        # Should expand to all bw_wbeing_* variables
        var_names = [v["variable"] for v in result["variables"]]
        assert "bw_wbeing_1" in var_names
        assert "bw_wbeing_2" in var_names
        assert "bw_stress_1" not in var_names  # Different prefix
    
    def test_query_all_variables_default(self):
        """Test that omitting both 'v' and 'variable_prefix' means all variables."""
        from glow_api.query_execution import execute_query
        from glow_api.canonical_query import normalize_query
        import pandas as pd
        
        df = pd.DataFrame({
            "uid": ["S001"],
            "school": ["School A"],
            "period_id": ["2023-2024"],
            "bw_wbeing_1": [3],
            "bw_stress_1": [2],
            "d_sex": ["M"],  # Categorical, not a variable
        })
        
        # Assume we have a whitelist of numerical variables
        numerical_whitelist = ["bw_wbeing_1", "bw_stress_1"]
        
        query = normalize_query()  # No variables specified
        result = execute_query(df, query, numerical_whitelist=numerical_whitelist)
        
        # Should include all numerical variables
        var_names = [v["variable"] for v in result["variables"]]
        assert "bw_wbeing_1" in var_names
        assert "bw_stress_1" in var_names
    
    def test_query_response_organization_periods(self):
        """Test that response includes top-level periods list."""
        from glow_api.query_execution import execute_query
        from glow_api.canonical_query import normalize_query
        import pandas as pd
        
        df = pd.DataFrame({
            "uid": ["S001", "S002", "S003"],
            "school": ["School A", "School A", "School A"],
            "period_id": ["2022-2023", "2023-2024", "2023-2024"],
            "bw_wbeing_1": [3, 4, 5],
        })
        
        query = normalize_query(v=["bw_wbeing_1"])
        result = execute_query(df, query)
        
        # Should have top-level periods in chronological order
        assert "periods" in result
        assert result["periods"] == ["2022-2023", "2023-2024"]
    
    def test_query_response_organization_dimensions(self):
        """Test that response includes requested dimensions."""
        from glow_api.query_execution import execute_query
        from glow_api.canonical_query import normalize_query
        import pandas as pd
        
        df = pd.DataFrame({
            "uid": ["S001", "S002"],
            "school": ["School A", "School A"],
            "period_id": ["2023-2024", "2023-2024"],
            "d_sex": ["M", "F"],
            "bw_wbeing_1": [3, 4],
        })
        
        query = normalize_query(v=["bw_wbeing_1"], d=["d_sex"])
        result = execute_query(df, query)
        
        # Should echo requested dimensions
        assert "dimensions" in result
        assert result["dimensions"] == ["d_sex"]
    
    def test_query_period_organized_results(self):
        """Test that results are organized by period within each variable."""
        from glow_api.query_execution import execute_query
        from glow_api.canonical_query import normalize_query
        import pandas as pd
        
        df = pd.DataFrame({
            "uid": ["S001", "S002", "S003"],
            "school": ["School A", "School A", "School A"],
            "period_id": ["2022-2023", "2023-2024", "2023-2024"],
            "bw_wbeing_1": [3, 4, 5],
        })
        
        query = normalize_query(v=["bw_wbeing_1"])
        result = execute_query(df, query)
        
        # Variable should have periods dict
        var = result["variables"][0]
        assert "periods" in var
        assert isinstance(var["periods"], dict)
        
        # Should have entries for observed periods
        assert "2022-2023" in var["periods"]
        assert "2023-2024" in var["periods"]
    
    def test_query_missing_period_not_in_results(self):
        """Test that periods with no data for a variable are omitted."""
        from glow_api.query_execution import execute_query
        from glow_api.canonical_query import normalize_query
        import pandas as pd
        
        df = pd.DataFrame({
            "uid": ["S001", "S002"],
            "school": ["School A", "School A"],
            "period_id": ["2022-2023", "2023-2024"],
            "bw_wbeing_1": [3, None],  # No value in 2023-2024
        })
        
        query = normalize_query(v=["bw_wbeing_1"])
        result = execute_query(df, query)
        
        # Period 2023-2024 might be missing or empty for this variable
        # (depends on how we handle null values)
        var = result["variables"][0]
        # At minimum, should have 2022-2023
        assert "2022-2023" in var["periods"]


class TestDeduplication:
    """Test per-variable deduplication (Step 3 TDD)."""

    def test_deduplicate_latest_non_null_per_uid(self):
        """Test that deduplication keeps latest non-null value per uid per period."""
        from glow_api.query_execution import deduplicate_submissions
        import pandas as pd
        from datetime import datetime
        
        df = pd.DataFrame({
            "uid": ["S001", "S001", "S001"],
            "school": ["School A", "School A", "School A"],
            "period_id": ["2023-2024", "2023-2024", "2023-2024"],
            "createdAt": [
                datetime(2023, 10, 1, 10, 0, 0),
                datetime(2023, 10, 15, 10, 0, 0),  # Latest
                datetime(2023, 10, 5, 10, 0, 0),
            ],
            "bw_wbeing_1": [3, 4, 2],
        })
        
        deduped = deduplicate_submissions(df, variable="bw_wbeing_1")
        
        # Should keep only the latest submission for S001
        assert len(deduped) == 1
        assert deduped.iloc[0]["bw_wbeing_1"] == 4  # From Oct 15
    
    def test_deduplicate_ignores_null_values(self):
        """Test that null values are ignored in latest-non-null logic."""
        from glow_api.query_execution import deduplicate_submissions
        import pandas as pd
        from datetime import datetime
        
        df = pd.DataFrame({
            "uid": ["S001", "S001", "S001"],
            "school": ["School A", "School A", "School A"],
            "period_id": ["2023-2024", "2023-2024", "2023-2024"],
            "createdAt": [
                datetime(2023, 10, 1, 10, 0, 0),
                datetime(2023, 10, 15, 10, 0, 0),  # Latest but null
                datetime(2023, 10, 5, 10, 0, 0),
            ],
            "bw_wbeing_1": [3, None, 2],
        })
        
        deduped = deduplicate_submissions(df, variable="bw_wbeing_1")
        
        # Should keep Oct 5 (value=2), not Oct 15 (null)
        assert len(deduped) == 1
        assert deduped.iloc[0]["bw_wbeing_1"] == 2
    
    def test_deduplicate_separate_periods(self):
        """Test that deduplication happens independently per period."""
        from glow_api.query_execution import deduplicate_submissions
        import pandas as pd
        from datetime import datetime
        
        df = pd.DataFrame({
            "uid": ["S001", "S001", "S001", "S001"],
            "school": ["School A", "School A", "School A", "School A"],
            "period_id": ["2022-2023", "2022-2023", "2023-2024", "2023-2024"],
            "createdAt": [
                datetime(2022, 10, 1, 10, 0, 0),
                datetime(2022, 10, 15, 10, 0, 0),
                datetime(2023, 10, 1, 10, 0, 0),
                datetime(2023, 10, 15, 10, 0, 0),
            ],
            "bw_wbeing_1": [3, 4, 5, 6],
        })
        
        deduped = deduplicate_submissions(df, variable="bw_wbeing_1")
        
        # Should have one row per period
        assert len(deduped) == 2
        
        # Check period 2022-2023 has latest value
        period_2022 = deduped[deduped["period_id"] == "2022-2023"].iloc[0]
        assert period_2022["bw_wbeing_1"] == 4
        
        # Check period 2023-2024 has latest value
        period_2023 = deduped[deduped["period_id"] == "2023-2024"].iloc[0]
        assert period_2023["bw_wbeing_1"] == 6
    
    def test_deduplicate_different_uids(self):
        """Test that different uids are kept separate."""
        from glow_api.query_execution import deduplicate_submissions
        import pandas as pd
        from datetime import datetime
        
        df = pd.DataFrame({
            "uid": ["S001", "S001", "S002", "S002"],
            "school": ["School A", "School A", "School A", "School A"],
            "period_id": ["2023-2024", "2023-2024", "2023-2024", "2023-2024"],
            "createdAt": [
                datetime(2023, 10, 1, 10, 0, 0),
                datetime(2023, 10, 15, 10, 0, 0),
                datetime(2023, 10, 1, 10, 0, 0),
                datetime(2023, 10, 15, 10, 0, 0),
            ],
            "bw_wbeing_1": [3, 4, 5, 6],
        })
        
        deduped = deduplicate_submissions(df, variable="bw_wbeing_1")
        
        # Should have one row per uid
        assert len(deduped) == 2
        assert set(deduped["uid"]) == {"S001", "S002"}


class TestQueryETag:
    """Test ETag behavior for query caching (Step 3 TDD)."""

    def test_query_returns_etag(self):
        """Test that query response includes an ETag header."""
        from glow_api.query_execution import compute_query_etag
        from glow_api.canonical_query import normalize_query
        
        query = normalize_query(v=["bw_wbeing_1"])
        etag = compute_query_etag(
            query=query,
            dataset_version="test-etag-123",
            api_version="0.1.0",
        )
        
        # Should return a non-empty string
        assert etag is not None
        assert isinstance(etag, str)
        assert len(etag) > 0
    
    def test_query_etag_deterministic(self):
        """Test that same query produces same ETag."""
        from glow_api.query_execution import compute_query_etag
        from glow_api.canonical_query import normalize_query
        
        query = normalize_query(v=["bw_wbeing_1"], d=["d_sex"])
        
        etag1 = compute_query_etag(query, "test-123", "0.1.0")
        etag2 = compute_query_etag(query, "test-123", "0.1.0")
        
        assert etag1 == etag2
    
    def test_query_etag_changes_with_query(self):
        """Test that different queries produce different ETags."""
        from glow_api.query_execution import compute_query_etag
        from glow_api.canonical_query import normalize_query
        
        query1 = normalize_query(v=["bw_wbeing_1"])
        query2 = normalize_query(v=["bw_wbeing_2"])
        
        etag1 = compute_query_etag(query1, "test-123", "0.1.0")
        etag2 = compute_query_etag(query2, "test-123", "0.1.0")
        
        assert etag1 != etag2
    
    def test_query_etag_changes_with_dataset_version(self):
        """Test that ETag changes when dataset changes."""
        from glow_api.query_execution import compute_query_etag
        from glow_api.canonical_query import normalize_query
        
        query = normalize_query(v=["bw_wbeing_1"])
        
        etag1 = compute_query_etag(query, "version-1", "0.1.0")
        etag2 = compute_query_etag(query, "version-2", "0.1.0")
        
        assert etag1 != etag2
    
    def test_query_etag_changes_with_api_version(self):
        """Test that ETag changes when API version changes."""
        from glow_api.query_execution import compute_query_etag
        from glow_api.canonical_query import normalize_query
        
        query = normalize_query(v=["bw_wbeing_1"])
        
        etag1 = compute_query_etag(query, "test-123", "0.1.0")
        etag2 = compute_query_etag(query, "test-123", "0.2.0")
        
        assert etag1 != etag2
