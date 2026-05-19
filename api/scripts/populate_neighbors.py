#!/usr/bin/env python3
"""
Script to pre-populate geographical and statistical neighbors for schools.

This script ensures that every school has at least 2 geographical neighbors
and at least 2 statistical neighbors. Neighbors may overlap between the two types.

Run this script after creating schools in the database:
    python scripts/populate_neighbors.py
"""

import random
import sys
from pathlib import Path

# Add parent directory to path so we can import ib_ox_api
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ib_ox_api.database import (
    SessionLocal,
    list_schools,
    set_geographical_neighbors,
    set_statistical_neighbors,
)


def populate_neighbors(min_geographical: int = 2, min_statistical: int = 2) -> None:
    """
    Populate neighbor relationships for all schools.
    
    For each school:
    - Assign at least min_geographical geographical neighbors
    - Assign at least min_statistical statistical neighbors
    - Neighbors may overlap between types
    - Relationships are reciprocal
    
    Args:
        min_geographical: Minimum number of geographical neighbors per school
        min_statistical: Minimum number of statistical neighbors per school
    """
    db = SessionLocal()
    try:
        schools = list_schools(db)
        
        if len(schools) < 3:
            print(f"Warning: Only {len(schools)} schools found. Need at least 3 to create meaningful neighbor relationships.")
            if len(schools) < 2:
                print("Error: Need at least 2 schools to create neighbor relationships.")
                return
        
        print(f"Found {len(schools)} schools")
        print(f"Ensuring each school has at least {min_geographical} geographical and {min_statistical} statistical neighbors")
        
        for school in schools:
            # Get all other schools (potential neighbors)
            potential_neighbors = [s for s in schools if s.id != school.id]
            
            if len(potential_neighbors) == 0:
                print(f"  {school.name}: No other schools available")
                continue
            
            # Determine how many neighbors to assign
            # Use minimum required, or fewer if not enough schools exist
            num_geo = min(min_geographical, len(potential_neighbors))
            num_stat = min(min_statistical, len(potential_neighbors))
            
            # Check current neighbor counts
            current_geo_count = len(school.geographical_neighbors)
            current_stat_count = len(school.statistical_neighbors)
            
            geo_neighbors_to_add = []
            stat_neighbors_to_add = []
            
            # Add geographical neighbors if needed
            if current_geo_count < num_geo:
                # Get IDs of current geographical neighbors
                current_geo_ids = {n.id for n in school.geographical_neighbors}
                # Select additional neighbors
                available = [s for s in potential_neighbors if s.id not in current_geo_ids]
                needed = num_geo - current_geo_count
                if needed > 0 and available:
                    new_neighbors = random.sample(available, min(needed, len(available)))
                    geo_neighbors_to_add = [n.id for n in new_neighbors]
            
            # Add statistical neighbors if needed
            if current_stat_count < num_stat:
                # Get IDs of current statistical neighbors
                current_stat_ids = {n.id for n in school.statistical_neighbors}
                # Select additional neighbors (may overlap with geographical)
                available = [s for s in potential_neighbors if s.id not in current_stat_ids]
                needed = num_stat - current_stat_count
                if needed > 0 and available:
                    new_neighbors = random.sample(available, min(needed, len(available)))
                    stat_neighbors_to_add = [n.id for n in new_neighbors]
            
            # Update geographical neighbors
            if geo_neighbors_to_add:
                all_geo_ids = [n.id for n in school.geographical_neighbors] + geo_neighbors_to_add
                set_geographical_neighbors(db, school, all_geo_ids)
                print(f"  {school.name}: Added {len(geo_neighbors_to_add)} geographical neighbors")
            elif current_geo_count >= num_geo:
                print(f"  {school.name}: Already has {current_geo_count} geographical neighbors")
            
            # Update statistical neighbors
            if stat_neighbors_to_add:
                all_stat_ids = [n.id for n in school.statistical_neighbors] + stat_neighbors_to_add
                set_statistical_neighbors(db, school, all_stat_ids)
                print(f"  {school.name}: Added {len(stat_neighbors_to_add)} statistical neighbors")
            elif current_stat_count >= num_stat:
                print(f"  {school.name}: Already has {current_stat_count} statistical neighbors")
        
        # Verify results
        print("\nVerification:")
        schools = list_schools(db)  # Re-fetch to get updated relationships
        for school in schools:
            geo_count = len(school.geographical_neighbors)
            stat_count = len(school.statistical_neighbors)
            overlap = len(set(n.id for n in school.geographical_neighbors) & 
                         set(n.id for n in school.statistical_neighbors))
            print(f"  {school.name}: {geo_count} geographical, {stat_count} statistical ({overlap} overlap)")
            
            if geo_count < min_geographical:
                print(f"    WARNING: Only {geo_count} geographical neighbors (minimum {min_geographical})")
            if stat_count < min_statistical:
                print(f"    WARNING: Only {stat_count} statistical neighbors (minimum {min_statistical})")
        
        print("\nNeighbor population completed successfully!")
        
    finally:
        db.close()


if __name__ == "__main__":
    populate_neighbors()
