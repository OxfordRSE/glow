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


def test_schools_list_for_user(client, sample_schools):
    """Regular user should see their assigned schools with query options."""
    response = client.get("/schools")
    assert response.status_code == status.HTTP_200_OK
    schools = response.json()

    # Should only see Focus School Academy (sample_user has access to this school)
    assert len(schools) == 1
    school = schools[0]
    assert school["name"] == "Focus School Academy"
    assert school["id"] == sample_schools["Focus School Academy"].id

    # Should include query_options
    assert "query_options" in school
    query_options = school["query_options"]

    # Query options should have all required fields
    assert "variables" in query_options
    assert "waves" in query_options
    assert "aggregations" in query_options
    assert "filters" in query_options

    # Variables should include wellbeing questions
    assert "bw_wbeing_1" in query_options["variables"]

    # Aggregations should include yearGroup, sex, etc.
    agg_values = [item["value"] for item in query_options["aggregations"]]
    assert "yearGroup" in agg_values
    assert "d_sex" in agg_values

    # Class should be focus_only
    class_agg = next(
        (item for item in query_options["aggregations"] if item["value"] == "class"),
        None,
    )
    assert class_agg is not None
    assert class_agg["scope"] == "focus_only"

    # Filters should have values
    for filter_item in query_options["filters"]:
        assert "value" in filter_item
        assert "values" in filter_item
        assert isinstance(filter_item["values"], list)
        assert len(filter_item["values"]) > 0


def test_schools_list_for_admin(admin_client, sample_schools):
    """Admin should see all schools with query options."""
    response = admin_client.get("/schools")
    assert response.status_code == status.HTTP_200_OK
    schools = response.json()

    # Should see all schools
    assert len(schools) == 2
    school_names = {s["name"] for s in schools}
    assert "Focus School Academy" in school_names
    assert "Neighbouring School" in school_names

    # All schools should have query_options
    for school in schools:
        assert "query_options" in school
        assert "variables" in school["query_options"]
        assert "waves" in school["query_options"]


def test_schools_list_query_options_scoped_to_school(client, sample_schools):
    """Query options should be scoped to each school's data."""
    response = client.get("/schools")
    assert response.status_code == status.HTTP_200_OK
    schools = response.json()

    # Get Focus School Academy
    alpha_school = next(s for s in schools if s["name"] == "Focus School Academy")

    # Check yearGroup filter values
    year_filter = next(
        (
            item
            for item in alpha_school["query_options"]["filters"]
            if item["value"] == "yearGroup"
        ),
        None,
    )
    assert year_filter is not None
    # Focus School Academy should only have year 7
    assert "7" in year_filter["values"]
    # Should not have year 8 (that's Neighbouring School)
    assert "8" not in year_filter["values"]


def test_schools_list_requires_authentication(auth_client):
    """Unauthenticated requests should be rejected."""
    response = auth_client.get("/schools")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_schools_include_neighbor_ids(client, db_session, sample_schools):
    """Schools should include geographical and statistical neighbor IDs."""
    # Set up neighbors
    alpha = sample_schools["Focus School Academy"]
    beta = sample_schools["Neighbouring School"]
    alpha.geographical_neighbors.append(beta)
    db_session.commit()

    response = client.get("/schools")
    assert response.status_code == status.HTTP_200_OK
    schools = response.json()

    alpha_school = next(s for s in schools if s["name"] == "Focus School Academy")
    assert beta.id in alpha_school["geographical_neighbor_ids"]
