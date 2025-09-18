#!/usr/bin/env python3
"""
Export persons + origins + indexes from a Gramps .gramps (XML) file.

Outputs (to --outdir):
  - persons.json                # keyed by person handle
  - origins.json                # place handle -> {name, lat, lon, parent, type, alt_names}
  - place_tree.json             # nested tree for "Browse by origin"
  - origin_index.json           # place handle -> [person handles...]
  - origin_parcel_index.json    # OPTIONAL, if --associations provided: place -> ["YEAR:PARCEL_ID",...]

Associations CSV (optional) must have headers:
  parcel_id,map_year,person_id,role,map_label
Where person_id = Gramps person handle used here.
"""

import argparse, csv, json, re
from pathlib import Path
import xml.etree.ElementTree as ET

NS = "{http://gramps-project.org/xml/1.7.2/}"
US_ROOTS = { "P0006" }  

def ymd(s):
    # returns (y,m,d) from "YYYY[-MM[-DD]]" or (None,None,None)
    if not s: return (None,None,None)
    m = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$", s)
    if not m: return (None,None,None)
    y = int(m.group(1))
    mo = int(m.group(2)) if m.group(2) else None
    d = int(m.group(3)) if m.group(3) else None
    return (y,mo,d)

def date_tuple_from_event(ev):
    dv = ev.find(f"{NS}dateval")
    if dv is not None and dv.get("val"):
        return ymd(dv.get("val"))
    dr = ev.find(f"{NS}daterange")
    if dr is not None:
        stop = dr.get("stop"); start = dr.get("start")
        return ymd(stop or start)  # use end if available, else start
    return (None,None,None)

def tuple_leq(a, b):
    # a <= b with None-aware logic (None in b means unknown -> treat a as <=)
    ay,am,ad = a; by,bm,bd = b
    if by is None: return True
    if ay is None: return False
    if ay != by: return ay < by
    if bm is None: return True if am is not None else True
    if am is None: return False
    if am != bm: return am <= bm
    if bd is None: return True if ad is not None else True
    if ad is None: return False
    return ad <= bd

def tag_rank(tags):
    tset = { (t or "").lower() for t in (tags or []) }
    if "evidence-direct" in tset: return 0
    if "evidence-family" in tset: return 1
    if "evidence-fallback" in tset: return 2
    return 3  # untagged/other

