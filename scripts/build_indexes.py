#!/usr/bin/env python3
from pathlib import Path
import json
import argparse
from collections import defaultdict

def read_json(p: Path):
    if not p.exists():
        return None
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def write_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def main():
    ap = argparse.ArgumentParser(description="Build crosswalk indexes: families↔origins↔parcels")
    ap.add_argument("--datadir", default="web/data", help="Directory containing app JSON data (default: web/data)")
    args = ap.parse_args()

    data_dir = Path(args.datadir)

    # Required core
    persons                  = read_json(data_dir / "persons.json") or {}
    family_person_index_ids  = read_json(data_dir / "family_person_index.json") or {}
    person_family_index_ids  = read_json(data_dir / "person_family_index.json") or {}

    # Helpful/optional
    families_meta            = read_json(data_dir / "families.json") or {}
    family_place_index_ids   = read_json(data_dir / "family_place_index.json") or {}

    person_index_handles     = read_json(data_dir / "person_index.json") or {}
    parcel_index_handles     = read_json(data_dir / "parcel_index.json") or {}
    origin_parcel_index      = read_json(data_dir / "origin_parcel_index.json") or {}

    # NEW tiny maps to be emitted by exporter (recommended)
    handle_by_id             = read_json(data_dir / "handle_by_id.json") or {}
    place_handle_by_id       = read_json(data_dir / "place_handle_by_id.json") or {}

    if family_person_index_ids and not handle_by_id:
        print("[build_indexes] WARNING: family_person_index.json present but handle_by_id.json is missing; "
              "cannot resolve persons. Consider emitting handle_by_id.json from export_from_gramps.py.")
    if family_place_index_ids and not place_handle_by_id:
        print("[build_indexes] WARNING: family_place_index.json present but place_handle_by_id.json is missing; "
              "will skip converting P#### IDs to handles and only rely on persons' origins.")

    # --- Build family → origins (place handles) ---
    fam_to_origins = defaultdict(set)

    # 1) From people’s chosen origins (preferable; derived from data)
    for fam_id, person_ids in family_person_index_ids.items():
        for pid in person_ids:
            ph = handle_by_id.get(pid)  # person handle
            if not ph:
                continue
            prec = persons.get(ph) or {}
            oph = prec.get("origin_place_handle")
            if oph:
                fam_to_origins[fam_id].add(oph)

    # 2) From family files' related places (P#### → convert to handles if possible)
    for fam_id, pids in family_place_index_ids.items():
        for place_id in pids:
            if place_handle_by_id:
                ph = place_handle_by_id.get(place_id)
                if ph:
                    fam_to_origins[fam_id].add(ph)

    # --- Invert to origin → families ---
    origin_to_fams = defaultdict(set)
    for fam, origins in fam_to_origins.items():
        for oph in origins:
            origin_to_fams[oph].add(fam)

    # --- Build family → parcels ---
    fam_to_parcels = defaultdict(set)

    # Strategy A: go through family→person IDs → person handle → person_index (handle→parcels)
    if person_index_handles:
        for fam_id, person_ids in family_person_index_ids.items():
            for pid in person_ids:
                ph = handle_by_id.get(pid)
                if not ph:
                    continue
                for parcel_key in person_index_handles.get(ph, []):
                    fam_to_parcels[fam_id].add(parcel_key)

    # Strategy B (fallback): invert parcel_index (parcel→handles) to handles→parcels,
    # then walk from family→person IDs→handle. (Only needed if person_index is missing)
    if not person_index_handles and parcel_index_handles:
        person_to_parcels = defaultdict(set)
        for parcel_key, person_handles in parcel_index_handles.items():
            for ph in person_handles:
                person_to_parcels[ph].add(parcel_key)
        for fam_id, person_ids in family_person_index_ids.items():
            for pid in person_ids:
                ph = handle_by_id.get(pid)
                if not ph:
                    continue
                for parcel_key in person_to_parcels.get(ph, []):
                    fam_to_parcels[fam_id].add(parcel_key)

    # --- Invert to parcel → families ---
    parcel_to_fams = defaultdict(set)
    for fam, parcels in fam_to_parcels.items():
        for pk in parcels:
            parcel_to_fams[pk].add(fam)

    # Normalize to sorted lists
    def norm(d):
        return {k: sorted(v) for k, v in sorted(d.items())}

    out_family_origin_index = norm(fam_to_origins)
    out_origin_family_index = norm(origin_to_fams)
    out_family_parcel_index = norm(fam_to_parcels)
    out_parcel_family_index = norm(parcel_to_fams)

    # Write
    write_json(data_dir / "family_origin_index.json", out_family_origin_index)
    write_json(data_dir / "origin_family_index.json", out_origin_family_index)
    write_json(data_dir / "family_parcel_index.json", out_family_parcel_index)
    write_json(data_dir / "parcel_family_index.json", out_parcel_family_index)

    # Summary
    print("[build_indexes] wrote:")
    print(f"  family_origin_index.json   families={len(out_family_origin_index)}")
    print(f"  origin_family_index.json   origins={len(out_origin_family_index)}")
    print(f"  family_parcel_index.json   families={len(out_family_parcel_index)}")
    print(f"  parcel_family_index.json   parcels={len(out_parcel_family_index)}")

if __name__ == "__main__":
    main()
