const DATA_BASE = 'data/';

// --- utilities ---------------------------------------------------------------

async function jget(name) {
  try {
    const res = await fetch(DATA_BASE + name, { cache: 'no-store' });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    return null;
  }
}
const byAlpha = (a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' });

function emitHighlight({ origins = [], parcels = [], source = 'panel' } = {}) {
  window.dispatchEvent(new CustomEvent('ui:highlight', { detail: { origins, parcels, source } }));
}
function emitFocus(payload) {
  window.dispatchEvent(new CustomEvent('ui:focus', { detail: payload }));
}

// --- minimal store -----------------------------------------------------------

const Store = (() => {
  let state = {
    tab: 'families',      // 'families' | 'origins' | 'parcels'
    filter: '',
    selection: null,      // { type: 'family'|'origin'|'parcel', id: string }
		followClicks: false,      // new
		autoSwitchTabs: false,    // optional
		review: null             // { type, id, label } or null
  };
  const subs = new Set();
  const get = () => state;
  const set = (patch) => {
    state = { ...state, ...patch };
    subs.forEach(fn => fn(state));
  };
  const subscribe = (fn) => { subs.add(fn); return () => subs.delete(fn); };
  return { get, set, subscribe };
})();

// --- data load ----------------------------------------------------------------

const Data = {
  families: {},                 // families.json
  origins: {},                  // origins.json (handle -> {name,...})
  familyOriginIndex: {},        // family -> [origin handles]
  originFamilyIndex: {},        // origin handle -> [families]
  familyParcelIndex: {},        // family -> [parcel keys]
  parcelFamilyIndex: {},        // parcel key -> [families]
};

async function loadAll() {
  const [
    families,
    origins,
    familyOriginIndex,
    originFamilyIndex,
    familyParcelIndex,
    parcelFamilyIndex
  ] = await Promise.all([
    jget('families.json'),
    jget('origins.json'),
    jget('family_origin_index.json'),
    jget('origin_family_index.json'),
    jget('family_parcel_index.json'),
    jget('parcel_family_index.json')
  ]);

  Data.families = families || {};
  Data.origins = origins || {};
  Data.familyOriginIndex = familyOriginIndex || {};
  Data.originFamilyIndex = originFamilyIndex || {};
  Data.familyParcelIndex = familyParcelIndex || {};
  Data.parcelFamilyIndex = parcelFamilyIndex || {};
}

// --- DOM refs -----------------------------------------------------------------

const el = {
  browser: document.getElementById('browser'),
  list: document.getElementById('browser-list'),
  filter: document.getElementById('browser-filter'),
  count: document.getElementById('browser-count'),
  tabs: Array.from(document.querySelectorAll('.tabs .tab')),
  info: document.getElementById('info-panel'),
};

// --- browser rendering --------------------------------------------------------

function currentCollection() {
  const { tab, filter } = Store.get();
  let items = [];

  if (tab === 'families') {
    items = Object.values(Data.families)
      .map(f => ({ id: f.id, label: f.label || f.id }))
      .sort((a, b) => byAlpha(a.label, b.label));
  } else if (tab === 'origins') {
    items = Object.entries(Data.origins)
      .map(([handle, p]) => ({ id: handle, label: p.name || handle }))
      .sort((a, b) => byAlpha(a.label, b.label));
  } else if (tab === 'parcels') {
    items = Object.keys(Data.parcelFamilyIndex || {})
      .map(k => ({ id: k, label: k }))
      .sort((a, b) => byAlpha(a.label, b.label));
  }

  // simple filter
  const q = (filter || '').trim().toLowerCase();
  if (q) {
    items = items.filter(x => x.label.toLowerCase().includes(q));
  }
  return items;
}

function renderBrowserList() {
  const items = currentCollection();
  el.list.innerHTML = '';
  el.count.textContent = items.length ? `${items.length}` : '';

  const frag = document.createDocumentFragment();
  items.forEach((row, i) => {
    const btn = document.createElement('button');
    btn.className = 'item';
    btn.role = 'option';
    btn.dataset.id = row.id;
    btn.textContent = row.label;
    btn.addEventListener('click', () => {
      const tab = Store.get().tab;
      if (tab === 'families') selectFamily(row.id);
      else if (tab === 'origins') selectOrigin(row.id);
      else selectParcel(row.id);
    });
    // keyboard support
    btn.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        btn.click();
      }
    });
    frag.appendChild(btn);
  });
  el.list.appendChild(frag);
}

