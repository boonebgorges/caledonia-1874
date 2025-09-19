// app/js/layers.js
// 2-space indent, framework-free Leaflet utilities for Origins + Parcels.
// Implements "highlight on click" + panel preview/commit via custom events.

import { Store } from './store.js';
import { Data, placeLineage, getOriginsForParcel, ownersWithOriginsForKey } from './data.js';
import { constants, isDescendantOfUSA } from './util.js';

// -----------------------------------------------------------------------------
// Shared helpers
// -----------------------------------------------------------------------------

function getTileLayerMaxZoom(map) {
  let z = Infinity;
  Object.values(map._layers || {}).forEach(l => {
    // L.TileLayer (including retina variants)
    if (l && typeof l.getTileSize === 'function') {
      if (Number.isFinite(l.options?.maxZoom)) {
        z = Math.min(z, l.options.maxZoom);
      }
    }
  });
  return Number.isFinite(z) ? z : undefined;
}

function clampZoom(map, requestedZoom, optMaxZoom) {
  const caps = [
    requestedZoom,
    optMaxZoom,
    map?.options?.maxZoom,
    getTileLayerMaxZoom(map),
  ].filter(z => Number.isFinite(z));
  return Math.min(...caps);
}

// flip to true temporarily if you want console traces
const DEBUG_FIT = false;
function dbg(...args) { if (DEBUG_FIT) console.debug('[fit]', ...args); }

function isCommitGesture(ev) {
  const oe = ev?.originalEvent;
  return !!(oe?.shiftKey || oe?.metaKey || oe?.ctrlKey);
}

// Keep references to built layer APIs so we can pan/zoom from panel events
// (set below when buildOriginsLayer/buildParcelsLayer are called)
let ORIGINS_API = null;
let PARCELS_API = null;

function emit(origin, detail) {
  window.dispatchEvent(new CustomEvent(origin, { detail }));
}

function safeGetOriginsForParcel(key) {
  if (typeof getOriginsForParcel === 'function') return getOriginsForParcel(key) || [];
  // Fallback via originParcelIndex invert (if you don’t have the helper)
  const out = [];
  const idx = Data.originParcelIndex || {};
  for (const [oph, keys] of Object.entries(idx)) {
    if (Array.isArray(keys) && keys.includes(key)) out.push(oph);
  }
  return out;
}

function safeOwnersWithOriginsForKey(key) {
  if (typeof ownersWithOriginsForKey === 'function') return ownersWithOriginsForKey(key) || [];
  // Fallback: show families unknown; callers can omit this if not needed
  return [];
}

// -----------------------------------------------------------------------------
// Origins layer
// -----------------------------------------------------------------------------

