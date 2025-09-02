import { Store } from './store.js';
import { Data, placeLineage } from './data.js';

export function buildOriginsLayer(map) {
  const registry = new Map(); // handle -> marker

	const hasCoords = p => Number.isFinite(p?.lat) && Number.isFinite(p?.lon);

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
        .bindPopup(() => popupHtml(handle))
        .on('click', () => selectOrigin(handle));
      registry.set(handle, m);
      return m;
    });

  const group = L.layerGroup(markers).addTo(map);

  const unsub = Store.subscribe(({ activeOrigins }) => {
    registry.forEach((marker, handle) => {
      const el = marker.getElement();
      if (el) el.classList.toggle('active', activeOrigins.has(handle));
    });
  });

  function selectOrigin(handle) {
    const parcelKeys = (Data.originParcelIndex || {})[handle] || [];
    Store.setActiveOrigins([handle]);
    Store.setActiveParcels(parcelKeys);
    // Open the origin popup explicitly
    const mk = registry.get(handle);
    if (mk) mk.openPopup();
  }

  function popupHtml(handle) {
    const p = (Data.origins || {})[handle];
    if (!p) return '<i>Unknown place</i>';
    const lin = placeLineage(handle, { stopTypes: ['Country'] });
    const linked = ((Data.originParcelIndex || {})[handle] || [])
      .map(k => `<li data-parcel="${k}">${k}</li>`).join('');
    return `<b>${p.name || handle}</b><br><small>${lin?.text || ''}</small><ul class="linked-parcels">${linked}</ul>`;
  }

  return { group, registry, destroy() { unsub(); map.removeLayer(group); } };
}
