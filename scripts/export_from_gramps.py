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

    # tags: handle -> name
    tagname_by_handle = {}
    for tag in root.findall(f"{NS}tags/{NS}tag"):
        tagname_by_handle[tag.get("handle")] = tag.get("name")

    # places
    places = {}  # handle -> dict
    children_by_parent = {}
    for po in root.findall(f"{NS}places/{NS}placeobj"):
        h = po.get("handle")
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
            "name": primary or h,
            "type": typ,
            "lat": lat,
            "lon": lon,
            "parent": parent,
            "alt_names": [n for n in names if n.get("value") != primary]
        }
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
            if nm: ev_tags.append(nm)
        place = None
        pl = ev.find(f"{NS}place")
        if pl is not None:
            place = pl.get("hlink")
        events[eh] = {
            "type": typ,
            "date": date_tuple_from_event(ev),
            "place": place,
            "tags": ev_tags
        }


    # people: handle -> dict
    people = {}
    id_by_handle = {}
    handle_by_id = {}
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
            if sur: display = (display + " " + sur).strip()
        else:
            display = ph

        evrefs = [er.get("hlink") for er in p.findall(f"{NS}eventref")]
        people[ph] = {"display_name": display, "event_refs": evrefs}

        if pid:
            id_by_handle[ph] = pid
            handle_by_id[pid] = ph


    # families: gather family eventrefs and map them to members
    family_events_by_person = {}
    for fam in root.findall(f"{NS}families/{NS}family"):
        evrefs = [er.get("hlink") for er in fam.findall(f"{NS}eventref")]

        members = []
        fa = fam.find(f"{NS}father")
        mo = fam.find(f"{NS}mother")
        if fa is not None and fa.get("hlink"): members.append(fa.get("hlink"))
        if mo is not None and mo.get("hlink"): members.append(mo.get("hlink"))
        for cr in fam.findall(f"{NS}childref"):
            if cr.get("hlink"):
                members.append(cr.get("hlink"))

        for ph in set(members):
            if evrefs:
                family_events_by_person.setdefault(ph, set()).update(evrefs)

    # attach to people
    for ph in people.keys():
        people[ph]["family_event_refs"] = sorted(family_events_by_person.get(ph, []))

    return people, events, places, children_by_parent, id_by_handle, handle_by_id

def choose_origin_for_person(person, events):
    # gather this person's own events + family events
    ev_handles = []
    ev_handles.extend([h for h in person.get("event_refs", []) if h in events])
    ev_handles.extend([h for h in person.get("family_event_refs", []) if h in events])

    evs = [events[h] for h in ev_handles]

    # immigration date (latest, if multiple)
    imigs = sorted([e["date"] for e in evs if e["type"].lower() == "immigration" and e["date"][0] is not None])
    imig = imigs[-1] if imigs else (None,None,None)

    # candidates = ANY dated event with a place
    candidates_all = [e for e in evs if e.get("place") and e.get("date") and e["date"][0] is not None]

    # ranking: evidence tag (direct > family > fallback > none),
    # then whether it’s ≤ immigration (prefer True),
    # then latest date wins
    candidates = sorted(
        candidates_all,
        key=lambda e: (
            tag_rank(e.get("tags")),
            0 if tuple_leq(e["date"], imig) else 1,
            (e["date"][0] or 0, e["date"][1] or 0, e["date"][2] or 0)
        )
    )

    origin_place = None
    origin_method = None
    origin_event_date = None

    for e in candidates:
        # If we know immigration, require e <= immigration. If we don't, accept the top-ranked event.
        if imig[0] is None or tuple_leq(e["date"], imig):
            origin_place = e["place"]
            origin_event_date = e["date"]
            # keep the nice method labeling you had
            origin_method = next((t for t in e.get("tags", []) if t.lower().startswith("evidence-")), e["type"].lower() or "event")
            break

    # fallback: birth (unchanged)
    if origin_place is None:
        births = [e for e in evs if e["type"].lower() == "birth" and e.get("place")]
        if births:
            b = births[0]
            origin_place = b["place"]
            origin_event_date = b["date"]
            origin_method = "birth"

    is_immigrant = any(e["type"].lower() == "immigration" for e in evs)

    return {
        "is_immigrant": bool(is_immigrant),
        "origin_place_handle": origin_place,
        "origin_method": origin_method,
        "origin_event_date": "-".join(str(x) for x in origin_event_date if x is not None) if origin_event_date else None
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

def main():
    ap = argparse.ArgumentParser(description="Export persons/origins/indexes from a Gramps .gramps file")
    ap.add_argument("--gramps", required=True, help="Path to .gramps XML file")
    ap.add_argument("--outdir", default="data", help="Output directory")
    ap.add_argument("--associations", help="Optional associations.csv to build origin_parcel_index.json")
    ap.add_argument("--places", choices=["all","origins"], default="all",
                    help="'all' = emit all places; 'origins' = emit only places referenced by person origins and their ancestors")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    people, events, places, children_by_parent, id_by_handle, handle_by_id = read_gramps(args.gramps)

    # Persons export
    persons_out = {}
    origin_index = {}  # place_handle -> [person_handle,...]
    origin_place_set = set()

    for ph, prec in people.items():
        choice = choose_origin_for_person(prec, events)
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
