#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

# ------------------------------------------------------------------------------
# Build families.json primarily from Gramps-derived JSONs:
#   - person_family_index.json  (person ID -> [family_id,...])
#   - family_person_index.json  (family_id -> [person IDs,...])
#
# Then enrich/override with optional Markdown files in data/families/*.md:
#   ---                     # front matter start
#   id: gorges              # required in MD to override filename-based id
#   label: "Gorges"         # optional, overrides auto-titleized label
#   related:
#     places:
#       - P0014             # optional list of P#### references
#   ---
#   (body becomes description_md)
#
# Outputs (to --datadir, default web/data):
#   - families.json
#   - family_place_index.json
# ------------------------------------------------------------------------------

FM_START = re.compile(r"^---\s*$", re.M)
FM_END   = re.compile(r"^---\s*$", re.M)

def strip_inline_comment(s: str) -> str:
    # "P0014 # Groß Salze" -> "P0014"
    i = s.find("#")
    if i != -1:
        s = s[:i]
    return s.strip()

def parse_front_matter_block(text: str):
    """
    Return (fm_text, body_text). If no front matter, fm_text='' and body_text=text.
    """
    m1 = FM_START.search(text)
    if not m1:
        return "", text
    m2 = FM_END.search(text, m1.end())
    if not m2:
        return "", text
    fm = text[m1.end():m2.start()]
    body = text[m2.end():].lstrip("\n")
    return fm, body

def extract_id(fm: str):
    m = re.search(r'(?m)^\s*id:\s*"?([^"\n]+)"?\s*$', fm)
    return m.group(1).strip() if m else None

def extract_label(fm: str):
    m = re.search(r'(?m)^\s*label:\s*"?([^"\n]+)"?\s*$', fm)
    return m.group(1).strip() if m else None

def extract_places(fm: str):
    """
    Finds:
      related:
        places:
          - P0014 # comment
          - P0024
    Returns list[str] of P####.
    """
    # First locate a 'places:' line (at any indent)
    places_line = None
    for m in re.finditer(r'(?m)^(?P<indent>[ \t]*)places:\s*$', fm):
        places_line = m
        break
    if not places_line:
        return []

    base_indent = places_line.group("indent")
    lines = fm[places_line.end():].splitlines()
    items = []
    for line in lines:
        if not line.strip():
            continue
        stripped = line.lstrip(" \t")
        indent_len = len(line) - len(stripped)
        # Stop when dedented to the same level or less
        if indent_len <= len(base_indent):
            break
        # Only accept list items at deeper indent
        if not stripped.startswith("- "):
            continue
        val = strip_inline_comment(stripped[2:].strip().strip('"'))
        if val:
            items.append(val)
    return items

def titleize(fid: str) -> str:
    """
    Simple titleizer: "gorges-ploetz" -> "Gorges Ploetz", "von_steuben" -> "Von Steuben".
    Keep it predictable; you can refine later for name particles.
    """
    parts = re.split(r"[-_\s]+", fid.strip())
    parts = [p.capitalize() if p else p for p in parts]
    return " ".join([p for p in parts if p])

def read_json(path: Path):
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def main():
    ap = argparse.ArgumentParser(
        description="Build families.json from Gramps data; enrich with optional Markdown."
    )
    ap.add_argument(
        "--datadir",
        default="web/data",
        help="Directory containing app JSON data (default: web/data)",
    )
    ap.add_argument(
        "--families-dir",
        default="data/families",
        help="Directory containing family Markdown files (default: data/families)",
    )
    ap.add_argument("--debug", action="store_true", help="Verbose logging")
    args = ap.parse_args()

    data_dir = Path(args.datadir)
    fam_dir = Path(args.families_dir)

    # 1) Primary set of family IDs from Gramps-derived JSONs
    fam_ids = set()

    person_family_index = read_json(data_dir / "person_family_index.json") or {}
    for _pid, fams in person_family_index.items():
        for f in (fams or []):
            fam_ids.add(f)

    family_person_index = read_json(data_dir / "family_person_index.json") or {}
    fam_ids |= set(family_person_index.keys())

    # 2) Seed default structures for each family
    families = {}           # family_id -> record
    fam_place_index = {}    # family_id -> [P####,...]
    for fid in sorted(fam_ids):
        families[fid] = {
            "id": fid,
            "label": titleize(fid),
            "description_md": "",
            "related": {"places": []},
        }
        fam_place_index[fid] = []

    # 3) Enrich/override from Markdown (secondary; optional)
    if fam_dir.exists():
        for md_path in sorted(fam_dir.glob("*.md")):
            raw = md_path.read_text(encoding="utf-8")
            fm_text, body_md = parse_front_matter_block(raw)

            fid = extract_id(fm_text) or md_path.stem  # fallback to filename
            label = extract_label(fm_text)
            places = extract_places(fm_text)

            if args.debug:
                print(f"[families] {md_path.name}")
                print(f"  id: {fid!r}")
                print(f"  label: {label!r}")
                print(f"  places({len(places)}): {places}")

            # Allow pre-staging a family via MD even if not yet in Gramps
            if fid not in families:
                families[fid] = {
                    "id": fid,
                    "label": titleize(fid),
                    "description_md": "",
                    "related": {"places": []},
                }
                fam_place_index[fid] = []

            if label:
                families[fid]["label"] = label
            if body_md:
                families[fid]["description_md"] = body_md

            if places:
                families[fid]["related"]["places"] = [{"gramps_id": p} for p in places]
                fam_place_index[fid] = places

    # 4) Normalize
    for fid in list(families.keys()):
        families[fid].setdefault("related", {}).setdefault("places", [])
        fam_place_index.setdefault(fid, [])

    # 5) Write outputs
    write_json(data_dir / "families.json", families)
    write_json(data_dir / "family_place_index.json", fam_place_index)

    print(
        f"[families] wrote {len(families)} families "
        f"({sum(len(v) for v in fam_place_index.values())} place refs)"
    )

if __name__ == "__main__":
    main()
