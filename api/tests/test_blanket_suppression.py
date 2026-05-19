"""Tests for blanket suppression logic.

Blanket suppression ensures that if ANY cell in a result set has 0 < n < MIN_N,
the ENTIRE result is suppressed (not just individual cells).

This prevents differencing attacks where attackers can infer suppressed values
by comparing overlapping cohorts.
"""

import io

import pandas as pd
import pytest


def _make_df(csv_text: str) -> pd.DataFrame:
    """Helper to create DataFrames from CSV strings."""
    return pd.read_csv(io.StringIO(csv_text))


# ---------------------------------------------------------------------------
# Test Data Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def safe_cohort_df():
    """A cohort where all groups have n >= 5 (safe)."""
    return _make_df("""uid,school,yearGroup,d_sex,bw_wbeing_1
S001,Focus School Academy,7,M,3
S002,Focus School Academy,7,M,4
S003,Focus School Academy,7,M,2
S004,Focus School Academy,7,M,4
S005,Focus School Academy,7,M,3
S006,Focus School Academy,7,F,4
S007,Focus School Academy,7,F,3
S008,Focus School Academy,7,F,4
S009,Focus School Academy,7,F,2
S010,Focus School Academy,7,F,3
S011,Focus School Academy,8,M,3
S012,Focus School Academy,8,M,4
S013,Focus School Academy,8,M,2
S014,Focus School Academy,8,M,4
S015,Focus School Academy,8,M,3
S016,Focus School Academy,8,F,4
S017,Focus School Academy,8,F,3
S018,Focus School Academy,8,F,4
S019,Focus School Academy,8,F,2
S020,Focus School Academy,8,F,3
""")


@pytest.fixture
def unsafe_cohort_df():
    """A cohort where one group has n=3 (unsafe, should trigger blanket suppression)."""
    return _make_df("""uid,school,yearGroup,d_sex,bw_wbeing_1
S001,Focus School Academy,7,M,3
S002,Focus School Academy,7,M,4
S003,Focus School Academy,7,M,2
S004,Focus School Academy,7,M,4
S005,Focus School Academy,7,M,3
S006,Focus School Academy,7,F,4
S007,Focus School Academy,7,F,3
S008,Focus School Academy,7,F,4
S009,Focus School Academy,7,F,2
S010,Focus School Academy,7,F,3
S011,Focus School Academy,8,M,3
S012,Focus School Academy,8,M,4
S013,Focus School Academy,8,M,2
S014,Focus School Academy,8,F,4
S015,Focus School Academy,8,F,3
S016,Focus School Academy,8,F,4
""")


@pytest.fixture
def multi_school_df():
    """Multiple schools with varying cohort sizes."""
    return _make_df("""uid,school,yearGroup,d_sex,bw_wbeing_1
S001,Focus School Academy,7,M,3
S002,Focus School Academy,7,M,4
S003,Focus School Academy,7,M,2
S004,Focus School Academy,7,M,4
S005,Focus School Academy,7,M,3
S006,Focus School Academy,7,F,4
S007,Focus School Academy,7,F,3
S008,Focus School Academy,7,F,4
S009,Focus School Academy,7,F,2
S010,Focus School Academy,7,F,3
S011,Neighbouring School,7,M,3
S012,Neighbouring School,7,M,4
S013,Neighbouring School,7,F,2
""")


# ---------------------------------------------------------------------------
# Unit Tests for Blanket Suppression Logic
# ---------------------------------------------------------------------------


class TestBlanketSuppressionChecker:
    """Test the core blanket suppression checking logic."""

    def test_safe_cohort_no_suppression(self, safe_cohort_df):
        """When all groups have n >= MIN_N, no suppression should occur."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        min_n = 5
        group_by = ["yearGroup", "d_sex"]
        
        is_suppressed = check_blanket_suppression(
            df=safe_cohort_df,
            school="Focus School Academy",
            group_by=group_by,
            min_n=min_n
        )
        
        assert is_suppressed is False, "Safe cohort should not be suppressed"

    def test_unsafe_cohort_triggers_suppression(self, unsafe_cohort_df):
        """When any group has 0 < n < MIN_N, entire result should be suppressed."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        min_n = 5
        group_by = ["yearGroup", "d_sex"]
        
        is_suppressed = check_blanket_suppression(
            df=unsafe_cohort_df,
            school="Focus School Academy",
            group_by=group_by,
            min_n=min_n
        )
        
        assert is_suppressed is True, "Cohort with small group should be suppressed"

    def test_zero_size_groups_are_safe(self):
        """Empty groups (n=0) are safe and should not trigger suppression."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        # All students are in yearGroup 7, so yearGroup 8 groups will have n=0
        df = _make_df("""uid,school,yearGroup,d_sex,bw_wbeing_1