def read_gramps(path):
    root = ET.parse(path).getroot()

    # Helper: split a family_id value that might be "gorges" or "gorges;ploetz"
    def split_multi(val):
        if not val:
            return []
        return [p.strip() for p in val.split(";") if p.strip()]

    # tags: handle -> name
    tagname_by_handle = {}
    for tag in root.findall(f"{NS}tags/{NS}tag"):
        tagname_by_handle[tag.get("handle")] = tag.get("name")

    # places
    # - keep your existing structure keyed by HANDLE
    # - also keep id<->handle crosswalks so you can use P#### later
    places = {}  # handle -> dict
    place_id_by_handle = {}
    place_handle_by_id = {}
    children_by_parent = {}

    for po in root.findall(f"{NS}places/{NS}placeobj"):
        h = po.get("handle")
        pid = po.get("id")  # e.g., "P0014"
        typ = po.get("type") or "Unknown"

        # primary name = first pname without lang, else first
        names = []
        primary = None
        for pn in po.findall(f"{NS}pname"):
            val = pn.get("value")
            lang = pn.get("lang")
            if val:
                names.append({"value": val, "lang": lang})
                if primary is None and not lang:
                    primary = val
        if primary is None and names:
            primary = names[0]["value"]

        coord = po.find(f"{NS}coord")
        lat = float(coord.get("lat")) if coord is not None and coord.get("lat") else None
        lon = float(coord.get("long")) if coord is not None and coord.get("long") else None

        parent = None
        pr = po.find(f"{NS}placeref")
        if pr is not None:
            parent = pr.get("hlink")

        places[h] = {
            "id": pid,  # NEW: preserve Gramps Place ID
            "name": primary or h,
            "type": typ,
            "lat": lat,
            "lon": lon,
            "parent": parent,
            "alt_names": [n for n in names if n.get("value") != primary],
        }
        if pid:
            place_id_by_handle[h] = pid
            place_handle_by_id[pid] = h

        if parent:
            children_by_parent.setdefault(parent, []).append(h)

    # events: handle -> dict
    events = {}
    for ev in root.findall(f"{NS}events/{NS}event"):
        eh = ev.get("handle")
        typ = (ev.findtext(f"{NS}type") or "").strip()
        # event-level tags
        ev_tags = []
        for tr in ev.findall(f"{NS}tagref"):
            nm = tagname_by_handle.get(tr.get("hlink"))
            if nm:
                ev_tags.append(nm)
        place = None
        pl = ev.find(f"{NS}place")
        if pl is not None:
            place = pl.get("hlink")  # place HANDLE (use place_id_by_handle later if you want P####)

        events[eh] = {
            "type": typ,
            "date": date_tuple_from_event(ev),
            "place": place,
            "tags": ev_tags,
        }

    # people: handle -> dict
    people = {}
    id_by_handle = {}
    handle_by_id = {}

    # NEW: indexes for families
    # We'll store by **person ID** (I####) for stable public use
    person_family_index = {}  # person ID -> [family_id, ...]
    family_person_index = {}  # family_id -> [person ID, ...]

    for p in root.findall(f"{NS}people/{NS}person"):
        ph = p.get("handle")
        pid = p.get("id")

        # name
        nm = p.find(f"{NS}name")
        if nm is not None:
            first = (nm.findtext(f"{NS}first") or "").strip()
            call  = (nm.findtext(f"{NS}call") or "").strip()
            sur   = (nm.findtext(f"{NS}surname") or "").strip()
            display = (call or first).strip()
            if sur:
                display = (display + " " + sur).strip()
        else:
            display = ph

        evrefs = [er.get("hlink") for er in p.findall(f"{NS}eventref")]
        people[ph] = {"display_name": display, "event_refs": evrefs}

        if pid:
            id_by_handle[ph] = pid
            handle_by_id[pid] = ph

        # NEW: parse <attribute type="family_id" value="...">
        fam_ids_raw = []
        for attr in p.findall(f"{NS}attribute"):
            if (attr.get("type") or "").lower() == "family_id":
                fam_ids_raw.extend(split_multi(attr.get("value") or ""))

        if pid and fam_ids_raw:
            # de-dupe, preserve order
            seen, fam_ids = set(), []
            for f in fam_ids_raw:
                if f and f not in seen:
                    fam_ids.append(f)
                    seen.add(f)
            if fam_ids:
                person_family_index[pid] = fam_ids
                for f in fam_ids:
                    family_person_index.setdefault(f, []).append(pid)

    # families: gather family eventrefs and map them to members with type-specific rules
    family_residence_by_person = {}   # person HANDLE -> set(event handles)
    spouse_marriage_by_person = {}    # person HANDLE -> set(event handles)

    for fam in root.findall(f"{NS}families/{NS}family"):
        evrefs = [er.get("hlink") for er in fam.findall(f"{NS}eventref") if er.get("hlink")]

        # Identify members
        father = fam.find(f"{NS}father")
        mother = fam.find(f"{NS}mother")
        fa_h = father.get("hlink") if (father is not None and father.get("hlink")) else None
        mo_h = mother.get("hlink") if (mother is not None and mother.get("hlink")) else None

        # Members: parents+children for Residence propagation
        members = []
        if fa_h: members.append(fa_h)
        if mo_h: members.append(mo_h)
        for cr in fam.findall(f"{NS}childref"):
            if cr.get("hlink"):
                members.append(cr.get("hlink"))

        # Classify each family event by type using the parsed `events` table
        for eh in evrefs:
            e = events.get(eh)
            if not e:
                continue
            et = (e.get("type") or "").lower()
            if et == "residence":
                for ph in set(members):
                    family_residence_by_person.setdefault(ph, set()).add(eh)
            elif et == "marriage":
                # Only spouses get family marriage events
                for ph in {h for h in (fa_h, mo_h) if h}:
                    spouse_marriage_by_person.setdefault(ph, set()).add(eh)

    # Attach to people (by HANDLE)
    for ph in people.keys():
        people[ph]["family_residence_event_refs"] = sorted(family_residence_by_person.get(ph, []))
        people[ph]["spouse_marriage_event_refs"] = sorted(spouse_marriage_by_person.get(ph, []))
        # families: gather family eventrefs and map them to members (as before)
        family_events_by_person = {}
        for fam in root.findall(f"{NS}families/{NS}family"):
            evrefs = [er.get("hlink") for er in fam.findall(f"{NS}eventref")]

            members = []
            fa = fam.find(f"{NS}father")
            mo = fam.find(f"{NS}mother")
            if fa is not None and fa.get("hlink"):
                members.append(fa.get("hlink"))
            if mo is not None and mo.get("hlink"):
                members.append(mo.get("hlink"))
            for cr in fam.findall(f"{NS}childref"):
                if cr.get("hlink"):
                    members.append(cr.get("hlink"))

    for ph in set(members):
      if evrefs:
        family_events_by_person.setdefault(ph, set()).update(evrefs)

    return (
        people,                # handle-keyed
        events,                # handle-keyed
        places,                # handle-keyed (now also carries "id": P####)
        children_by_parent,    # handle-keyed
        id_by_handle,          # person handle -> ID (I####)
        handle_by_id,          # person ID (I####) -> handle
        person_family_index,   # person ID (I####) -> [family_id,...]
        family_person_index,   # family_id -> [person IDs]
        place_id_by_handle,    # place handle -> place ID (P####)
        place_handle_by_id,    # place ID (P####) -> place handle
    )

