// Longitude/latitude ↔ UTM for grids reported as "EPSG:326zz" / "EPSG:327zz".
import proj4 from "proj4";

const cache = new Map<string, proj4.Converter>();

function converter(crs: string): proj4.Converter {
  let c = cache.get(crs);
  if (!c) {
    const m = /^EPSG:32([67])(\d{2})$/.exec(crs);
    if (!m) throw new Error(`Unsupported CRS ${crs}`);
    const south = m[1] === "7" ? " +south" : "";
    c = proj4("EPSG:4326", `+proj=utm +zone=${Number(m[2])}${south} +datum=WGS84 +units=m +no_defs`);
    cache.set(crs, c);
  }
  return c;
}

export function toUtm(crs: string, lon: number, lat: number): [number, number] {
  const [x, y] = converter(crs).forward([lon, lat]);
  return [x, y];
}

export function toLonLat(crs: string, x: number, y: number): [number, number] {
  const [lon, lat] = converter(crs).inverse([x, y]);
  return [lon, lat];
}

/** UTM zone of a point, matching backend `utm_crs_for`. */
export function utmCrsFor(lon: number, lat: number): string {
  const zone = (Math.floor((lon + 180) / 6) % 60) + 1;
  return `EPSG:${(lat < 0 ? 32700 : 32600) + zone}`;
}
