"""Three hand-authored BuildingParams for Gate 1 reproducibility snapshots.

Each case targets a different structural system and spec level:
  - case_01: G+2 residential, RCC framed, basic spec
  - case_02: G+4 hostel, RCC framed, standard spec    (the demo case used in Week 3)
  - case_03: G+1 shop-cum-residence, load-bearing, basic spec

These are stored in code so the inputs are reviewable; the frozen outputs live
in `golden/*.json` next to this file.
"""
from __future__ import annotations

GOLDEN_CASES: dict[str, dict] = {
    "case_01_g2_residential_rcc_basic": {
        "use_type": "residential",
        "plot_area_m2": 300.0,
        "builtup_area_m2": 450.0,
        "floors": 3,
        "floor_height_m": 3.0,
        "aspect_ratio": 1.3,
        "structural_system": "rcc_framed",
        "spec_level": "basic",
        "sbc_kpa": 150.0,
        "plan_shape": "rectangular",
        "location": "Delhi",
        "source": "form",
    },
    "case_02_g4_hostel_rcc_standard": {
        "use_type": "hostel",
        "plot_area_m2": 1800.0,
        "builtup_area_m2": 3000.0,
        "floors": 5,
        "floor_height_m": 3.0,
        "aspect_ratio": 1.5,
        "structural_system": "rcc_framed",
        "spec_level": "standard",
        "sbc_kpa": 150.0,
        "plan_shape": "rectangular",
        "location": "Mumbai",
        "source": "form",
    },
    "case_03_g1_shoprow_load_bearing_basic": {
        "use_type": "mixed_use",
        "plot_area_m2": 150.0,
        "builtup_area_m2": 220.0,
        "floors": 2,
        "floor_height_m": 3.0,
        "aspect_ratio": 2.0,
        "structural_system": "load_bearing",
        "spec_level": "basic",
        "sbc_kpa": 120.0,
        "plan_shape": "rectangular",
        "location": "Lucknow",
        "source": "form",
    },
}