def is_descendant_of(places: dict, place_handle: str, root_handles: set[str]) -> bool:
    h = place_handle
    seen = set()
    while h:
        if h in root_handles:
            return True
        if h in seen:
            break
        seen.add(h)
        h = places.get(h, {}).get("parent")
    return False

def event_is_in_country(events: dict, places: dict, event_handle: str, country_root_handles: set[str]) -> bool:
  """True if the event has a place and that place lies under any of the given country roots."""

  ev = events.get(event_handle) or {}
  ph = ev.get("place")
  return bool(ph and is_descendant_of(places, ph, country_root_handles))

def choose_origin_for_person(person, events, places, us_roots: set[str]):
    # Person's own events (for immigration + direct candidates)
    own_eh = [h for h in person.get("event_refs", []) if h in events]
    own_evs = [events[h] for h in own_eh]

    # Immigration date (from the PERSON, not family)
    imigs = sorted([e["date"] for e in own_evs
                    if (e["type"] or "").lower() == "immigration" and e["date"][0] is not None])
    imig = imigs[-1] if imigs else (None, None, None)

    # --- NEW: bring in family Residence (everyone) and spouse Marriage (spouses only)
    fam_res_eh = [h for h in person.get("family_residence_event_refs", []) if h in events]
    spouse_mar_eh = [h for h in person.get("spouse_marriage_event_refs", []) if h in events]

    # Build candidate handles:
    # - Residence: own + family
    # - Marriage: own + spouse-only (no child-propagated marriages)
    cand_handles = []

    # Residence candidates
    cand_handles.extend([
        h for h in own_eh
        if (events[h].get("type") or "").lower() == "residence"
    ])
    cand_handles.extend(fam_res_eh)

    # Marriage candidates
    cand_handles.extend([
        h for h in own_eh
        if (events[h].get("type") or "").lower() == "marriage"
    ])
    cand_handles.extend(spouse_mar_eh)

    # Keep everything, but drop marriages that occur in the USA
    def keep_for_origin(eh: str) -> bool:
      t = (events[eh].get("type") or "").lower()
      if t == "marriage" and event_is_in_country(events, places, eh, us_roots):
        return False  # exclude U.S. marriages only
      return True

    cand_handles = [h for h in cand_handles if keep_for_origin(h)]

    # De-dupe while preserving order
    seen = set()
    cand_handles = [h for h in cand_handles if not (h in seen or seen.add(h))]

    # Materialize candidate events with required place+date
    candidates_all = []
    for h in cand_handles:
        e = events[h]
        if e.get("place") and e.get("date") and e["date"][0] is not None:
            candidates_all.append(e)

    # Rank: tags → <= immigration → latest date
    candidates = sorted(
        candidates_all,
        key=lambda e: (
            tag_rank(e.get("tags")),
            0 if tuple_leq(e["date"], imig) else 1,
            (e["date"][0] or 0, e["date"][1] or 0, e["date"][2] or 0),
        ),
    )

    origin_place = origin_method = origin_event_date = None
    for e in candidates:
        # If we know immigration, require e <= immigration. Else accept top-ranked.
        if imig[0] is None or tuple_leq(e["date"], imig):
            origin_place = e["place"]
            origin_event_date = e["date"]
            origin_method = next(
                (t for t in (e.get("tags") or []) if t.lower().startswith("evidence-")),
                (e.get("type") or "event").lower(),
            )
            break

    # Fallback: birth
    if origin_place is None:
        births = [e for e in own_evs if (e["type"] or "").lower() == "birth" and e.get("place")]
        if births:
            b = births[0]
            origin_place = b["place"]
            origin_event_date = b["date"]
            origin_method = "birth"

    is_immigrant = any((e["type"] or "").lower() == "immigration" for e in own_evs)

    return {
        "is_immigrant": bool(is_immigrant),
        "origin_place_handle": origin_place,
        "origin_method": origin_method,
        "origin_event_date": "-".join(str(x) for x in origin_event_date if x is not None) if origin_event_date else None,
    }

