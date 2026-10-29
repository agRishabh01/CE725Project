"""Week 1 smoke tests: app boots, models importable, schemas validate."""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.db.models import (
    AgentRun,
    BOQLine,
    BuildingParams,
    CostIndex,
    Estimate,
    Organization,
    Project,
    RateEdition,
    RateItem,
    RuleSet,
    User,
    ValidationCase,
)
from api.main import app
from api.schemas.building import BuildingParams as BuildingParamsSchema


def test_health_endpoint_returns_ok():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "engine_version" in body


def test_all_twelve_entities_declared():
    """Guard against accidental removal of a PDR entity."""
    entities = {
        Organization, User, Project, BuildingParams, Estimate, BOQLine,
        RateEdition, RateItem, CostIndex, RuleSet, ValidationCase, AgentRun,
    }
    assert len(entities) == 12


def test_building_params_schema_validates_a_sensible_case():
    params = BuildingParamsSchema(
        use_type="hostel",
        plot_area_m2=1200.0,
        builtup_area_m2=3000.0,
        floors=5,
        floor_height_m=3.0,
        structural_system="rcc_framed",
        spec_level="standard",
        sbc_kpa=150.0,
        location="Mumbai",
    )
    assert params.floors == 5
    assert params.aspect_ratio == 1.5  # default


def test_building_params_rejects_impossible_builtup():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BuildingParamsSchema(
            use_type="office",
            plot_area_m2=100.0,
            builtup_area_m2=10_000.0,  # 100× the plot — bogus
            floors=2,
            floor_height_m=3.0,
            structural_system="rcc_framed",
        )