export function buildOriginsLayer(map) {
  const group = L.layerGroup().addTo(map);
  const registry = new Map(); // handle -> marker

  const hasCoords = (p) => Number.isFinite(p?.lat) && Number.isFinite(p?.lon);

	// Popup HTML with a commit button
	function originPopupHtml(handle) {
		const p = (Data.origins || {})[handle];
		if (!p) return '<i>Unknown place</i>';

		const lineage = typeof placeLineage === 'function'
			? placeLineage(handle, { stopTypes: ['Country'] })
			: null;

		// Prefer direct index; fall back to deriving from origin→parcel→families
		const familiesForOrigin = (() => {
			const direct = (Data.originFamilyIndex || {})[handle];
			if (Array.isArray(direct) && direct.length) return Array.from(new Set(direct));
			const parcels = (Data.originParcelIndex || {})[handle] || [];
			const out = new Set();
			parcels.forEach(pk => ((Data.parcelFamilyIndex || {})[pk] || []).forEach(fid => out.add(fid)));
			return Array.from(out);
		})();

		const linkedFamilies = familiesForOrigin
			.map(fid => {
				const fam = (Data.families || {})[fid];
				const label = fam?.label || fam?.name || fid;
				return `<li data-family="${fid}">${label}</li>`;
			})
			.join('');

		return `
			<div class="popup">
				<div class="bubble-title"><b>${p.name || handle}</b></div>
				${lineage?.text ? `<div class="subtle"><small>${lineage.text}</small></div>` : ''}
				${linkedFamilies
					? `<div class="mt-2"><div><small>Families</small></div><ul class="linked-families">${linkedFamilies}</ul></div>`
					: ''}
				<div class="actions mt-2">
					<button class="open-details" data-origin="${handle}">Open details</button>
				</div>
			</div>
		`;
	}

  // Map-side highlight only (no panel selection)
  function highlightOrigin(handle) {
    const parcelKeys = (Data.originParcelIndex || {})[handle] || [];
    Store.setActiveOrigins([handle]);
    Store.setActiveParcels(parcelKeys);

    const mk = registry.get(handle);
    if (mk) mk.openPopup();
  }

  // Emit to panel layer
  function emitOriginClick(handle, commit = false) {
    emit('map:click:origin', { handle, commit });
  }

  // Click handler for marker
  function onOriginClick(handle, ev) {
    highlightOrigin(handle);
    emitOriginClick(handle, isCommitGesture(ev));
  }

  // Wire popup “Open details” & linked parcel clicks
  function wireOriginPopupOpen() {
    map.on('popupopen', (e) => {
      const root = e?.popup?.getElement?.() || e?.popup?._container || null;
      if (!root) return;

      // Commit to panel
      const btn = root.querySelector('.open-details[data-origin]');
      if (btn) {
        const handle = btn.getAttribute('data-origin');
        btn.addEventListener('click', (ev) => {
          ev.stopPropagation();
          emitOriginClick(handle, true);
        }, { once: true });
      }

			// Clicks on linked families list (preview + optional commit)
      root.querySelectorAll('ul.linked-families li[data-family]').forEach(li => {
        li.addEventListener('click', (ev2) => {
          ev2.stopPropagation();
          const fid = li.getAttribute('data-family');
          const origins = (Data.familyOriginIndex || {})[fid] || [];
          const parcels = (Data.familyParcelIndex || {})[fid]
            || Array.from(new Set(
                 origins.flatMap(h => (Data.originParcelIndex || {})[h] || [])
               ));

          // Cross-highlight immediately
          Store.setActiveOrigins(origins);
          Store.setActiveParcels(parcels);

          // Preview in panel; user can commit from the preview strip
          emit('map:click:family', { id: fid, commit: false });
        }, { once: true });
      });
    });
  }

  // Create markers
  const markers = Object.entries(Data.origins || {})
    .filter(([handle, p]) => {
			return hasCoords(p) && !isDescendantOfUSA(handle)
		})
    .map(([handle, p]) => {
      const m = L.marker([p.lat, p.lon], {
        icon: L.divIcon({
          className: 'origin-marker',
          html: '<span class="dot">●</span>',
          iconSize: [18, 18],
        })
      })
        .bindPopup(() => originPopupHtml(handle))
        .on('click', (ev) => onOriginClick(handle, ev));

      registry.set(handle, m);
      return m;
    });

  L.featureGroup(markers).addTo(group);
  wireOriginPopupOpen();

  // React to Store updates (active origins)
  const unsub = Store.subscribe(({ activeOrigins }) => {
    registry.forEach((mk, handle) => {
      const el = mk.getElement(); // divIcon root
      if (!el) return;
      el.classList.toggle('is-active', !!activeOrigins && activeOrigins.has(handle));
    });
  });

	const api = {
		group,
		registry,

		fit(handles, opts = {}) {
			const padding = opts.padding || [20, 20];
			const optMaxZoom = opts.maxZoom; // e.g. your maxZOrigins

			const pts = (handles || [])
				.map(h => {
					const p = (Data.origins || {})[h];
					return p ? L.latLng(p.lat, p.lon) : null;
				})
				.filter(Boolean);

			if (!pts.length) return;

			if (pts.length === 1) {
				// Single-point case: compute a safe zoom and setView()
				const desired = clampZoom(map, map.getMaxZoom?.() ?? 18, optMaxZoom);
				dbg('single point', { desired, mapMax: map.options?.maxZoom, tileMax: getTileLayerMaxZoom(map), optMaxZoom });
				map.setView(pts[0], desired);
				return;
			}

			// Multi-point case: compute bounds, get target zoom, clamp, setView()
			const b = L.latLngBounds(pts);
			// getBoundsZoom returns the zoom that would fit the bounds
			const requested = map.getBoundsZoom(b, false, padding);
			const clamped = clampZoom(map, requested, optMaxZoom);
			dbg('multi point', { requested, clamped, mapMax: map.options?.maxZoom, tileMax: getTileLayerMaxZoom(map), optMaxZoom });

			// Use setView(center, clamped) instead of fitBounds to enforce our clamp
			map.setView(b.getCenter(), clamped);
		},

		destroy() { unsub(); map.removeLayer(group); }
	};

  ORIGINS_API = api;
  return api;
}

// -----------------------------------------------------------------------------
// Parcels layer
// -----------------------------------------------------------------------------

