import { loadAllData } from './data.js';
import { buildParcelsLayer } from './layers-parcels.js';

(async function init() {
  const map = L.map('map').setView([44.2934, -88.8006], 13);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxZoom: 20, attribution: '&copy; OSM' }).addTo(map);

  // If you have historical tiles:
  // L.tileLayer('tiles/{z}/{x}/{y}.png', { minZoom: 12, maxZoom: 19, opacity: 0.75 }).addTo(map);

  await loadAllData();
  const parcels = buildParcelsLayer(map);

  try { map.fitBounds(parcels.layer.getBounds(), { padding: [16, 16] }); } catch (e) {}
})();