def build_place_tree(places, root_handles=None):
    """
    Build a nested tree of places. If root_handles is None, build forest of places with no parent.
    """
    # Index children
    children = {}
    roots = []
    for h, p in places.items():
        par = p.get("parent")
        if par:
            children.setdefault(par, []).append(h)
        else:
            roots.append(h)

    # If caller specified explicit roots, use those instead of inferred roots
    if root_handles:
        roots = list(root_handles)

    def build_node(h):
        node = {
            "handle": h,
            "name": places[h]["name"],
            "type": places[h]["type"],
            "children": []
        }
        for ch in sorted(children.get(h, []), key=lambda k: places[k]["name"]):
            node["children"].append(build_node(ch))
        return node

    forest = [build_node(h) for h in sorted(roots, key=lambda k: places[k]["name"])]
    return forest

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_associations(csv_path):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            rows.append(r)
    return rows

def parse_person_family_links(gramps_xml_path: Path):
    """
    Returns (person_family_index: dict[str, list[str]], family_person_index: dict[str, list[str]])
    by reading <person> elements and their <attribute type="family_id" value="..."> children.
    Accepts multiple attributes and/or semicolon-delimited values.
    """
    tree = ET.parse(gramps_xml_path)
    root = tree.getroot()

    # Gramps default namespace handling (strip if present)
    # If your XML uses namespaces, ElementTree tags look like '{ns}person'.
    # We'll match by localname to be safe.
    def local(tag):
        return tag.rsplit('}', 1)[-1] if '}' in tag else tag

    person_family_index = {}
    for person in root.iter():
        if local(person.tag) != "person":
            continue
        pid = person.get("id")
        if not pid:
            continue

        fam_ids = []
        for attr in person.findall("./*"):
            if local(attr.tag) != "attribute":
                continue
            if (attr.get("type") or "").lower() != "family_id":
                continue
            raw = (attr.get("value") or "").strip()
            if not raw:
                continue
            # support "gorges" or "gorges;ploetz"
            parts = [p.strip() for p in raw.split(";")]
            fam_ids.extend([p for p in parts if p])

        # de-dup while keeping order
        seen, uniq = set(), []
        for f in fam_ids:
            if f not in seen:
                uniq.append(f); seen.add(f)

        if uniq:
            person_family_index[pid] = uniq

    # invert index
    family_person_index = {}
    for pid, fams in person_family_index.items():
        for fid in fams:
            family_person_index.setdefault(fid, []).append(pid)

    # sort lists for a stable output (optional)
    for pid in person_family_index:
        person_family_index[pid] = sorted(person_family_index[pid])
    for fid in family_person_index:
        family_person_index[fid] = sorted(family_person_index[fid])

    return person_family_index, family_person_index

def to_place_handle(token: str) -> str | None:
    """Accept 'P####' or a handle; return a handle (or None)."""
    if not token:
        return None
    if token in places:                 # already a handle
        return token
    if token in place_handle_by_id:     # looks like P#### ID
        return place_handle_by_id[token]
    return None

