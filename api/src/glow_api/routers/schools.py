from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from glow_api.auth import get_current_user
from glow_api.dashboard_query_options import build_query_options
from glow_api.data import DataStore, get_datastore
from glow_api.database import get_db, list_schools
from glow_api.models import SchoolListResponse, SchoolRead, UserRead

router = APIRouter(prefix="/schools", tags=["schools"])


@router.get("", response_model=SchoolListResponse)
def get_schools(
    current_user: UserRead = Depends(get_current_user),
    db: Session = Depends(get_db),
    datastore: DataStore = Depends(get_datastore),
) -> list[SchoolRead]:
    """
    List all schools the user can access with query options.
    Admins can access all schools, regular users can only access their assigned schools.
    Query options are scoped to each school's data.
    """
    all_schools = list_schools(db)
    dfwl = datastore.to_frozen()

    # If user is admin, return all schools
    if current_user.is_admin:
        return [
            SchoolRead(
                id=s.id,
                name=s.name,
                size=s.size,
                category=s.category,
                geographical_neighbor_ids=[n.id for n in s.geographical_neighbors],
                statistical_neighbor_ids=[n.id for n in s.statistical_neighbors],
                query_options=build_query_options(dfwl, s.name),
            )
            for s in all_schools
        ]

    # Otherwise, filter to only schools the user has access to
    user_school_ids = set(current_user.school_ids)
    accessible_schools = [s for s in all_schools if s.id in user_school_ids]

    return [
        SchoolRead(
            id=s.id,
            name=s.name,
            size=s.size,
            category=s.category,
            geographical_neighbor_ids=[n.id for n in s.geographical_neighbors],
            statistical_neighbor_ids=[n.id for n in s.statistical_neighbors],
            query_options=build_query_options(dfwl, s.name),
        )
        for s in accessible_schools
    ]
