"""Deterministic quantity take-off across 9 elements.

Produces ~55 BOQ lines per estimate. Each line is a `QuantityLine` carrying a
FormulaTrace so the UI can show the derivation. Rates are NOT applied here —
that's `pricing.price_boq`.

Element taxonomy (matches PDR §Estimation engine):
  1. substructure       7 items
  2. frame             10 items (RCC + steel + formwork)
  3. masonry            3 items
  4. finishes          10 items
  5. doors_windows      5 items
  6. waterproofing      2 items
  7. services           4 items
  8. external_works     4 items
  9. miscellaneous      4 items
                       --
                       49-ish, +conditional (lift, grills) → 50-55

Deductions baked in per PDR §Pipeline step 4:
  - Openings on brickwork (12% of wall area)
  - Backfill = 70% of excavation
  - Wet-area deduction on flooring (9% of floor area)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .geometry import ColumnGrid, FloorPlate, column_grid, floor_plate
from .sizing import (
    BeamSize,
    ColumnSize,
    FootingSize,
    SlabSize,
    beam_size,
    column_size,
    footing_size,
    slab_size,
)
from .trace import FormulaTrace

# -------------------------------------------------------------- opening deductions
OPENING_DEDUCTION_WALL = 0.12         # 12% off wall area (doors+windows aggregate)
BACKFILL_RATIO = 0.70
WET_AREA_FLOOR_DEDUCTION = 0.09
INTERNAL_WALL_FACTOR = 1.6            # internal wall length ≈ 1.6 × external perimeter
PARAPET_HEIGHT_M = 1.0
PLINTH_HEIGHT_M = 0.6
INTERNAL_WALL_THICKNESS_M = 0.115     # 115 mm partition


# ----------------------------------------------------------------- line types
@dataclass(frozen=True, slots=True)
class QuantityLine:
    element: str
    seq: int
    description: str
    unit: str
    qty: float
    rate_code: str
    fallback_rate_inr: float | None = None   # from spec, when DSR mapping unknown
    trace: FormulaTrace | None = None


@dataclass(frozen=True, slots=True)
class TakeoffContext:
    """Pre-computed geometry + sizing shared across element take-offs."""

    params: dict[str, Any]
    rules: dict[str, Any]
    spec: dict[str, Any]
    plate: FloorPlate
    grid: ColumnGrid
    col_size: ColumnSize
    beam_size: BeamSize
    slab_size: SlabSize
    footing_size: FootingSize


def build_context(params: dict[str, Any], rules: dict[str, Any], spec: dict[str, Any]) -> TakeoffContext:
    plate, _ = floor_plate(
        builtup_area_m2=params["builtup_area_m2"],
        floors=params["floors"],
        aspect_ratio=params.get("aspect_ratio", 1.5),
    )
    grid, _ = column_grid(plate, rules)
    col, _ = column_size(params["floors"], rules)
    bm, _ = beam_size(span_m=max(grid.span_long_m, grid.span_short_m), rules=rules)
    sl, _ = slab_size(span_m=min(grid.span_long_m, grid.span_short_m), rules=rules)
    ft, _ = footing_size(
        floors=params["floors"],
        plate=plate,
        grid=grid,
        sbc_kpa=params.get("sbc_kpa", 150.0),
        rules=rules,
    )
    return TakeoffContext(params, rules, spec, plate, grid, col, bm, sl, ft)


# ================================================================= substructure
def takeoff_substructure(ctx: TakeoffContext) -> list[QuantityLine]:
    plate, grid, ft = ctx.plate, ctx.grid, ctx.footing_size
    num_cols = grid.columns_per_floor
    foot_depth_m = ft.depth_mm / 1000.0
    pcc_t = ft.pcc_thickness_mm / 1000.0

    exc_qty = num_cols * (ft.side_m + 0.3) ** 2 * (foot_depth_m + pcc_t + 0.15)
    pcc_qty = num_cols * (ft.side_m + 0.1) ** 2 * pcc_t
    footing_rcc = num_cols * ft.side_m * ft.side_m * foot_depth_m
    steel = footing_rcc * ctx.rules["consumption"]["steel_kg_per_m3"]["footing"]
    formwork = num_cols * 4 * ft.side_m * foot_depth_m
    backfill = exc_qty * BACKFILL_RATIO
    antitermite = plate.area_m2
    dpc = plate.perimeter_m * 0.230       # 230 mm wide DPC strip

    lines = [
        _line(
            "substructure", 1,
            "Earthwork in excavation for foundations, in ordinary soil, including dressing",
            "m3", exc_qty, "EARTH_EXC_ORDINARY", 320.0,
            "n*(s+0.3)^2*(d+pcc+0.15)",
            {"n_cols": num_cols, "side_m": ft.side_m, "depth_m": foot_depth_m, "pcc_m": pcc_t},
        ),
        _line(
            "substructure", 2,
            "Plain cement concrete 1:4:8 under footings, 100 mm thick",
            "m3", pcc_qty, "PCC_1_4_8", 5200.0,
            "n*(s+0.1)^2*pcc_t",
            {"n_cols": num_cols, "pcc_t": pcc_t},
        ),
        _line(
            "substructure", 3,
            "Reinforced cement concrete M20 in isolated footings, including shuttering",
            "m3", footing_rcc, "RCC_M20_FOOTING", 7200.0,
            "n * s^2 * d",
            {"n_cols": num_cols, "s": ft.side_m, "d": foot_depth_m},
        ),
        _line(
            "substructure", 4,
            "Fe 500 reinforcement steel in footings — supply, cut, bend, place",
            "kg", steel, "STEEL_FE500_FOOTING", 85.0,
            "rcc_vol * steel_kg_per_m3",
            {"rcc_vol": round(footing_rcc, 2),
             "steel_kg_per_m3": ctx.rules["consumption"]["steel_kg_per_m3"]["footing"]},
        ),
        _line(
            "substructure", 5,
            "Formwork (shuttering) for footings — supply, erect, strike",
            "m2", formwork, "FORMWORK_FOOTING", 420.0,
            "n * 4 * side * depth",
            {"n_cols": num_cols, "side": ft.side_m, "depth": foot_depth_m},
        ),
        _line(
            "substructure", 6,
            "Earth filling in plinth and around foundations (backfill)",
            "m3", backfill, "BACKFILL", 180.0,
            "excavation * 0.7",
            {"excavation": round(exc_qty, 2)},
        ),
        _line(
            "substructure", 7,
            "Anti-termite chemical treatment to plinth area",
            "m2", antitermite, "ANTITERMITE", 110.0,
            "plate_area",
            {"plate_area": round(plate.area_m2, 2)},
        ),
        _line(
            "substructure", 8,
            "Damp-proof course (DPC) at plinth level, 20 mm thick CM 1:3 with waterproof compound",
            "m2", dpc, "DPC", 290.0,
            "perimeter * 0.230",
            {"perimeter": round(plate.perimeter_m, 2)},
        ),
    ]
    return lines


# ================================================================= frame
def takeoff_frame(ctx: TakeoffContext) -> list[QuantityLine]:
    p, g, col, bm, sl = ctx.plate, ctx.grid, ctx.col_size, ctx.beam_size, ctx.slab_size
    floors = ctx.params["floors"]
    H = float(ctx.params["floor_height_m"])
    cons = ctx.rules["consumption"]

    col_vol = col.area_m2 * H * g.columns_per_floor * floors
    # Beam total length per floor: (bays_long+1) short-direction beams + (bays_short+1) long-direction.
    # Simplified: 2 * (L + B) + inner beams on gridlines.
    beam_length_per_floor = (g.bays_long + 1) * p.breadth_m + (g.bays_short + 1) * p.length_m
    beam_vol = beam_length_per_floor * bm.area_m2 * floors
    slab_vol = p.area_m2 * (sl.thickness_mm / 1000.0) * floors
    staircase_vol = slab_vol * 0.015  # ~1.5% of slab volume, concept estimate

    col_steel = col_vol * cons["steel_kg_per_m3"]["column"]
    beam_steel = beam_vol * cons["steel_kg_per_m3"]["beam"]
    slab_steel = slab_vol * cons["steel_kg_per_m3"]["slab"]

    col_formwork = (
        2 * (col.b_mm + col.d_mm) / 1000.0 * H * g.columns_per_floor * floors
    )  # perimeter × height
    beam_formwork = (
        beam_length_per_floor * (2 * bm.depth_mm / 1000.0 + bm.width_mm / 1000.0) * floors
    )  # 2 sides + bottom
    slab_formwork = p.area_m2 * floors

    lines = [
        _line("frame", 1,
              "RCC M25 in columns, including vibrating and curing",
              "m3", col_vol, "RCC_M25_COLUMN", 8900.0,
              "col_area * H * n_cols * N",
              {"col_area_m2": round(col.area_m2, 4), "H": H,
               "n_cols": g.columns_per_floor, "N": floors}),
        _line("frame", 2,
              "RCC M25 in beams (plinth, floor, roof) incl. vibrating and curing",
              "m3", beam_vol, "RCC_M25_BEAM", 8500.0,
              "beam_len_per_floor * beam_area * N",
              {"beam_len_m_per_floor": round(beam_length_per_floor, 2),
               "beam_area_m2": round(bm.area_m2, 4), "N": floors}),
        _line("frame", 3,
              "RCC M25 in slabs (floor + roof), including vibrating and curing",
              "m3", slab_vol, "RCC_M25_SLAB", 8200.0,
              "plate_area * t * N",
              {"plate_area_m2": round(p.area_m2, 2),
               "slab_t_mm": sl.thickness_mm, "N": floors}),
        _line("frame", 4,
              "RCC M25 in staircase waist slab, treads and landings",
              "m3", staircase_vol, "RCC_M25_STAIR", 9400.0,
              "slab_vol * 0.015",
              {"slab_vol_m3": round(slab_vol, 2)}),
        _line("frame", 5,
              "Fe 500 steel reinforcement in columns",
              "kg", col_steel, "STEEL_FE500_COLUMN", 85.0,
              "col_vol * kg_per_m3",
              {"col_vol_m3": round(col_vol, 2),
               "kg_per_m3": cons["steel_kg_per_m3"]["column"]}),
        _line("frame", 6,
              "Fe 500 steel reinforcement in beams",
              "kg", beam_steel, "STEEL_FE500_BEAM", 85.0,
              "beam_vol * kg_per_m3",
              {"beam_vol_m3": round(beam_vol, 2),
               "kg_per_m3": cons["steel_kg_per_m3"]["beam"]}),
        _line("frame", 7,
              "Fe 500 steel reinforcement in slabs (incl. staircase)",
              "kg", slab_steel, "STEEL_FE500_SLAB", 85.0,
              "slab_vol * kg_per_m3",
              {"slab_vol_m3": round(slab_vol, 2),
               "kg_per_m3": cons["steel_kg_per_m3"]["slab"]}),
        _line("frame", 8,
              "Formwork (shuttering) for columns",
              "m2", col_formwork, "FORMWORK_COLUMN", 540.0,
              "perim * H * n * N",
              {"col_perim_m": round(2 * (col.b_mm + col.d_mm) / 1000.0, 3),
               "H": H, "n_cols": g.columns_per_floor, "N": floors}),
        _line("frame", 9,
              "Formwork for beams (sides + soffit)",
              "m2", beam_formwork, "FORMWORK_BEAM", 480.0,
              "beam_len * (2*depth + width) * N",
              {"beam_len_m_per_floor": round(beam_length_per_floor, 2),
               "depth_mm": bm.depth_mm, "width_mm": bm.width_mm, "N": floors}),
        _line("frame", 10,
              "Formwork for slabs (soffit)",
              "m2", slab_formwork, "FORMWORK_SLAB", 460.0,
              "plate_area * N",
              {"plate_area_m2": round(p.area_m2, 2), "N": floors}),
    ]
    return lines


# ================================================================= masonry
def takeoff_masonry(ctx: TakeoffContext) -> list[QuantityLine]:
    p = ctx.plate
    floors = ctx.params["floors"]
    H = float(ctx.params["floor_height_m"])
    external_t_m = 0.230  # default external thickness; load-bearing varies but acceptable approx
    gross_ext_wall_area = p.perimeter_m * H * floors
    net_ext_wall_area = gross_ext_wall_area * (1 - OPENING_DEDUCTION_WALL)
    ext_wall_vol = net_ext_wall_area * external_t_m

    internal_wall_length_per_floor = p.perimeter_m * INTERNAL_WALL_FACTOR
    gross_int_wall_area = internal_wall_length_per_floor * H * floors
    net_int_wall_area = gross_int_wall_area * (1 - OPENING_DEDUCTION_WALL)
    int_wall_vol = net_int_wall_area * INTERNAL_WALL_THICKNESS_M

    parapet_vol = p.perimeter_m * PARAPET_HEIGHT_M * external_t_m

    lines = [
        _line("masonry", 1,
              "Brickwork in external walls with 1st class brick in CM 1:6, 230 mm thick",
              "m3", ext_wall_vol, "BRICK_EXT_230", 7800.0,
              "perim * H * N * (1-dedn) * t",
              {"perim_m": round(p.perimeter_m, 2), "H": H, "N": floors,
               "dedn": OPENING_DEDUCTION_WALL, "t_m": external_t_m}),
        _line("masonry", 2,
              "Brickwork / AAC block in internal partitions, 115 mm thick",
              "m3", int_wall_vol, "BRICK_INT_115", 7400.0,
              "int_perim * H * N * (1-dedn) * t",
              {"int_perim_m": round(internal_wall_length_per_floor, 2),
               "H": H, "N": floors,
               "dedn": OPENING_DEDUCTION_WALL, "t_m": INTERNAL_WALL_THICKNESS_M}),
        _line("masonry", 3,
              "Parapet wall at terrace, 230 mm thick, 1.0 m high",
              "m3", parapet_vol, "BRICK_PARAPET", 7900.0,
              "perim * parapet_h * t",
              {"perim_m": round(p.perimeter_m, 2),
               "parapet_h": PARAPET_HEIGHT_M, "t_m": external_t_m}),
    ]
    return lines


# ================================================================= finishes
def takeoff_finishes(ctx: TakeoffContext) -> list[QuantityLine]:
    p = ctx.plate
    s = ctx.spec
    floors = ctx.params["floors"]
    H = float(ctx.params["floor_height_m"])

    # Wall areas (both faces of internal walls count toward internal plaster/paint).
    external_wall_face_area = p.perimeter_m * H * floors * (1 - OPENING_DEDUCTION_WALL)
    internal_wall_face_area = (
        p.perimeter_m * INTERNAL_WALL_FACTOR * H * floors * 2 * (1 - OPENING_DEDUCTION_WALL)
    )
    # Internal plaster covers internal walls (both faces) + internal face of external walls.
    internal_plaster_area = internal_wall_face_area + external_wall_face_area
    ceiling_area = p.area_m2 * floors
    skirting_length = p.perimeter_m * INTERNAL_WALL_FACTOR * floors * 0.85

    toilets = _toilet_count(ctx)
    dado_area = toilets * s["dado"]["height_m"] * 10.0   # ~5 m perimeter per toilet × dado_h × 2 faces trimmed to 10
    wet_area = toilets * 5.0                              # m² per toilet
    floor_tile_area = ceiling_area * (1 - WET_AREA_FLOOR_DEDUCTION) - wet_area

    lines = [
        _line("finishes", 1,
              f"Internal plaster CM 1:4, {s['internal_plaster']['thickness_mm']} mm thick",
              "m2", internal_plaster_area, "PLASTER_INT",
              float(s["internal_plaster"]["rate_inr_per_m2"]),
              "int_wall_both_faces + ext_wall_inner_face",
              {"H": H, "N": floors, "perim_m": round(p.perimeter_m, 2)}),
        _line("finishes", 2,
              f"External plaster CM 1:4, {s['external_plaster']['thickness_mm']} mm thick, two-coat",
              "m2", external_wall_face_area, "PLASTER_EXT",
              float(s["external_plaster"]["rate_inr_per_m2"]),
              "perim * H * N * (1-dedn)",
              {"perim_m": round(p.perimeter_m, 2), "H": H, "N": floors,
               "dedn": OPENING_DEDUCTION_WALL}),
        _line("finishes", 3,
              "Ceiling plaster CM 1:4, 6 mm thick",
              "m2", ceiling_area, "PLASTER_CEILING", 220.0,
              "plate_area * N",
              {"plate_area_m2": round(p.area_m2, 2), "N": floors}),
        _line("finishes", 4,
              f"Internal paint — {s['internal_paint']['material']}, 2 coats over primer",
              "m2", internal_plaster_area, "PAINT_INT",
              float(s["internal_paint"]["rate_inr_per_m2"]),
              "same area as internal plaster",
              {"m2": round(internal_plaster_area, 2)}),
        _line("finishes", 5,
              f"External paint — {s['external_paint']['material']}, 2 coats",
              "m2", external_wall_face_area, "PAINT_EXT",
              float(s["external_paint"]["rate_inr_per_m2"]),
              "same area as external plaster",
              {"m2": round(external_wall_face_area, 2)}),
        _line("finishes", 6,
              f"Flooring — {s['flooring']['material']} on CM bed",
              "m2", max(floor_tile_area, 0.0), "FLOORING",
              float(s["flooring"]["rate_inr_per_m2"]),
              "plate*(1-wet_dedn)*N - wet_area",
              {"plate_m2": round(p.area_m2, 2), "wet_dedn": WET_AREA_FLOOR_DEDUCTION,
               "wet_area_m2": round(wet_area, 2), "N": floors}),
        _line("finishes", 7,
              f"Wet-area dado — {s['dado']['material']} up to {s['dado']['height_m']} m height",
              "m2", dado_area, "DADO",
              float(s["dado"]["rate_inr_per_m2"]),
              "toilets * dado_h * 10",
              {"toilets": toilets, "dado_h": s["dado"]["height_m"]}),
        _line("finishes", 8,
              "Wet-area flooring — anti-skid ceramic tiles",
              "m2", wet_area, "WET_FLOORING", 850.0,
              "toilets * 5",
              {"toilets": toilets}),
        _line("finishes", 9,
              f"Skirting — {s['skirting']['material']}, 100 mm high",
              "m", skirting_length, "SKIRTING",
              float(s["skirting"]["rate_inr_per_m"]),
              "int_perim * N * 0.85 (door deduction)",
              {"int_perim_m": round(p.perimeter_m * INTERNAL_WALL_FACTOR, 2),
               "N": floors}),
        _line("finishes", 10,
              "False ceiling in common areas (gypsum, grid-mounted) — 20% of plate",
              "m2", ceiling_area * 0.20, "FALSE_CEILING", 1250.0,
              "plate * 0.20 * N",
              {"plate_m2": round(p.area_m2, 2), "N": floors}),
    ]
    return lines


# ================================================================= doors & windows
def takeoff_doors_windows(ctx: TakeoffContext) -> list[QuantityLine]:
    p = ctx.plate
    s = ctx.spec
    floors = ctx.params["floors"]
    H = float(ctx.params["floor_height_m"])

    toilets = _toilet_count(ctx)
    rooms_per_floor = max(3, int(math.ceil(p.area_m2 / 25.0)))  # ~1 door per 25 m²
    internal_door_count = (rooms_per_floor + toilets) * floors
    main_door_count = floors
    door_leaf = float(s["doors"]["average_leaf_m2"])

    internal_door_area = internal_door_count * door_leaf
    main_door_area = main_door_count * door_leaf

    window_area = p.perimeter_m * H * floors * float(s["windows"]["wwr"])

    # Grills (basic/standard, not premium). We charge a token kg for all; cost very different per level.
    grill_kg = p.perimeter_m * floors * 8.0

    lines = [
        _line("doors_windows", 1,
              f"Main entrance door shutter — {s['doors']['material']} (upgraded)",
              "m2", main_door_area, "DOOR_MAIN",
              float(s["doors"]["main_door_rate_inr_per_m2"]),
              "main_doors * leaf_area",
              {"count": main_door_count, "leaf_m2": door_leaf}),
        _line("doors_windows", 2,
              f"Internal door shutters — {s['doors']['material']}",
              "m2", internal_door_area, "DOOR_INT",
              float(s["doors"]["rate_inr_per_m2"]),
              "int_doors * leaf_area",
              {"count": internal_door_count, "leaf_m2": door_leaf}),
        _line("doors_windows", 3,
              "Door frames (hardwood/pine) — 60 × 100 mm section",
              "m", (main_door_count + internal_door_count) * 5.5, "DOOR_FRAME", 820.0,
              "doors * 5.5 m frame perimeter",
              {"total_doors": main_door_count + internal_door_count}),
        _line("doors_windows", 4,
              f"Windows — {s['windows']['material']}",
              "m2", window_area, "WINDOW",
              float(s["windows"]["rate_inr_per_m2"]),
              "perim * H * N * wwr",
              {"perim_m": round(p.perimeter_m, 2), "H": H, "N": floors,
               "wwr": s["windows"]["wwr"]}),
        _line("doors_windows", 5,
              "MS grills on external windows (ground floor + stilts)",
              "kg", grill_kg, "GRILL_MS", 180.0,
              "perim * N * 8",
              {"perim_m": round(p.perimeter_m, 2), "N": floors}),
    ]
    return lines


# ================================================================= waterproofing
def takeoff_waterproofing(ctx: TakeoffContext) -> list[QuantityLine]:
    p = ctx.plate
    s = ctx.spec
    toilets = _toilet_count(ctx)
    terrace_area = p.area_m2  # roof only
    toilet_area = toilets * 5.0

    lines = [
        _line("waterproofing", 1,
              "Terrace waterproofing — APP membrane 4 mm with protective screed",
              "m2", terrace_area, "WP_TERRACE",
              float(s["waterproofing"]["terrace_rate_inr_per_m2"]),
              "roof_plate_area",
              {"plate_m2": round(p.area_m2, 2)}),
        _line("waterproofing", 2,
              "Toilet / wet-area waterproofing — polymer-modified cementitious coating",
              "m2", toilet_area, "WP_TOILET",
              float(s["waterproofing"]["toilet_rate_inr_per_m2"]),
              "toilets * 5",
              {"toilets": toilets}),
    ]
    return lines


# ================================================================= services
def takeoff_services(ctx: TakeoffContext) -> list[QuantityLine]:
    p = ctx.plate
    s = ctx.spec
    builtup = float(ctx.params["builtup_area_m2"])
    toilets = _toilet_count(ctx)

    e_points = builtup * float(s["electrical"]["points_per_m2_builtup"])
    plumbing_lump = toilets * 25000.0           # plumbing lines + fittings supply/install
    sanitary_lump = toilets * float(s["sanitary"]["per_toilet_lumpsum_inr"])

    lines = [
        _line("services", 1,
              f"Electrical point wiring — {s['electrical']['rate_inr_per_point']} INR/point",
              "nos", e_points, "ELEC_POINT",
              float(s["electrical"]["rate_inr_per_point"]),
              "builtup * points_per_m2",
              {"builtup_m2": builtup,
               "pts_per_m2": s["electrical"]["points_per_m2_builtup"]}),
        _line("services", 2,
              "Electrical main board, meter and feeder cables — lump sum per floor",
              "nos", float(ctx.params["floors"]), "ELEC_MAIN", 42000.0,
              "floors",
              {"floors": ctx.params["floors"]}),
        _line("services", 3,
              "Internal plumbing — supply and installation (per toilet)",
              "nos", float(toilets), "PLUMBING",
              plumbing_lump / max(toilets, 1),
              "toilets",
              {"toilets": toilets}),
        _line("services", 4,
              "Sanitary fittings — WC, basin, tap set, bath fittings (per toilet)",
              "nos", float(toilets), "SANITARY",
              float(s["sanitary"]["per_toilet_lumpsum_inr"]),
              "toilets",
              {"toilets": toilets, "spec_rate": s["sanitary"]["per_toilet_lumpsum_inr"]}),
    ]
    return lines


# ================================================================= external works
def takeoff_external_works(ctx: TakeoffContext) -> list[QuantityLine]:
    plot_area = float(ctx.params["plot_area_m2"])
    builtup_footprint = float(ctx.params["builtup_area_m2"]) / float(ctx.params["floors"])

    # Rough plot perimeter if plot is roughly square.
    plot_perim = 4.0 * math.sqrt(plot_area)
    paving_area = max(plot_area - builtup_footprint, 0.0)
    compound_wall_length = plot_perim

    lines = [
        _line("external_works", 1,
              "Compound wall — 1.8 m high brickwork with RCC coping, 230 mm thick",
              "m", compound_wall_length, "COMPOUND_WALL", 2400.0,
              "4*sqrt(plot_area)",
              {"plot_area_m2": plot_area}),
        _line("external_works", 2,
              "Driveway and courtyard paving — M20 PCC 100 mm thick with wire mesh",
              "m2", paving_area, "DRIVEWAY_PAVE", 820.0,
              "plot_area - footprint",
              {"plot_m2": plot_area, "footprint_m2": round(builtup_footprint, 2)}),
        _line("external_works", 3,
              "MS boundary gate — twin-leaf 3.0 m wide, incl. hinges and lock",
              "nos", 1.0, "GATE_MS", 32000.0,
              "lumpsum",
              {}),
        _line("external_works", 4,
              "Landscaping and soft areas — lump sum",
              "nos", 1.0, "LANDSCAPE", 45000.0,
              "lumpsum",
              {}),
    ]
    return lines


# ================================================================= miscellaneous
def takeoff_misc(ctx: TakeoffContext) -> list[QuantityLine]:
    floors = int(ctx.params["floors"])
    builtup = float(ctx.params["builtup_area_m2"])
    tanks = max(1, int(math.ceil(builtup / 500.0)))
    lift_lines: list[QuantityLine] = []
    if floors >= 4:
        lift_lines.append(_line(
            "miscellaneous", 10,
            f"Passenger lift — 6-pax capacity, {floors} stops incl. shaft RCC extra",
            "nos", 1.0, "LIFT", 1_250_000.0,
            "lumpsum when floors>=4",
            {"floors": floors},
        ))

    lines = [
        _line("miscellaneous", 1,
              "Overhead PVC water tank — 1000 L capacity on RCC supports",
              "nos", float(tanks), "WATER_TANK_OHT", 18000.0,
              "ceil(builtup/500)",
              {"builtup_m2": builtup}),
        _line("miscellaneous", 2,
              "Underground sump — RCC, 10 KL capacity with manhole",
              "nos", 1.0, "SUMP_UGR", 85000.0,
              "lumpsum",
              {}),
        _line("miscellaneous", 3,
              "Rainwater harvesting pit with filter and recharge well",
              "nos", 1.0, "RWH", 32000.0,
              "lumpsum",
              {}),
    ]
    return lines + lift_lines


# ================================================================= public API
def run_takeoff(params: dict[str, Any], rules: dict[str, Any], spec: dict[str, Any]) -> list[QuantityLine]:
    """End-to-end: BuildingParams dict + rules + spec → ordered list of QuantityLines."""
    ctx = build_context(params, rules, spec)
    lines = (
        takeoff_substructure(ctx)
        + takeoff_frame(ctx)
        + takeoff_masonry(ctx)
        + takeoff_finishes(ctx)
        + takeoff_doors_windows(ctx)
        + takeoff_waterproofing(ctx)
        + takeoff_services(ctx)
        + takeoff_external_works(ctx)
        + takeoff_misc(ctx)
    )
    return lines


# ------------------------------------------------------------------ internals
def _toilet_count(ctx: TakeoffContext) -> int:
    builtup = float(ctx.params["builtup_area_m2"])
    per_100 = float(ctx.spec["sanitary"]["toilets_per_100m2_builtup"])
    return max(1, int(round(builtup / 100.0 * per_100)))


def _line(
    element: str,
    seq: int,
    description: str,
    unit: str,
    qty: float,
    rate_code: str,
    fallback_rate: float,
    formula: str,
    inputs: dict,
) -> QuantityLine:
    trace = FormulaTrace(
        rule_id=f"takeoff.{element}.{seq}",
        version="0.1.0",
        formula=formula,
        inputs=inputs,
        output=round(qty, 3),
        source=f"takeoff.py:{element}",
    )
    return QuantityLine(
        element=element,
        seq=seq,
        description=description,
        unit=unit,
        qty=round(qty, 3),
        rate_code=rate_code,
        fallback_rate_inr=fallback_rate,
        trace=trace,
    )