def main():
    ap = argparse.ArgumentParser(description="Export persons/origins/indexes from a Gramps .gramps file")
    ap.add_argument("--gramps", required=True, help="Path to .gramps XML file")
    ap.add_argument("--outdir", default="data", help="Output directory")
    ap.add_argument("--associations", help="Optional associations.csv to build origin_parcel_index.json")
    ap.add_argument("--places", choices=["all","origins"], default="all",
                    help="'all' = emit all places; 'origins' = emit only places referenced by person origins and their ancestors")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    people, events, places, children_by_parent, id_by_handle, handle_by_id, person_family_index, family_person_index, place_id_by_handle, place_handle_by_id = read_gramps(args.gramps)

    # build mapping once if you want ID support
    place_handle_by_id = {}
    for h, p in places.items():
        pid = p.get("id") if "id" in p else None  # add 'id' when parsing places if not present yet
        if pid:
            place_handle_by_id[pid] = h
    
    def to_place_handle(token: str) -> str | None:
        if not token:
            return None
        if token in places:                 # already a handle
            return token
        if token in place_handle_by_id:     # ID like P0006
            return place_handle_by_id[token]
        return None
    
    # Build a handles-only set ONCE
    US_ROOTS_HANDLES = { h for tok in US_ROOTS for h in [to_place_handle(tok)] if h }

    # Persons export
    persons_out = {}
    origin_index = {}  # place_handle -> [person_handle,...]
    origin_place_set = set()

    for ph, prec in people.items():
        choice = choose_origin_for_person(prec, events, places, US_ROOTS_HANDLES)
        persons_out[ph] = {
            "display_name": prec["display_name"],
            "is_immigrant": choice["is_immigrant"],
            "origin_place_handle": choice["origin_place_handle"],
            "origin_method": choice["origin_method"],
            "origin_event_date": choice["origin_event_date"]
        }
        oph = choice["origin_place_handle"]
        if oph:
            origin_index.setdefault(oph, []).append(ph)
            # Collect ancestors so we can include them in origins.json/place_tree if --places=origins
            cur = oph
            while cur:
                origin_place_set.add(cur)
                cur = places.get(cur, {}).get("parent")

    # Optionally filter places to only those relevant to origins (and ancestors)
    if args.places == "origins":
        places_filtered = {h:p for h,p in places.items() if h in origin_place_set}
    else:
        places_filtered = places

    # origins.json
    origins_out = {h: {
        "name": p["name"],
        "type": p["type"],
        "lat": p["lat"],
        "lon": p["lon"],
        "parent": p["parent"],
        "alt_names": p["alt_names"]
    } for h,p in places_filtered.items()}

    # place_tree.json: build a forest rooted at top-level places in the filtered set
    roots = [h for h,p in places_filtered.items() if not p.get("parent")]
    place_tree = build_place_tree(places_filtered, root_handles=roots)

    # Sort index lists for stability
    for k in list(origin_index.keys()):
        origin_index[k] = sorted(origin_index[k])

    # Optional: build indexes from associations if provided
    origin_parcel_index = {}
    parcel_index = {}       # "year:parcel_id" -> [person_handle,...]
    person_index = {}       # person_handle -> ["year:parcel_id",...]

    if args.associations:
        def add(d, k, v):
            if k not in d: d[k] = []
            if v not in d[k]: d[k].append(v)

        def to_handle(pid_or_handle: str):
            pid_or_handle = (pid_or_handle or "").strip()
            if not pid_or_handle:
                return None
            # already a handle?
            if pid_or_handle in people:
                return pid_or_handle
            # looks like a Gramps person ID (e.g., I0001)?
            if pid_or_handle in handle_by_id:
                return handle_by_id[pid_or_handle]
            return None  # unknown

        assoc_rows = load_associations(args.associations)
        for r in assoc_rows:
            parcel_id = (r.get("parcel_id") or "").strip()
            raw_person = (r.get("person_id") or "").strip()
            map_year  = (r.get("map_year")  or "").strip()
            if not parcel_id or not raw_person or not map_year:
                continue

            person_handle = to_handle(raw_person)
            if not person_handle:
                # skip rows that don't resolve
                continue

            key = f"{map_year}:{parcel_id}"

            # parcel_index & person_index use HANDLES so they match persons.json
            add(parcel_index, key, person_handle)
            add(person_index, person_handle, key)

            # origin_parcel_index (place -> parcels), using persons we just exported
            oph = persons_out.get(person_handle, {}).get("origin_place_handle")
            if oph:
                add(origin_parcel_index, oph, key)

        # sort for stable outputs
        for d in (origin_parcel_index, parcel_index, person_index):
            for k in d:
                d[k] = sorted(d[k])

    # Write files
    write_json(outdir / "persons.json", persons_out)
    write_json(outdir / "origins.json", origins_out)
    write_json(outdir / "place_tree.json", place_tree)
    write_json(outdir / "origin_index.json", origin_index)
    write_json(outdir / "person_family_index.json", person_family_index)
    write_json(outdir / "family_person_index.json", family_person_index)
    write_json(outdir / "id_by_handle.json", id_by_handle)
    write_json(outdir / "handle_by_id.json", handle_by_id)
    write_json(outdir / "place_id_by_handle.json", place_id_by_handle)
    write_json(outdir / "place_handle_by_id.json", place_handle_by_id)

    if origin_parcel_index:
        write_json(outdir / "origin_parcel_index.json", origin_parcel_index)
        write_json(outdir / "parcel_index.json", parcel_index)
        write_json(outdir / "person_index.json", person_index)

    # Small summary
    print(f"Wrote to {outdir}/")
    print(f"  persons.json: {len(persons_out)} people")
    print(f"  origins.json: {len(origins_out)} places (mode={args.places})")
    print(f"  place_tree.json: roots={len([n for n in place_tree])}")
    print(f"  origin_index.json: {len(origin_index)} origin place keys")
    if origin_parcel_index:
        print(f"  origin_parcel_index.json: {len(origin_parcel_index)} origin place keys (from associations)")

if __name__ == "__main__":
    main()
