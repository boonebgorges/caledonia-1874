// Minimal evented selection store
export const Store = (() => {
  const state = { activeParcels: new Set(), activeOrigins: new Set() };
  const subs = new Set();
  const notify = () => subs.forEach(fn => fn(state));

  return {
    get: () => state,
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
    setActiveParcels(keys, { merge = false } = {}) {
      state.activeParcels = merge ? new Set([...state.activeParcels, ...keys]) : new Set(keys);
      notify();
    },
    setActiveOrigins(handles, { merge = false } = {}) {
      state.activeOrigins = merge ? new Set([...state.activeOrigins, ...handles]) : new Set(handles);
      notify();
    },
    clear() { state.activeParcels.clear(); state.activeOrigins.clear(); notify(); },
  };
})();
