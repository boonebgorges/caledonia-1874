// Simple helpers shared across views
export function baseHref() {
  return document.querySelector('base')?.href || window.location.href;
}
export function urlFor(p) {
  return new URL(p, baseHref()).toString();
}
