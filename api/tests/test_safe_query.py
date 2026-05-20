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


class TestQueryEndpoint:
    """Test the /query endpoint with blanket suppression."""

    def test_query_requires_authentication(self, auth_client):
        """Unauthenticated requests should be rejected."""
        response = auth_client.post(
            "/query",
            json={
                "school_id": 1,
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": [],
                "filters": {},
            },
        )
        assert response.status_code == 401

    def test_query_simple_mean(self, auth_client, alpha_user, login_as_user):
        """Query mean of a question variable for a school."""
        token = login_as_user(alpha_user["username"])
        
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": [],
                "filters": {},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        if response.status_code != 200:
            print(f"Error response: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        
        # Should have focus school data
        assert "focus_school" in data
        assert data["focus_school"]["school_id"] == alpha_user["school_id"]
        assert data["focus_school"]["school_name"] == alpha_user["school_name"]
        
        # Should have wave-indexed results
        assert "results" in data["focus_school"]
        assert isinstance(data["focus_school"]["results"], dict)
        
        # Check at least one wave has results
        for wave in ["1", "2", "3"]:
            assert wave in data["focus_school"]["results"]
            wave_result = data["focus_school"]["results"][wave]
            assert "suppressed" in wave_result
            
            # Should have results or suppression message
            if wave_result["suppressed"]:
                assert "suppression_message" in wave_result
                assert wave_result["results"] is None
            else:
                assert isinstance(wave_result["results"], list)
                assert len(wave_result["results"]) > 0
                # Should have mean and student_n
                result = wave_result["results"][0]
                assert "mean" in result
                assert "student_n" in result

    def test_query_with_year_group_aggregation(self, auth_client, alpha_user, login_as_user):
        """Query with yearGroup aggregation."""
        token = login_as_user(alpha_user["username"])
        
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": ["yearGroup"],
                "filters": {},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check wave-indexed results
        for wave in ["1", "2", "3"]:
            wave_result = data["focus_school"]["results"][wave]
            if not wave_result["suppressed"]:
                # Results should have yearGroup field
                for result in wave_result["results"]:
                    assert "yearGroup" in result
                    assert "mean" in result
                    assert "student_n" in result

    def test_query_with_wave_filter(self, auth_client, alpha_user, login_as_user):
        """Query with wave filter."""
        token = login_as_user(alpha_user["username"])
        
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": [],
                "filters": {"wave": [1]},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return valid response (suppressed or not)
        assert "focus_school" in data

    def test_query_with_class_aggregation(self, auth_client, alpha_user, login_as_user):
        """Query with class aggregation (focus school only)."""
        token = login_as_user(alpha_user["username"])
        
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": ["class"],
                "filters": {},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check wave-indexed results
        for wave in ["1", "2", "3"]:
            wave_result = data["focus_school"]["results"][wave]
            if not wave_result["suppressed"]:
                # Results should have class field
                for result in wave_result["results"]:
                    assert "class" in result
                    assert "mean" in result
                    assert "student_n" in result

    def test_query_with_neighbors(self, auth_client, alpha_user, login_as_user, db_session, sample_schools):
        """Query with neighbor schools included."""
        # Set up Focus School Academy and Neighbouring School as neighbors
        alpha_school = sample_schools["Focus School Academy"]
        beta_school = sample_schools["Neighbouring School"]
        alpha_school.geographical_neighbors.append(beta_school)
        db_session.commit()
        
        token = login_as_user(alpha_user["username"])
        
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": [],
                "filters": {},
                "include_neighbors": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have focus school
        assert "focus_school" in data
        
        # Should have neighbors list (may be empty if suppressed)
        assert "neighbors" in data
        assert isinstance(data["neighbors"], list)

    def test_query_derived_score(self, auth_client, alpha_user, login_as_user):
        """Query a derived score variable."""
        token = login_as_user(alpha_user["username"])
        
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "bw_wbeing_total",
                "waves": ["1", "2", "3"],
                "aggregations": [],
                "filters": {},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        if response.status_code != 200:
            print(f"Error response: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        
        # Should process derived score like any other variable
        assert "focus_school" in data

    def test_query_blanket_suppression_triggers(self, auth_client, alpha_user, login_as_user):
        """Verify blanket suppression is triggered for unsafe cohorts."""
        token = login_as_user(alpha_user["username"])
        
        # Query with multiple aggregations that might create small cohorts
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": ["yearGroup", "d_sex", "d_ethnicity"],
                "filters": {},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check wave-indexed results for suppression
        for wave in ["1", "2", "3"]:
            wave_result = data["focus_school"]["results"][wave]
            # If suppressed, should have message and no results
            if wave_result["suppressed"]:
                assert wave_result["suppression_message"] is not None
                assert wave_result["results"] is None

    def test_query_neighbor_suppressed_dropped(self, auth_client, alpha_user, login_as_user, db_session, sample_schools):
        """Suppressed neighbor schools should be dropped from results."""
        # Set up neighbors
        alpha_school = sample_schools["Focus School Academy"]
        beta_school = sample_schools["Neighbouring School"]
        alpha_school.geographical_neighbors.append(beta_school)
        db_session.commit()
        
        token = login_as_user(alpha_user["username"])
        
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": ["yearGroup", "d_sex"],  # May suppress Neighbouring School
                "filters": {},
                "include_neighbors": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Neighbors list should only include non-suppressed schools
        for neighbor in data["neighbors"]:
            # Each neighbor should have results (suppressed ones are dropped)
            assert neighbor["results"] is not None
            assert not neighbor.get("suppressed", False)

    def test_query_invalid_variable(self, auth_client, alpha_user, login_as_user):
        """Invalid variable should return error."""
        token = login_as_user(alpha_user["username"])
        
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "nonexistent_variable",
                "waves": ["1", "2", "3"],
                "aggregations": [],
                "filters": {},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 400
        assert "variable" in response.json()["detail"].lower()

    def test_query_invalid_aggregation(self, auth_client, alpha_user, login_as_user):
        """Invalid aggregation dimension should return error."""
        token = login_as_user(alpha_user["username"])
        
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": ["invalid_dimension"],
                "filters": {},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 400

    def test_query_user_can_only_query_own_school(self, auth_client, alpha_user, beta_user, login_as_user):
        """Non-admin user should only query their own school."""
        token = login_as_user(alpha_user["username"])
        
        # Try to query Neighbouring School school with Focus School Academy user's token
        response = auth_client.post(
            "/query",
            json={
                "school_id": beta_user["school_id"],
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": [],
                "filters": {},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 403

    def test_query_admin_can_query_any_school(self, auth_client, admin_token, alpha_user):
        """Admin user can query any school."""
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": [],
                "filters": {},
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        
        assert response.status_code == 200

    def test_query_class_aggregation_not_allowed_for_neighbors(self, auth_client, alpha_user, login_as_user):
        """Class aggregation should not be allowed when including neighbors."""
        token = login_as_user(alpha_user["username"])
        
        response = auth_client.post(
            "/query",
            json={
                "school_id": alpha_user["school_id"],
                "variable": "bw_wbeing_1",
                "waves": ["1", "2", "3"],
                "aggregations": ["class"],
                "filters": {},
                "include_neighbors": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        
        assert response.status_code == 400
        assert "class" in response.json()["detail"].lower()
