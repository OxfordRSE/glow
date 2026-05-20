"""Tests for the GLOW API."""

import io

import pandas as pd
from fastapi import status


def test_health(client):
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_login_valid(auth_client):
    response = auth_client.post(
        "/auth/login",
        data={"username": "testuser", "password": "testpass"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_password(auth_client):
    response = auth_client.post(
        "/auth/login",
        data={"username": "testuser", "password": "wrongpass"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_login_unknown_user(auth_client):
    response = auth_client.post(
        "/auth/login",
        data={"username": "nobody", "password": "pass"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_columns(client):
    response = client.get("/data/columns")
    assert response.status_code == status.HTTP_200_OK
    cols = response.json()
    assert "uid" not in cols
    assert "school" in cols
    assert "bw_wbeing_1" in cols


def test_get_columns(client):
    response = client.get("/data/describe")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "variables" in data
    assert len(data["variables"]) == 5
    assert "bw_wbeing_1" in data["variables"]
    assert "bw_wbeing_total" in data["variables"]
    assert "aggregation_options" in data
    assert len(data["aggregation_options"]) == 4
    assert "class" in data["aggregation_options"]
    assert "school" not in data["aggregation_options"]
    assert "filter_options" in data
    assert len(data["filter_options"]) == 4
    assert "value" in data["filter_options"][0]
    assert "values" in data["filter_options"][0]


def test_suppression_count_students(sample_df):
    from glow_api.suppression import count_students

    assert count_students(sample_df) == 10


def test_suppression_count_students_no_uid():
    from glow_api.suppression import count_students

    no_uid_df = pd.DataFrame({"school": ["A", "B", "C"], "score": [1, 2, 3]})
    assert count_students(no_uid_df) == 3


def test_suppression_frequency_no_group_by_above_min_n(sample_df):
    from glow_api.suppression import suppress_frequency_table

    result_df, suppressions = suppress_frequency_table(
        sample_df, group_cols=[], value_col=None, min_n=5
    )
    assert len(result_df) == 1
    assert "n" in result_df.columns
    assert result_df["n"].iloc[0] == 10
    assert suppressions == {}


def test_suppression_frequency_no_group_by_below_min_n(tiny_df):
    from glow_api.suppression import suppress_frequency_table

    result_df, suppressions = suppress_frequency_table(
        tiny_df, group_cols=[], value_col=None, min_n=5
    )
    assert result_df["n"].isna().all()
    assert "n" in suppressions


def test_suppression_frequency_below_min_n(tiny_df):
    from glow_api.suppression import suppress_frequency_table

    result_df, suppressions = suppress_frequency_table(
        tiny_df, group_cols=["school"], value_col=None, min_n=5
    )
    assert result_df["n"].isna().all()
    assert "n" in suppressions


def test_suppression_frequency_above_min_n(sample_df):
    from glow_api.suppression import suppress_frequency_table

    alpha_df = sample_df[sample_df["school"] == "Focus School Academy"]
    result_df, suppressions = suppress_frequency_table(
        alpha_df, group_cols=["wave"], value_col=None, min_n=3
    )
    assert not result_df["n"].isna().all()
    assert suppressions == {}


def test_suppression_means_below_min_n(tiny_df):
    from glow_api.suppression import suppress_means_table

    means_df, _, suppressions = suppress_means_table(
        tiny_df, group_cols=["school"], value_cols=["bw_wbeing_1"], min_n=5
    )
    assert means_df["bw_wbeing_1"].isna().all()
    assert "bw_wbeing_1" in suppressions


def test_suppression_means_above_min_n(sample_df):
    from glow_api.suppression import suppress_means_table

    means_df, _, suppressions = suppress_means_table(
        sample_df, group_cols=["school"], value_cols=["bw_wbeing_1"], min_n=3
    )
    assert not means_df["bw_wbeing_1"].isna().all()
    assert suppressions == {}


def test_user_scope_applied(sample_df):
    from glow_api.models import UserScope
    from glow_api.query_utils import apply_user_scope

    scope = UserScope(filters={"school": ["Focus School Academy"]})
    filtered = apply_user_scope(sample_df, scope)
    assert set(filtered["school"].unique()) == {"Focus School Academy"}


def test_admin_list_users(admin_client):
    response = admin_client.get("/admin/users")
    assert response.status_code == status.HTTP_200_OK
    users = response.json()
    assert len(users) == 1
    assert users[0]["username"] == "adminuser"
    assert users[0]["is_admin"] is True


def test_admin_create_user(admin_client, sample_schools):
    # Get school ID for Focus School Academy
    alpha_id = sample_schools["Focus School Academy"].id
    
    payload = {
        "username": "analyst",
        "password": "analyst-pass",
        "school_ids": [alpha_id],
        "is_admin": False,
    }
    response = admin_client.post("/admin/users", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    user = response.json()
    assert user["username"] == "analyst"
    assert alpha_id in user["school_ids"]
    assert "Focus School Academy" in user["school_names"]


def test_admin_update_user(admin_client, sample_schools):
    # Get school IDs
    alpha_id = sample_schools["Focus School Academy"].id
    beta_id = sample_schools["Neighbouring School"].id
    
    create_response = admin_client.post(
        "/admin/users",
        json={
            "username": "analyst",
            "password": "analyst-pass",
            "school_ids": [alpha_id],
            "is_admin": False,
        },
    )
    user_id = create_response.json()["id"]

    response = admin_client.put(
        f"/admin/users/{user_id}",
        json={
            "school_ids": [beta_id],
            "is_active": False,
            "is_admin": True,
        },
    )
    assert response.status_code == status.HTTP_200_OK
    updated = response.json()
    assert beta_id in updated["school_ids"]
    assert "Neighbouring School" in updated["school_names"]
    assert updated["is_active"] is False
    assert updated["is_admin"] is True


def test_admin_delete_user(admin_client, sample_schools):
    alpha_id = sample_schools["Focus School Academy"].id
    
    create_response = admin_client.post(
        "/admin/users",
        json={
            "username": "analyst",
            "password": "analyst-pass",
            "school_ids": [alpha_id],
            "is_admin": False,
        },
    )
    user_id = create_response.json()["id"]

    response = admin_client.delete(f"/admin/users/{user_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    list_response = admin_client.get("/admin/users")
    usernames = [user["username"] for user in list_response.json()]
    assert "analyst" not in usernames


def test_admin_me_endpoint(admin_client):
    response = admin_client.get("/admin/me")
    assert response.status_code == status.HTTP_200_OK
    user = response.json()
    assert user["username"] == "adminuser"
    assert user["is_admin"] is True


def test_docs_example_fixture_is_parseable(sample_df):
    df = pd.read_csv(io.StringIO(sample_df.to_csv(index=False)))
    assert not df.empty
