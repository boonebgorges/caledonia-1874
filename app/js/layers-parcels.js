import { Store } from './store.js';
import { Data, ownersWithOriginsForKey, getOriginsForParcel } from './data.js';

export function buildParcelsLayer(map) {
  const byKey = new Map();

  const baseStyle = { color: '#333', weight: 2, fillOpacity: 0.15 };
  const activeStyle = { color: '#111', weight: 3, fillOpacity: 0.35 };

  const layer = L.geoJSON(Data.parcelsGeoJSON, {
    style: baseStyle,
    onEachFeature: (f, lyr) => {
      const year = f.properties.map_year || 1874;
      const key = `${year}:${f.properties.parcel_id}`;
      byKey.set(key, lyr);

      const owners = ownersWithOriginsForKey(key);
      const ownersHtml = owners.length
        ? `<ul class="owners">${owners.map(o => `<li>${o.name} — ${o.originText}${o.method ? ` <span class="method">[${o.method}]</span>` : ''}</li>`).join('')}</ul>`
        : '<i>No linked persons</i>';

      const title = `<b>${f.properties.parcel_id}</b>${f.properties.plss_desc ? ` (${f.properties.plss_desc})` : ''}`;
      lyr.bindPopup(`${title}<br><b>Owners:</b>${ownersHtml}`);

      lyr.on('click', () => {
        Store.setActiveParcels([key]);
				Store.setActiveOrigins(getOriginsForParcel(key));
      });
    }
  }).addTo(map);

  const unsub = Store.subscribe(({ activeParcels }) => {
    byKey.forEach((lyr, key) => {
      lyr.setStyle(activeParcels.has(key) ? activeStyle : baseStyle);
      if (activeParcels.has(key)) lyr.openPopup();
    });
  });

  return { layer, byKey, destroy() { unsub(); map.removeLayer(layer); } };
}
