import { Data } from './data.js';

// Simple helpers shared across views
export function baseHref() {
  return document.querySelector('base')?.href || window.location.href;
}
export function urlFor(p) {
  return new URL(p, baseHref()).toString();
}
export function isDescendantOfUSA(handle) {
	let current = Data.origins[handle];
	while (current && current.parent) {
		const parentObj = Data.origins[current.parent];
		if (parentObj.name === 'USA') return true;
		current = Data.origins[current.parent];
	}
	return false;
}
export function getPersonHandleById(id) {
	return Data.personHandleById ? Data.personHandleById[id] || null : null;
}
export function constants() {
	return {
		padding: [20, 20],
		maxZOrigins: 10,
		maxZParcels: 14,
	};
}
