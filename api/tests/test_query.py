import pytest
from fastapi import status

from ib_ox_api.models import QueryResult
from ib_ox_api.query_examples import (
    DOCS_PATH,
    MIN_N_FOR_DOCS,
    assert_example_result,
    query_examples,
    render_examples_markdown,
)


def test_query_catalog_returns_scoped_dimensions_and_suggestions(client):
    response = client.get("/query/catalog")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "school" in data["dimensions"]
    assert "bw_wbeing_1" in data["measures"]
    assert "bw_wbeing_total" in data["scores"]
    assert data["waves"] == ["1", "2"]
    assert "Alpha" in data["value_suggestions"]["school"]


@pytest.mark.parametrize("example", query_examples(), ids=lambda example: example.slug)
def test_query_examples_execute_and_match_expected_results(client, example):
    response = client.post("/query", json=example.plan.model_dump(mode="json"))
    assert response.status_code == status.HTTP_200_OK
    result = response.json()
    assert_example_result(example, QueryResult.model_validate(result))
    assert "csv" in result
    assert "count_csv" in result
    assert "suppressions" in result
    assert "provenance" in result


def test_query_docs_are_generated_from_the_example_suite(sample_df):
    if not DOCS_PATH.exists():
        pytest.skip("Checked-in query docs are not available in this test environment.")
    rendered = render_examples_markdown(sample_df, min_n=MIN_N_FOR_DOCS)
    assert DOCS_PATH.read_text() == rendered


def test_query_rejects_unsafe_identifier_filters_even_when_buried(client):
    payload = {
        "steps": [
            {"type": "derive_score", "score": "bw_wbeing_total"},
            {
                "type": "pair_waves",
                "from_wave": "1",
                "to_wave": "2",
                "measures": ["bw_wbeing_total"],
            },
            {"type": "filter", "column": "uid", "op": "eq", "value": "S001"},
            {
                "type": "aggregate",
                "group_by": ["school"],
                "metrics": [{"kind": "count_students"}],
            },
        ]
    }
    response = client.post("/query", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "uid" in response.json()["detail"]


def test_query_rejects_unsafe_grouping_even_when_buried(client):
    payload = {
        "steps": [
            {"type": "derive_score", "score": "bw_wbeing_total"},
            {
                "type": "pair_waves",
                "from_wave": "1",
                "to_wave": "2",
                "measures": ["bw_wbeing_total"],
            },
            {
                "type": "filter",
                "column": "baseline_bw_wbeing_total",
                "op": "gte",
                "value": 3,
            },
            {
                "type": "aggregate",
                "group_by": ["uid"],
                "metrics": [{"kind": "count_students"}],
            },
        ]
    }
    response = client.post("/query", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "uid" in response.json()["detail"]


def test_legacy_query_routes_are_removed(client):
    for path in ("/query/v2", "/query/v2/catalog", "/query/frequency", "/query/means", "/query/wave-change"):
        response = client.post(path, json={"steps": []}) if path != "/query/v2/catalog" else client.get(path)
        assert response.status_code == status.HTTP_404_NOT_FOUND
