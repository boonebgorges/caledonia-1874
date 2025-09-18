import { loadAllData, Data } from './data.js';
import { buildParcelsLayer, buildOriginsLayer } from './layers.js';
import { Store } from './store.js';

(function mountContainers() {
  const root = document.getElementById('app') || document.body;
  if (!document.getElementById('dual-layout')) {
    const wrap = document.createElement('div');
    wrap.id = 'dual-layout';
    wrap.innerHTML = `
      <div id="controls" class="controls">
        <button id="clearSel" type="button" title="Clear selection">Clear selection</button>
      </div>

			<div class="info-head">
				<div class="info-title" id="info-title">Details</div>
				<div class="info-controls">
					<label class="toggle">
						<input type="checkbox" id="toggle-follow"> Follow map clicks
					</label>
					<!-- optional -->
					<label class="toggle">
						<input type="checkbox" id="toggle-autotab"> Auto-switch tabs
					</label>
				</div>
			</div>

			<div id="preview-strip" class="preview-strip" hidden>
				<span id="preview-text"></span>
				<button id="preview-open" class="linklike">Open details</button>
				<button id="preview-dismiss" class="linklike" aria-label="Dismiss">×</button>
			</div>

      <div id="maps" class="maps">
        <div class="panel">
          <div class="panel-head">Caledonia Parcels</div>
          <div id="mapC" class="map"></div>
        </div>
        <div class="panel">
          <div class="panel-head">Origins</div>
          <div id="mapO" class="map"></div>
        </div>
      </div>`;
    root.appendChild(wrap);
    document.getElementById('clearSel').addEventListener('click', () => Store.clear());
  }
})();

(async function init() {
  // Create maps
  const mapC = L.map('mapC'); // no setView yet — we'll fit bounds
  const mapO = L.map('mapO');

  // Basemaps
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxZoom: 20, attribution: '&copy; OSM' }).addTo(mapC);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxZoom: 20, attribution: '&copy; OSM' }).addTo(mapO);

	const platTiles = L.tileLayer('https://pub-ac84f04214d14c64ba9f968faa86c0c2.r2.dev/1874-v2025-09-02/{z}/{x}/{y}.png', {
		minZoom: 12, maxZoom: 19, opacity: 0.75
	}).addTo(mapC);

	L.control.scale({ imperial: true, metric: true }).addTo(mapC);
	L.control.scale({ imperial: true, metric: true }).addTo(mapO);

  await loadAllData();

  // Layers
  const parcels = buildParcelsLayer(mapC);
  const origins = buildOriginsLayer(mapO);

  // --- Initial extent for Caledonia: parcel polygons ---
  let initBoundsC = null;
  try { initBoundsC = parcels.layer.getBounds(); mapC.fitBounds(initBoundsC, { padding: [16,16] }); } catch(e) {}

  // --- Initial extent for Origins: compute from origin lat/lon ---
  const pts = Object.values(Data.origins || {})
    .filter(p => Number.isFinite(p?.lat) && Number.isFinite(p?.lon))
    .map(p => L.latLng(p.lat, p.lon));
  let initBoundsO = null;
  if (pts.length) {
    initBoundsO = L.latLngBounds(pts);
    mapO.fitBounds(initBoundsO, { padding: [16,16], maxZoom: 8 }); // start fairly zoomed out
  } else {
    mapO.setView([44.2934, -88.8006], 5); // fallback
  }

  // --- Selection-based recentering (no continuous sync) ---
  const PADDING = [20, 20];
  const MAX_Z_ORIGINS = 11; // don’t over-zoom pins
  const MAX_Z_PARCELS  = 15;

  Store.subscribe(({ activeParcels, activeOrigins }) => {
    // If origins are active, recenter Origins map to those markers
    if (activeOrigins.size) {
      const bounds = boundsFromOriginHandles(activeOrigins, origins.registry);
      if (bounds) fitToBoundsOrPoint(mapO, bounds, { padding: PADDING, maxZoom: MAX_Z_ORIGINS });
    }

    // If parcels are active, recenter Caledonia map to those features
    if (activeParcels.size) {
      const bounds = boundsFromParcelKeys(activeParcels, parcels.byKey);
      if (bounds) fitToBoundsOrPoint(mapC, bounds, { padding: PADDING, maxZoom: MAX_Z_PARCELS });
    }

    // If selection is cleared, you can optionally reset:
    // else if (!activeOrigins.size) mapO.fitBounds(initBoundsO, { padding: PADDING });
    // else if (!activeParcels.size) mapC.fitBounds(initBoundsC, { padding: PADDING });
  });

  // Helpers
  function boundsFromOriginHandles(set, registry) {
    const latlngs = [];
    set.forEach(h => {
      const m = registry.get(h);
      const ll = m?.getLatLng?.();
      if (ll) latlngs.push(ll);
    });
    return latlngs.length ? L.latLngBounds(latlngs) : null;
  }

  function boundsFromParcelKeys(set, byKey) {
    let b = null;
    set.forEach(k => {
      const lyr = byKey.get(k);
      if (!lyr) return;
      const lb = lyr.getBounds?.();
      if (lb && lb.isValid()) b = b ? b.extend(lb) : L.latLngBounds(lb.getSouthWest(), lb.getNorthEast());
    });
    return b;
  }

  function fitToBoundsOrPoint(map, bounds, opts = {}) {
    // If bounds collapse to a point, do setView; else fitBounds.
    if (bounds.getSouthWest().equals(bounds.getNorthEast())) {
      map.setView(bounds.getCenter(), opts.maxZoom ?? map.getZoom(), { animate: true });
    } else {
      map.fitBounds(bounds, opts);
    }
  }
})();