S001,Focus School Academy,7,M,3
S002,Focus School Academy,7,M,4
S003,Focus School Academy,7,M,2
S004,Focus School Academy,7,M,4
S005,Focus School Academy,7,M,3
S006,Focus School Academy,7,F,4
S007,Focus School Academy,7,F,3
S008,Focus School Academy,7,F,4
S009,Focus School Academy,7,F,2
S010,Focus School Academy,7,F,3
""")
        
        min_n = 5
        group_by = ["yearGroup", "d_sex"]
        
        is_suppressed = check_blanket_suppression(
            df=df,
            school="Focus School Academy",
            group_by=group_by,
            min_n=min_n
        )
        
        # Should be safe because only observed groups are checked
        assert is_suppressed is False, "Zero-size groups should not trigger suppression"

    def test_multi_school_isolation(self, multi_school_df):
        """Each school's suppression should be checked independently."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        min_n = 5
        group_by = ["yearGroup", "d_sex"]
        
        # Focus School Academy has safe groups (5 M, 5 F)
        alpha_suppressed = check_blanket_suppression(
            df=multi_school_df,
            school="Focus School Academy",
            group_by=group_by,
            min_n=min_n
        )
        assert alpha_suppressed is False, "Focus School Academy should be safe"
        
        # Neighbouring School has unsafe groups (2 M, 1 F)
        beta_suppressed = check_blanket_suppression(
            df=multi_school_df,
            school="Neighbouring School",
            group_by=group_by,
            min_n=min_n
        )
        assert beta_suppressed is True, "Neighbouring School should be suppressed"

    def test_no_grouping_overall_count(self):
        """When group_by is empty, check overall school count."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        # Small school with only 3 students
        df = _make_df("""uid,school,yearGroup,d_sex,bw_wbeing_1
S001,Tiny,7,M,3
S002,Tiny,7,F,4
S003,Tiny,7,M,2
""")
        
        min_n = 5
        group_by = []  # No grouping, overall count
        
        is_suppressed = check_blanket_suppression(
            df=df,
            school="Tiny",
            group_by=group_by,
            min_n=min_n
        )
        
        assert is_suppressed is True, "Small school overall count should be suppressed"


class TestBlanketSuppressionWithWaveAggregation:
    """Test blanket suppression when aggregating by wave."""

    def test_wave_aggregation_all_waves_safe(self):
        """When aggregating by wave and all wave groups are safe."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        df = _make_df("""uid,school,wave,yearGroup,bw_wbeing_1
S001,Focus School Academy,1,7,3
S002,Focus School Academy,1,7,4
S003,Focus School Academy,1,7,2
S004,Focus School Academy,1,7,4
S005,Focus School Academy,1,7,3
S006,Focus School Academy,2,7,4
S007,Focus School Academy,2,7,3
S008,Focus School Academy,2,7,4
S009,Focus School Academy,2,7,2
S010,Focus School Academy,2,7,3
""")
        
        min_n = 5
        group_by = ["wave", "yearGroup"]
        
        is_suppressed = check_blanket_suppression(
            df=df,
            school="Focus School Academy",
            group_by=group_by,
            min_n=min_n
        )
        
        assert is_suppressed is False, "All waves safe should not suppress"

    def test_wave_aggregation_one_wave_unsafe(self):
        """When aggregating by wave and one wave has small n."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        df = _make_df("""uid,school,wave,yearGroup,bw_wbeing_1
S001,Focus School Academy,1,7,3
S002,Focus School Academy,1,7,4
S003,Focus School Academy,1,7,2
S004,Focus School Academy,1,7,4
S005,Focus School Academy,1,7,3
S006,Focus School Academy,2,7,4
S007,Focus School Academy,2,7,3
S008,Focus School Academy,2,7,4
""")
        
        min_n = 5
        group_by = ["wave", "yearGroup"]
        
        is_suppressed = check_blanket_suppression(
            df=df,
            school="Focus School Academy",
            group_by=group_by,
            min_n=min_n
        )
        
        assert is_suppressed is True, "Wave 2 with n=3 should trigger suppression"


class TestBlanketSuppressionWithClassFilter:
    """Test blanket suppression when filtering by class (focus school only)."""

    def test_class_filter_safe(self):
        """When filtering to a specific class with safe n."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        df = _make_df("""uid,school,yearGroup,class,d_sex,bw_wbeing_1