export function buildParcelsLayer(map) {
  const byKey = new Map();

  const baseStyle = { color: '#333', weight: 2, fillOpacity: 0.15 };
  const activeStyle = { color: '#111', weight: 3, fillOpacity: 0.35 };

  function popupHtmlForParcel(key, feature) {
    const owners = safeOwnersWithOriginsForKey(key); // optional enhancement
		const ownerNames = owners.map(o => o.name);

		const ownersText = owners.map(o => {
			const ownerName = o.name || 'Unknown';
			const ownerOrigin = o.originText ? ` — ${o.originText}` : '';
			return `<li>${ownerName}${ownerOrigin}</li>`;
		}).join('\n');
    const ownersHtml = owners.length
      ? `<div class="mt-1">Owners: <ul>${ownersText}</ul></div>`
      : '';

    return `
      <div class="popup">
        <div class="bubble-title"><b>Parcel ${key}</b></div>
        ${ownersHtml}
        <div class="actions mt-2">
          <button class="open-details" data-parcel="${key}">Open details</button>
        </div>
      </div>
    `;
  }

  function highlightParcel(key) {
    // Turn on parcel + related origins
    Store.setActiveParcels([key]);
    Store.setActiveOrigins(safeGetOriginsForParcel(key));

    // Ensure popup opens for visual feedback
    const lyr = byKey.get(key);
    if (lyr) lyr.openPopup();
  }

  function emitParcelClick(key, commit = false) {
    emit('map:click:parcel', { key, commit });
  }

  function onParcelClick(key, ev) {
    highlightParcel(key);
    emitParcelClick(key, isCommitGesture(ev));
  }

  const layer = L.geoJSON(Data.parcelsGeoJSON, {
    style: baseStyle,
    onEachFeature: (f, lyr) => {
      const year = f.properties.map_year || 1874;
      const key = `${year}:${f.properties.parcel_id}`;
      byKey.set(key, lyr);

      lyr.bindPopup(() => popupHtmlForParcel(key, f));
      lyr.on('click', (ev) => onParcelClick(key, ev));

      // Wire popup commit button on open
      lyr.on('popupopen', (ev) => {
        const root = ev?.popup?.getElement?.() || ev?.popup?._container || null;
        if (!root) return;
        const btn = root.querySelector('.open-details[data-parcel]');
        if (btn) {
          btn.addEventListener('click', (e2) => {
            e2.stopPropagation();
            emitParcelClick(key, true);
          }, { once: true });
        }
      });
    }
  }).addTo(map);

  // React to Store updates (active parcels)
  const unsub = Store.subscribe(({ activeParcels }) => {
    byKey.forEach((lyr, key) => {
      const isOn = !!activeParcels && activeParcels.has(key);
      lyr.setStyle(isOn ? activeStyle : baseStyle);
    });
  });

	const api = {
    layer,
    byKey,
    // Fit parcels with zoom clamping; accepts opts = { maxZoom, padding }
    fit(keys, opts = {}) {
      const padding = opts.padding || [20, 20];
      const optMaxZoom = opts.maxZoom; // e.g., 13

      const b = L.latLngBounds([]);
      (keys || []).forEach(k => {
        const lyr = byKey.get(k);
        if (!lyr) return;
        try {
          const lb = lyr.getBounds?.();
          if (lb?.isValid()) b.extend(lb);
        } catch {}
      });
      if (!b.isValid()) return;

      // Slightly inflate tiny bounds so we don't over-zoom on sliver parcels
      const padded = b.pad(0.02); // ~2% expansion; tweak if needed

      const requested = map.getBoundsZoom(padded, false, padding);
      const clamped = clampZoom(map, requested, optMaxZoom);
      dbg({ requested, clamped, mapMax: map.options?.maxZoom, tileMax: getTileLayerMaxZoom(map), optMaxZoom });

      map.setView(padded.getCenter(), clamped);
    },
    destroy() { unsub(); map.removeLayer(layer); }
  };

	PARCELS_API = api;
	return api;
}

// -----------------------------------------------------------------------------
// Panel → Map bridge (react to panel’s CustomEvents)
// -----------------------------------------------------------------------------

// Highlight sets (drives the existing Store subscriptions in both layers)
window.addEventListener('ui:highlight', (e) => {
  const { origins = [], parcels = [] } = e.detail || {};
  Store.setActiveOrigins(origins);
  Store.setActiveParcels(parcels);
});

// Focus/fit each map based on the panel selection type
window.addEventListener('ui:focus', (e) => {
  const d = e.detail || {};
  let origins = [];
  let parcels = [];

  if (d.type === 'family') {
    origins = (Data.familyOriginIndex || {})[d.id] || [];
    parcels = (Data.familyParcelIndex || {})[d.id] || [];
  } else if (d.type === 'origin') {
    origins = [d.id];
    parcels = ((Data.originParcelIndex || {})[d.id]) || [];
  } else if (d.type === 'parcel') {
    parcels = [d.id];
    origins = safeGetOriginsForParcel(d.id);
  }

  if (ORIGINS_API && origins.length) ORIGINS_API.fit(origins, { maxZoom: constants().maxZOrigins });
  if (PARCELS_API && parcels.length) PARCELS_API.fit(parcels, { maxZoom: constants().maxZParcels });
});
