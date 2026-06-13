# Perch — find the nearest place to sit

A free, no-install web app (PWA) that points you to the nearest public **bench** — plus **food,
parks, zoos, views, playgrounds and culture** — with a **live 3D compass**. Built accessibility-first
for anyone who can't always make it to the next rest.

**No app store. No login. No ads. Your location never leaves your phone.**

👉 **Live:** https://sagek17.github.io/perch/

## Features

- Live 3D compass (WebGL) that sweeps to the nearest spot; flat-arrow fallback on older devices.
- 7 categories — Seats · Food · Parks · Zoos · Views · Play · Culture.
- **Surprise me** — a slot-machine reveal that picks a random spot ("where do we eat?").
- **AR view** — your camera + compass point you there (sensor-based, no cloud).
- **Dinner tools** — split the bill, or spin "Who pays?".
- **Meet here** — share a QR/link to the exact spot.
- Compass shop with 12 designs. Independent, family-owned eateries get a "Local" badge.

## How it's built

100% client-side static site — vanilla HTML/CSS/JS, no build step, no backend. Map data from
[OpenStreetMap](https://www.openstreetmap.org/copyright) via the free Overpass API; maps by
[Leaflet](https://leafletjs.com); 3D by [Three.js](https://threejs.org). Hosted free on GitHub Pages.

## License

[MIT](LICENSE.txt). Map data © OpenStreetMap contributors (ODbL). Built with AI assistance and
verified against live data.
