"""Tests for dashboard query options builder and validation."""

import pytest

from glow_api.data import DataFrameWithWhitelists, DataStore
from glow_api.dashboard_query_options import build_query_options, validate_query_request
from glow_api.models import QueryOptions


@pytest.fixture
def dfwl(sample_df):
    """Create DataFrameWithWhitelists from sample data."""
    # Use DataStore to process the data and extract whitelists
    ds = DataStore.__new__(DataStore)
    df = ds._process_loaded_data(sample_df)
    return DataFrameWithWhitelists(
        df=df,
        categorical_whitelist=ds._categorical_whitelist,
        numerical_whitelist=ds._numerical_whitelist,
    )


class TestBuildQueryOptions:
    """Test build_query_options function."""

    def test_build_query_options_all_schools(self, dfwl):
        """Build query options from all schools in dataset."""
        options = build_query_options(dfwl)

        options = build_query_options(dfwl)

        # Should have variables from numerical whitelist
        assert isinstance(options.variables, list)
        assert len(options.variables) > 0
        assert "bw_wbeing_1" in options.variables
        assert "bw_wbeing_2" in options.variables
        assert "bw_wbeing_3" in options.variables
        # Should include derived totals
        assert "bw_wbeing_total" in options.variables

        # Variables should be sorted
        assert options.variables == sorted(options.variables)

        # Should have waves
        assert isinstance(options.waves, list)
        assert "1" in options.waves
        assert "2" in options.waves

        # Waves should be sorted
        assert options.waves == sorted(options.waves)

        # Should have aggregations
        assert len(options.aggregations) > 0
        agg_values = [item.value for item in options.aggregations]
        assert "yearGroup" in agg_values
        assert "d_sex" in agg_values
        assert "d_ethnicity" in agg_values
        assert "class" in agg_values

        # Aggregations should be sorted
        assert agg_values == sorted(agg_values)

        # Class should be focus_only, others should be shared
        for item in options.aggregations:
            if item.value == "class":
                assert item.scope == "focus_only"
            else:
                assert item.scope == "shared"

        # Should not include school or wave in aggregations
        assert "school" not in agg_values
        assert "wave" not in agg_values

        # Should have filters
        assert len(options.filters) > 0
        filter_values = [item.value for item in options.filters]
        assert "yearGroup" in filter_values
        assert "d_sex" in filter_values
        # wave is not included because it's handled separately in waves parameter

        # Filters should be sorted
        assert filter_values == sorted(filter_values)

        # Should not include school in filters
        assert "school" not in filter_values

        # Class filter should be focus_only
        for item in options.filters:
            if item.value == "class":
                assert item.scope == "focus_only"

        # Filters should have values
        for item in options.filters:
            assert isinstance(item.values, list)
            assert len(item.values) > 0

    def test_build_query_options_scoped_to_school(self, dfwl):
        """Build query options scoped to specific school."""

        options = build_query_options(dfwl, school_name="Focus School Academy")

        # Should still have variables (not scoped by school)
        assert "bw_wbeing_1" in options.variables

        # Should only have waves present in Focus School Academy data
        assert isinstance(options.waves, list)
        assert len(options.waves) > 0

        # Should have filters with values specific to Focus School Academy
        for item in options.filters:
            if item.value == "yearGroup":
                # Focus School Academy only has yearGroup 7
                assert "7" in item.values
                # Should not have year 8 (Neighbouring School only)
                assert "8" not in item.values

    def test_build_query_options_filter_values_limited(self, dfwl):
        """Filter values should be limited to 50 items."""

        options = build_query_options(dfwl)

        # All filter items should have at most 50 values
        for item in options.filters:
            assert len(item.values) <= 50

    def test_build_query_options_no_wave_column(self, tiny_df):
        """Handle data without wave column."""
        # Remove wave column
        df_no_wave = tiny_df.drop(columns=["wave"])

        # Process with DataStore
        ds = DataStore.__new__(DataStore)
        df = ds._process_loaded_data(df_no_wave)
        dfwl = DataFrameWithWhitelists(
            df=df,
            categorical_whitelist=ds._categorical_whitelist,
            numerical_whitelist=ds._numerical_whitelist,
        )

        options = build_query_options(dfwl)

        # Should have empty waves list
        assert options.waves == []

    def test_build_query_options_nonexistent_school(self, dfwl):
        """Build query options for nonexistent school returns empty options."""

        options = build_query_options(dfwl, school_name="Nonexistent School")

        # Should return empty options since no data matches
        # Variables are still included (from whitelist)
        assert isinstance(options.variables, list)
        # But waves should be empty
        assert options.waves == []