S001,Focus School Academy,7,A,M,3
S002,Focus School Academy,7,A,M,4
S003,Focus School Academy,7,A,M,2
S004,Focus School Academy,7,A,M,4
S005,Focus School Academy,7,A,M,3
S006,Focus School Academy,7,A,F,4
S007,Focus School Academy,7,A,F,3
S008,Focus School Academy,7,A,F,4
S009,Focus School Academy,7,A,F,2
S010,Focus School Academy,7,A,F,3
S011,Focus School Academy,7,B,M,1
S012,Focus School Academy,7,B,M,2
""")
        
        min_n = 5
        # Filter to class A before checking
        class_a_df = df[df["class"] == "A"]
        group_by = ["yearGroup", "d_sex"]
        
        is_suppressed = check_blanket_suppression(
            df=class_a_df,
            school="Focus School Academy",
            group_by=group_by,
            min_n=min_n
        )
        
        assert is_suppressed is False, "Class A groups are safe"

    def test_class_filter_unsafe(self):
        """When filtering to a specific class with unsafe n."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        df = _make_df("""uid,school,yearGroup,class,d_sex,bw_wbeing_1
S001,Focus School Academy,7,A,M,3
S002,Focus School Academy,7,A,M,4
S003,Focus School Academy,7,A,M,2
S004,Focus School Academy,7,A,F,4
S005,Focus School Academy,7,A,F,3
S011,Focus School Academy,7,B,M,1
S012,Focus School Academy,7,B,M,2
""")
        
        min_n = 5
        # Filter to class A before checking
        class_a_df = df[df["class"] == "A"]
        group_by = ["yearGroup", "d_sex"]
        
        is_suppressed = check_blanket_suppression(
            df=class_a_df,
            school="Focus School Academy",
            group_by=group_by,
            min_n=min_n
        )
        
        assert is_suppressed is True, "Class A with small groups should be suppressed"


# ---------------------------------------------------------------------------
# Integration Tests with Query Execution
# ---------------------------------------------------------------------------


class TestBlanketSuppressionIntegration:
    """Test blanket suppression integrated with the query execution pipeline."""

    def test_safe_query_returns_data(self, safe_cohort_df):
        """A safe query should return data normally."""
        from ib_ox_api.blanket_suppression import execute_safe_query

        query_params = {
            "school": "Focus School Academy",
            "variable": "bw_wbeing_1",
            "waves": ["1"],
            "group_by": ["yearGroup", "d_sex"],
            "filters": {},
        }
        
        result = execute_safe_query(
            df=safe_cohort_df,
            query_params=query_params,
            min_n=5
        )
        
        # Result is now wave-indexed
        assert "1" in result, "Result should contain wave '1'"
        wave_result = result["1"]
        assert wave_result["suppressed"] is False, "Safe query should not be suppressed"
        assert "data" in wave_result, "Result should contain data"
        assert len(wave_result["data"]) > 0, "Data should not be empty"

    def test_unsafe_query_returns_suppression_message(self, unsafe_cohort_df):
        """An unsafe query should return a polite suppression message."""
        from ib_ox_api.blanket_suppression import execute_safe_query

        query_params = {
            "school": "Focus School Academy",
            "variable": "bw_wbeing_1",
            "waves": ["1"],
            "group_by": ["yearGroup", "d_sex"],
            "filters": {},
        }
        
        result = execute_safe_query(
            df=unsafe_cohort_df,
            query_params=query_params,
            min_n=5
        )
        
        # Result is now wave-indexed
        assert "1" in result, "Result should contain wave '1'"
        wave_result = result["1"]
        assert wave_result["suppressed"] is True, "Unsafe query should be suppressed"
        assert "message" in wave_result, "Result should contain suppression message"
        assert "data" not in wave_result or wave_result["data"] == [], "Suppressed query should not return data"

    def test_neighbor_school_suppression_drops_from_chart(self):
        """If a neighbor school is suppressed, it should be dropped from comparison."""
        from ib_ox_api.blanket_suppression import execute_safe_query_with_neighbors

        df = _make_df("""uid,school,yearGroup,d_sex,bw_wbeing_1