// --- info panel ---------------------------------------------------------------

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  children.flat().forEach(c => {
    if (c == null) return;
    node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  });
  return node;
}

function renderInfo() {
  const sel = Store.get().selection;
  el.info.innerHTML = '';

  if (!sel) {
    el.info.appendChild(h('div', { class: 'placeholder' }, 'Select a family, origin, or parcel.'));
    return;
  }

  if (sel.type === 'family') {
    const fam = Data.families[sel.id] || { id: sel.id, label: sel.id, description_md: '' };
    const origins = (Data.familyOriginIndex[fam.id] || []).map(oph => ({
      handle: oph,
      name: Data.origins[oph]?.name || oph
    }));
    const parcels = (Data.familyParcelIndex[fam.id] || []).slice();

    el.info.append(
      h('h2', {}, `Family: ${fam.label || fam.id}`),
      h('h3', {}, 'Origins'),
      h('div', { class: 'tags' },
        origins.length
          ? origins.map(o => h('button', {
              class: 'tag',
              onClick: () => selectOrigin(o.handle),
              title: 'Show origin'
            }, o.name))
          : h('span', {}, 'No origins found.')
      ),
      h('h3', {}, 'Parcels'),
      h('div', { class: 'tags' },
        parcels.length
          ? parcels.map(pk => h('button', {
              class: 'tag',
              onClick: () => selectParcel(pk),
              title: 'Show parcel'
            }, pk))
          : h('span', {}, 'No parcels found.')
      )
    );

    // map highlight side-effect
    emitHighlight({
      origins: origins.map(o => o.handle),
      parcels,
      source: 'panel',
    });
    emitFocus({ type: 'family', id: fam.id });

  } else if (sel.type === 'origin') {
    const name = Data.origins[sel.id]?.name || sel.id;
    const families = (Data.originFamilyIndex[sel.id] || []).slice().sort(byAlpha);
    const parcels = families
      .flatMap(fid => Data.familyParcelIndex[fid] || [])
      .filter(Boolean)
      .sort(byAlpha);

    el.info.append(
      h('h2', {}, `Origin: ${name}`),
      h('h3', {}, 'Families'),
      h('div', { class: 'tags' },
        families.length
          ? families.map(fid => h('button', {
              class: 'tag',
              onClick: () => selectFamily(fid),
              title: 'Show family'
            }, Data.families[fid]?.label || fid))
          : h('span', {}, 'No families found.')
      ),
      h('h3', {}, 'Parcels'),
      h('div', { class: 'tags' },
        parcels.length
          ? Array.from(new Set(parcels)).map(pk => h('button', {
              class: 'tag',
              onClick: () => selectParcel(pk),
              title: 'Show parcel'
            }, pk))
          : h('span', {}, 'No parcels found.')
      )
    );

    emitHighlight({ origins: [sel.id], parcels: Array.from(new Set(parcels)), source: 'panel' });
    emitFocus({ type: 'origin', id: sel.id });

  } else if (sel.type === 'parcel') {
    const families = (Data.parcelFamilyIndex[sel.id] || []).slice().sort(byAlpha);
    const origins = Array.from(new Set(
      families.flatMap(fid => Data.familyOriginIndex[fid] || [])
    ));

    el.info.append(
      h('h2', {}, `Parcel: ${sel.id}`),
      h('h3', {}, 'Families'),
      h('div', { class: 'tags' },
        families.length
          ? families.map(fid => h('button', {
              class: 'tag',
              onClick: () => selectFamily(fid),
              title: 'Show family'
            }, Data.families[fid]?.label || fid))
          : h('span', {}, 'No families found.')
      ),
      h('h3', {}, 'Origins'),
      h('div', { class: 'tags' },
        origins.length
          ? origins.map(oph => h('button', {
              class: 'tag',
              onClick: () => selectOrigin(oph),
              title: 'Show origin'
            }, Data.origins[oph]?.name || oph))
          : h('span', {}, 'No origins found.')
      )
    );

    emitHighlight({ origins, parcels: [sel.id], source: 'panel' });
    emitFocus({ type: 'parcel', id: sel.id });
  }
}

// --- selection API (used by browser + maps) ----------------------------------

