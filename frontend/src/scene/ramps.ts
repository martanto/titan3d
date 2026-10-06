// Colour ramps for flow fields: Crameri Scientific Colour Maps, 256 samples.
// Each quantity gets its own map family so modes are never confused:
//   depth → batlow   (general-purpose sequential, dark low end visible on light terrain)
//   speed → imola    (blue → yellow-green)
//   max   → lajolla, reversed (pale yellow → red → dark brown; maximum-depth envelope)
import * as THREE from "three";
import { BATLOW, IMOLA, LAJOLLA } from "./cmaps";

export type FlowMode = "depth" | "speed" | "max";

function reversed(hex: string): string {
  let out = "";
  for (let i = hex.length - 6; i >= 0; i -= 6) out += hex.slice(i, i + 6);
  return out;
}

const HEX: Record<FlowMode, string> = { depth: BATLOW, speed: IMOLA, max: reversed(LAJOLLA) };

export const RAMP_NAME: Record<FlowMode, string> = {
  depth: "batlow",
  speed: "imola",
  max: "lajolla (reversed)",
};

export const RAMP_CITATION =
  "Colour maps: Crameri (2018), Scientific colour maps, doi:10.5281/zenodo.1243862";

function rgbAt(mode: FlowMode, i: number): [number, number, number] {
  const s = HEX[mode];
  const o = i * 6;
  return [parseInt(s.slice(o, o + 2), 16), parseInt(s.slice(o + 2, o + 4), 16), parseInt(s.slice(o + 4, o + 6), 16)];
}

export function rampBytes(mode: FlowMode): Uint8Array {
  const d = new Uint8Array(256 * 4);
  for (let i = 0; i < 256; i++) {
    d.set([...rgbAt(mode, i), 255], i * 4);
  }
  return d;
}

export function rampTexture(mode: FlowMode): THREE.DataTexture {
  const t = new THREE.DataTexture(rampBytes(mode), 256, 1, THREE.RGBAFormat);
  t.colorSpace = THREE.SRGBColorSpace;
  t.magFilter = t.minFilter = THREE.LinearFilter;
  t.needsUpdate = true;
  return t;
}

/** CSS gradient for colourbars, sampled from the same table as the texture. */
export function rampCss(mode: FlowMode, direction = "90deg"): string {
  const stops = [];
  for (let k = 0; k <= 16; k++) {
    const i = Math.round((k / 16) * 255);
    const [r, g, b] = rgbAt(mode, i);
    stops.push(`rgb(${r} ${g} ${b}) ${(k / 16) * 100}%`);
  }
  return `linear-gradient(${direction}, ${stops.join(", ")})`;
}