S001,Focus School Academy,7,M,3
S002,Focus School Academy,7,M,4
S003,Focus School Academy,7,M,2
S004,Focus School Academy,7,M,4
S005,Focus School Academy,7,M,3
S006,Focus School Academy,7,F,4
S007,Focus School Academy,7,F,3
S008,Focus School Academy,7,F,4
S009,Focus School Academy,7,F,2
S010,Focus School Academy,7,F,3
S011,Neighbouring School,7,M,3
S012,Neighbouring School,7,M,4
S013,Neighbouring School,7,F,2
S014,State Local High,7,M,1
S015,State Local High,7,M,2
S016,State Local High,7,M,3
S017,State Local High,7,M,4
S018,State Local High,7,M,5
S019,State Local High,7,F,1
S020,State Local High,7,F,2
S021,State Local High,7,F,3
S022,State Local High,7,F,4
S023,State Local High,7,F,5
""")
        
        query_params = {
            "school": "Focus School Academy",
            "variable": "bw_wbeing_1",
            "waves": ["1"],
            "group_by": ["yearGroup", "d_sex"],
            "filters": {},
            "neighbors": ["Neighbouring School", "State Local High"],  # Neighbouring School is unsafe, State Local High is safe
        }
        
        result = execute_safe_query_with_neighbors(
            df=df,
            query_params=query_params,
            min_n=5
        )
        
        # Result is now wave-indexed
        assert "focus" in result
        assert "1" in result["focus"], "Focus result should contain wave '1'"
        focus_wave = result["focus"]["1"]
        
        # Focus School Academy should be safe
        assert focus_wave["suppressed"] is False
        assert len(focus_wave["data"]) > 0
        
        # Check neighbor schools - structure is list of {"school": name, "results": {wave: {...}}}
        neighbor_schools = [n["school"] for n in result["neighbors"]]
        
        assert "Neighbouring School" not in neighbor_schools, "Neighbouring School should be dropped due to suppression"
        
        # State Local High should be included
        assert "State Local High" in neighbor_schools, "State Local High should be included"


# ---------------------------------------------------------------------------
# Edge Cases and Error Handling
# ---------------------------------------------------------------------------


class TestBlanketSuppressionEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_dataframe(self):
        """Empty DataFrame should be treated as safe (no data to suppress)."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        df = _make_df("""uid,school,yearGroup,d_sex,bw_wbeing_1
""")
        
        is_suppressed = check_blanket_suppression(
            df=df,
            school="Focus School Academy",
            group_by=["yearGroup", "d_sex"],
            min_n=5
        )
        
        # Empty is safe (nothing to suppress)
        assert is_suppressed is False, "Empty DataFrame should be safe"

    def test_school_not_in_data(self):
        """Requesting a school not in the data should return empty/safe."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        df = _make_df("""uid,school,yearGroup,d_sex,bw_wbeing_1
S001,Focus School Academy,7,M,3
S002,Focus School Academy,7,M,4
""")
        
        is_suppressed = check_blanket_suppression(
            df=df,
            school="NonExistent",
            group_by=["yearGroup", "d_sex"],
            min_n=5
        )
        
        assert is_suppressed is False, "Non-existent school should be safe"

    def test_min_n_zero_always_safe(self):
        """MIN_N=0 should make everything safe (no suppression)."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        df = _make_df("""uid,school,yearGroup,d_sex,bw_wbeing_1
S001,Focus School Academy,7,M,3
""")
        
        is_suppressed = check_blanket_suppression(
            df=df,
            school="Focus School Academy",
            group_by=["yearGroup", "d_sex"],
            min_n=0  # No suppression threshold
        )
        
        assert is_suppressed is False, "MIN_N=0 should disable suppression"

    def test_min_n_one_only_suppresses_zero(self):
        """MIN_N=1 should only suppress n=0 (but we treat n=0 as safe)."""
        from ib_ox_api.blanket_suppression import check_blanket_suppression

        df = _make_df("""uid,school,yearGroup,d_sex,bw_wbeing_1
S001,Focus School Academy,7,M,3
""")
        
        is_suppressed = check_blanket_suppression(
            df=df,
            school="Focus School Academy",
            group_by=["yearGroup", "d_sex"],
            min_n=1
        )
        
        # n=1 should be safe when MIN_N=1
        assert is_suppressed is False, "Single student safe with MIN_N=1"