function selectFamily(fid) {
  Store.set({ selection: { type: 'family', id: fid } });
  renderInfo();
}
function selectOrigin(oph) {
  Store.set({ selection: { type: 'origin', id: oph } });
  renderInfo();
}
function selectParcel(pk) {
  Store.set({ selection: { type: 'parcel', id: pk } });
  renderInfo();
}

// Expose for your map layers / click handlers:
window.UISelect = { family: selectFamily, origin: selectOrigin, parcel: selectParcel };

// --- wire up browser UI ------------------------------------------------------

function activateTab(tab) {
  Store.set({ tab });
  el.tabs.forEach(b => {
    const isActive = b.dataset.tab === tab;
    b.classList.toggle('is-active', isActive);
    b.setAttribute('aria-selected', String(isActive));
  });
  el.filter.value = '';
  Store.set({ filter: '' });
  renderBrowserList();
}

function initBrowser() {
  // tabs
  el.tabs.forEach(b => b.addEventListener('click', () => activateTab(b.dataset.tab)));

  // filtering
  el.filter.addEventListener('input', () => {
    Store.set({ filter: el.filter.value || '' });
    renderBrowserList();
  });

  // initial render
  activateTab(Store.get().tab);
}

// --- init --------------------------------------------------------------------

(async function init() {
  await loadAll();
  initBrowser();
  renderInfo();
})();

// --- Optional: listen to map clicks (if you dispatch these from your maps) ---
window.addEventListener('map:click:origin', (e) => {
  const handle = e.detail?.handle;
  if (handle) selectOrigin(handle);
});
window.addEventListener('map:click:parcel', (e) => {
  const key = e.detail?.key; // e.g., "1874:32"
  if (key) selectParcel(key);
});
window.addEventListener('map:click:family', (e) => {
  const fid = e.detail?.id;
  if (fid) selectFamily(fid);
});


const toggleFollow = document.getElementById('toggle-follow');
const toggleAuto   = document.getElementById('toggle-autotab');
toggleFollow.addEventListener('change', () => Store.set({ followClicks: toggleFollow.checked }));
if (toggleAuto) toggleAuto.addEventListener('change', () => Store.set({ autoSwitchTabs: toggleAuto.checked }));

const previewStrip = document.getElementById('preview-strip');
const previewText  = document.getElementById('preview-text');
const previewOpen  = document.getElementById('preview-open');
const previewDismiss = document.getElementById('preview-dismiss');

function renderPreview() {
  const p = Store.get().preview;
  if (!p) { previewStrip.hidden = true; return; }
  const kind = p.type.charAt(0).toUpperCase() + p.type.slice(1);
  previewText.textContent = `Previewing: ${kind} — ${p.label}`;
  previewOpen.onclick = () => {
    commitSelection(p.type, p.id, { forceTabSwitch: true });
    Store.set({ preview: null });
    renderPreview();
  };
  previewDismiss.onclick = () => { Store.set({ preview: null }); renderPreview(); };
  previewStrip.hidden = false;
}

function commitSelection(type, id, { forceTabSwitch = false } = {}) {
  const { autoSwitchTabs } = Store.get();
  // Tab policy
  const targetTab = type === 'family' ? 'families' : type === 'origin' ? 'origins' : 'parcels';
  const shouldSwitch = forceTabSwitch || (autoSwitchTabs && Store.get().tab !== targetTab);

  Store.set({ selection: { type, id } });
  renderInfo();

  if (shouldSwitch) {
    activateTab(targetTab);
    // optional pulse to draw attention
    document.querySelector(`.tabs .tab[data-tab="${targetTab}"]`)?.classList.add('tab-pulse');
    setTimeout(() => document.querySelector(`.tabs .tab[data-tab="${targetTab}"]`)?.classList.remove('tab-pulse'), 1200);
  }
}
/*

layer.on('click', (e) => {
  const commit = !!(e.originalEvent && (e.originalEvent.shiftKey || e.originalEvent.metaKey || e.originalEvent.ctrlKey));
  // show bubble as you already do…
  window.dispatchEvent(new CustomEvent('map:click:origin', { detail: { handle: originHandle, commit } }));
});
*/

// In your bubble HTML/JS:
/*
const openBtn = L.DomUtil.create('button', 'open-details');
openBtn.textContent = 'Open details';
openBtn.addEventListener('click', () => {
  window.dispatchEvent(new CustomEvent('map:click:origin', { detail: { handle: originHandle, commit: true } }));
});
*/