class TestValidateQueryRequest:
    """Test validate_query_request function."""

    def test_validate_query_request_valid_simple(self, dfwl):
        """Validate a simple valid query request."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["1", "2"],
            aggregations=[],
            filters={},
            query_options=options,
            include_neighbors=False,
        )

        assert valid is True
        assert error is None

    def test_validate_query_request_valid_with_aggregations(self, dfwl):
        """Validate query with shared aggregations."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["1"],
            aggregations=["yearGroup", "d_sex"],
            filters={},
            query_options=options,
            include_neighbors=False,
        )

        assert valid is True
        assert error is None

    def test_validate_query_request_valid_with_filters(self, dfwl):
        """Validate query with filters."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["1"],
            aggregations=[],
            filters={"d_sex": ["M", "F"]},
            query_options=options,
            include_neighbors=False,
        )

        assert valid is True
        assert error is None

    def test_validate_query_request_invalid_variable(self, dfwl):
        """Invalid variable should fail validation."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        valid, error = validate_query_request(
            variable="nonexistent_variable",
            waves=["1"],
            aggregations=[],
            filters={},
            query_options=options,
            include_neighbors=False,
        )

        assert valid is False
        assert error is not None
        assert "variable" in error.lower()
        assert "nonexistent_variable" in error

    def test_validate_query_request_invalid_wave(self, dfwl):
        """Invalid wave should fail validation."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["99"],
            aggregations=[],
            filters={},
            query_options=options,
            include_neighbors=False,
        )

        assert valid is False
        assert error is not None
        assert "wave" in error.lower()
        assert "99" in error

    def test_validate_query_request_invalid_aggregation(self, dfwl):
        """Invalid aggregation should fail validation."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["1"],
            aggregations=["invalid_dimension"],
            filters={},
            query_options=options,
            include_neighbors=False,
        )

        assert valid is False
        assert error is not None
        assert "aggregation" in error.lower()
        assert "invalid_dimension" in error

    def test_validate_query_request_invalid_filter(self, dfwl):
        """Invalid filter dimension should fail validation."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["1"],
            aggregations=[],
            filters={"invalid_dimension": ["value"]},
            query_options=options,
            include_neighbors=False,
        )

        assert valid is False
        assert error is not None
        assert "filter" in error.lower()
        assert "invalid_dimension" in error

    def test_validate_query_request_class_aggregation_focus_only(self, dfwl):
        """Class aggregation should be allowed for focus school only."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        # Should be valid without neighbors
        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["1"],
            aggregations=["class"],
            filters={},
            query_options=options,
            include_neighbors=False,
        )

        assert valid is True
        assert error is None

        # Should fail with neighbors
        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["1"],
            aggregations=["class"],
            filters={},
            query_options=options,
            include_neighbors=True,
        )

        assert valid is False
        assert error is not None
        assert "class" in error.lower()
        assert "focus school" in error.lower()

    def test_validate_query_request_class_filter_focus_only(self, dfwl):
        """Class filter should be allowed for focus school only."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        # Should be valid without neighbors
        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["1"],
            aggregations=[],
            filters={"class": ["A", "B"]},
            query_options=options,
            include_neighbors=False,
        )

        assert valid is True
        assert error is None

        # Should fail with neighbors
        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["1"],
            aggregations=[],
            filters={"class": ["A", "B"]},
            query_options=options,
            include_neighbors=True,
        )

        assert valid is False
        assert error is not None
        assert "class" in error.lower()
        assert "focus school" in error.lower()

    def test_validate_query_request_shared_aggregation_with_neighbors(self, dfwl):
        """Shared aggregations should be allowed with neighbors."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["1"],
            aggregations=["yearGroup", "d_sex"],
            filters={},
            query_options=options,
            include_neighbors=True,
        )

        assert valid is True
        assert error is None

    def test_validate_query_request_multiple_waves(self, dfwl):
        """Validate query with multiple waves."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        valid, error = validate_query_request(
            variable="bw_wbeing_1",
            waves=["1", "2"],
            aggregations=[],
            filters={},
            query_options=options,
            include_neighbors=False,
        )

        assert valid is True
        assert error is None

    def test_validate_query_request_derived_variable(self, dfwl):
        """Derived variables should be allowed."""
        options = build_query_options(dfwl, school_name="Focus School Academy")

        valid, error = validate_query_request(
            variable="bw_wbeing_total",
            waves=["1"],
            aggregations=[],
            filters={},
            query_options=options,
            include_neighbors=False,
        )

        assert valid is True
        assert error is None
