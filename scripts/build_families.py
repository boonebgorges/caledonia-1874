#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent
FAMDIR = ROOT / "data" / "families"
OUTDIR = ROOT / "web" / "data"

FM_START = re.compile(r"^---\s*$", re.M)
FM_END   = re.compile(r"^---\s*$", re.M)

# simple helpers
def strip_inline_comment(s: str) -> str:
    # remove inline comment: "P0014 # Groß Salze" -> "P0014"
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
    # find the next --- after the first
    m2 = FM_END.search(text, m1.end())
    if not m2:
        # malformed; treat as no FM
        return "", text
    fm = text[m1.end():m2.start()]
    body = text[m2.end():].lstrip("\n")
    return fm, body

def extract_id(fm: str) -> str | None:
    # id: gorges   OR id: "gorges"
    m = re.search(r'(?m)^\s*id:\s*"?([^"\n]+)"?\s*$', fm)
    return m.group(1).strip() if m else None

def extract_label(fm: str) -> str | None:
    # label: Gorges  OR label: "Gorges"
    m = re.search(r'(?m)^\s*label:\s*"?([^"\n]+)"?\s*$', fm)
    return m.group(1).strip() if m else None

def extract_places(fm: str) -> list[str]:
    """
    Find an indented 'places:' block (usually under 'related:') and return list items.
    We assume:
      related:
        places:
          - P0014 # comment
          - P0024
    """
    # locate the 'places:' line and its indentation
    places_line = None
    for m in re.finditer(r'(?m)^(?P<indent>[ \t]*)places:\s*$', fm):
        places_line = m
        break
    if not places_line:
        return []

    base_indent = places_line.group("indent")
    # list items must be indented MORE than 'places:' and start with "- "
    lines = fm[places_line.end():].splitlines()
    items = []
    for line in lines:
        if not line.strip():
            # blank lines inside block are fine; keep scanning
            continue
        # stop when dedented back to same or less than 'places:' indent and not a list item
        if not line.startswith(base_indent) or (len(line) > len(base_indent) and line[len(base_indent)] not in (" ", "\t", "-")):
            # conservative stop on clear dedent
            pass
        # determine current indentation
        stripped = line.lstrip(" \t")
        indent_len = len(line) - len(stripped)
        # must be strictly deeper than base indent
        if indent_len <= len(base_indent):
            # dedented out of the block => stop
            break
        # must be a list item at this level or deeper
        if not stripped.startswith("- "):
            # if it's a nested map, we ignore it (we only care about list items)
            # but if it's a further-indented continuation, we stop when dedented anyway
            continue
        val = strip_inline_comment(stripped[2:].strip().strip('"'))
        if val:
            items.append(val)
    return items

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="print per-file parse info")
    args = ap.parse_args()

    families = {}
    fam_place_index = {}

    if not FAMDIR.exists():
        raise SystemExit(f"Missing directory: {FAMDIR}")

    for md_path in sorted(FAMDIR.glob("*.md")):
        raw = md_path.read_text(encoding="utf-8")

        fm_text, body_md = parse_front_matter_block(raw)
        fid   = extract_id(fm_text)
        label = extract_label(fm_text)
        places = extract_places(fm_text)

        if args.debug:
            print(f"[families] {md_path.name}")
            print(f"  id: {fid!r}")
            print(f"  label: {label!r}")
            print(f"  places({len(places)}): {places}")

        if not fid:
            raise SystemExit(f"{md_path.name}: front matter must include 'id'")

        if not label:
            label = fid.title()

        families[fid] = {
            "id": fid,
            "label": label,
            "description_md": body_md,
            "related": {"places": [{"gramps_id": p} for p in places]},
        }
        fam_place_index[fid] = places

    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "families.json").write_text(json.dumps(families, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTDIR / "family_place_index.json").write_text(json.dumps(fam_place_index, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[families] wrote {len(families)} families "
          f"({sum(len(v) for v in fam_place_index.values())} place refs)")

if __name__ == "__main__":
    main()
