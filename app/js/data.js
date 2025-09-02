import { urlFor } from './util.js';

// Loaded-at-runtime data caches
export const Data = {
  persons: null,
  parcelIndex: null,
  origins: null,
  originParcelIndex: null,
  parcelsGeoJSON: null,
};

// Load all JSON assets needed across views
export async function loadAllData() {
  const [
    persons, parcelIndex, origins, originParcelIndex, parcelsGeoJSON
  ] = await Promise.all([
    fetch(urlFor('data/persons.json')).then(r => r.json()),
    fetch(urlFor('data/parcel_index.json')).then(r => r.json()),
    fetch(urlFor('data/origins.json')).then(r => r.json()),
    // Optional file; tolerate 404 -> empty object
    fetch(urlFor('data/origin_parcel_index.json')).then(r => r.ok ? r.json() : ({})).catch(() => ({})),
    fetch(urlFor('data/parcels-1874.geojson')).then(r => r.json()),
  ]);

  Data.persons = persons;
  Data.parcelIndex = parcelIndex;
  Data.origins = origins;
  Data.originParcelIndex = originParcelIndex;
  Data.parcelsGeoJSON = parcelsGeoJSON;
}

// Helpers migrated from the inline script
const lineageCache = new Map();
export function placeLineage(handle, opts = {}) {
  const origins = Data.origins || {};
  if (!handle || !origins[handle]) return null;
  if (lineageCache.has(handle)) return lineageCache.get(handle);

  const { stopTypes = [], includeAlt = false, altLang = null } = opts;
  const names = [];
  let h = handle;
  while (h && origins[h]) {
    const p = origins[h];
    let label = p.name || h;

    if (includeAlt && altLang && Array.isArray(p.alt_names)) {
      const alt = p.alt_names.find(a => (a.lang || '').toLowerCase() === altLang.toLowerCase());
      if (alt && alt.value) label = `${label} (${alt.value})`;
    }

    names.push(label);
    if (stopTypes.includes(p.type)) break;
    h = p.parent || null;
  }
  const res = { labels: names, text: names.join(', ') };
  lineageCache.set(handle, res);
  return res;
}

export function ownersWithOriginsForKey(key) {
  const persons = Data.persons || {};
  const parcelIndex = Data.parcelIndex || {};
  const personIds = parcelIndex[key] || [];
  return personIds.map(pid => {
    const person = persons[pid];
    if (!person) return { name: pid, originText: '(unknown)', method: null };
    const lin = placeLineage(person.origin_place_handle, { stopTypes: ['Country'] });
    return {
      name: person.display_name || pid,
      originText: lin?.text || '(origin unknown)',
      method: person.origin_method || null,
    };
  });
}

export function getOriginsForParcel(key) {
  const persons = Data.persons || {};
  const ids = (Data.parcelIndex || {})[key] || [];
  const handles = ids.map(id => persons[id]?.origin_place_handle).filter(Boolean);
  return Array.from(new Set(handles));
}
