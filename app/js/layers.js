// app/js/layers.js
// 2-space indent, framework-free Leaflet utilities for Origins + Parcels.
// Implements "highlight on click" + panel preview/commit via custom events.

import { Store } from './store.js';
import { Data, placeLineage, getOriginsForParcel, ownersWithOriginsForKey } from './data.js';

// -----------------------------------------------------------------------------
// Shared helpers
// -----------------------------------------------------------------------------

function isCommitGesture(ev) {
  const oe = ev?.originalEvent;
  return !!(oe?.shiftKey || oe?.metaKey || oe?.ctrlKey);
}

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

    const linkedParcels = ((Data.originParcelIndex || {})[handle] || [])
      .map(k => `<li data-parcel="${k}">${k}</li>`).join('');

    return `
      <div class="popup">
        <div class="bubble-title"><b>${p.name || handle}</b></div>
        ${lineage?.text ? `<div class="subtle"><small>${lineage.text}</small></div>` : ''}
        ${linkedParcels
          ? `<div class="mt-2"><div><small>Parcels</small></div><ul class="linked-parcels">${linkedParcels}</ul></div>`
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

      // Clicks on linked parcels list (preview + optional commit)
      root.querySelectorAll('ul.linked-parcels li[data-parcel]').forEach(li => {
        li.addEventListener('click', (ev2) => {
          ev2.stopPropagation();
          const key = li.getAttribute('data-parcel');
          // Cross-highlight immediately
          Store.setActiveParcels([key]);
          Store.setActiveOrigins(safeGetOriginsForParcel(key));
          // Preview in panel; user can commit from panel strip
          emit('map:click:parcel', { key, commit: false });
        }, { once: true });
      });
    });
  }

  // Create markers
  const markers = Object.entries(Data.origins || {})
    .filter(([, p]) => hasCoords(p))
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

  return {
    group,
    registry,
    fit(handles) {
      const pts = (handles || []).map(h => {
        const p = Data.origins[h];
        return p && [p.lat, p.lon];
      }).filter(Boolean);
      if (!pts.length) return;
      map.fitBounds(L.latLngBounds(pts), { padding: [20, 20] });
    },
    destroy() { unsub(); map.removeLayer(group); }
  };
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
      if (isOn) lyr.openPopup();
    });
  });

  return {
    layer,
    byKey,
    fit(keys) {
      const bounds = L.latLngBounds([]);
      (keys || []).forEach(k => {
        const lyr = byKey.get(k);
        if (!lyr) return;
        try { bounds.extend(lyr.getBounds()); } catch {}
      });
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [20, 20] });
    },
    destroy() { unsub(); map.removeLayer(layer); }
  };
}
