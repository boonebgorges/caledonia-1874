import { loadAllData } from './data.js';
import { buildParcelsLayer } from './layers-parcels.js';
import { buildOriginsLayer } from './layers-origins.js';

(async function init() {
  const map = L.map('map').setView([44.2934, -88.8006], 5);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxZoom: 20, attribution: '&copy; OSM' }).addTo(map);

  await loadAllData();

  // Show both layers in the Origins view to allow cross-highlighting
  buildParcelsLayer(map);
  buildOriginsLayer(map);

  // Optional: start zoomed out for broader context
})();
