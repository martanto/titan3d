// three.js scene for terrain previews and flow playback.
//
// World units are kilometres: X = east, Z = −north, Y = (bed − zmin)·vex.
// Terrain and flow heights are computed in the vertex shader from a bed
// texture, so vertical exaggeration is a uniform and the CPU never rewrites
// vertex buffers. Flow playback streams the two frames around the current time
// into RG8 textures (R = depth, G = speed) and interpolates on the GPU.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { Line2 } from "three/addons/lines/Line2.js";
import { LineGeometry } from "three/addons/lines/LineGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import type { GridMeta, Result, Terrain } from "../data/bundle";
import { depthTable, speedTable } from "../data/bundle";
import { type FlowMode, rampTexture } from "./ramps";

export interface PickInfo {
  x: number; // grid CRS easting [m]
  y: number; // grid CRS northing [m]
  z: number; // bed elevation [m]
  k: number; // nearest cell index
}

export interface Marker {
  kind: "pile" | "flux";
  x: number;
  y: number;
  radius: number;
  selected?: boolean;
  pin?: boolean; // vertical pin at the centre (default true)
}

export type ViewKind = "plan" | "oblique";
export type SurfaceKind = "natural" | "relief";

export interface DomainBox {
  west: number;
  south: number;
  east: number;
  north: number;
}

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const TERRAIN_VS = /* glsl */ `
in vec2 cell;
in float valid;
uniform sampler2D uBed;
uniform ivec2 uSize;
uniform float uVex, uZmin, uDx;
out float vE;
out float vValid;
out vec3 vN;
out float vD;
out float vSlope;
out float vCurv;
out vec2 vXY;
float bedAt(ivec2 c) { return texelFetch(uBed, clamp(c, ivec2(0), uSize - 1), 0).r; }
void main() {
  ivec2 c = ivec2(cell);
  float b = bedAt(c);
  float bx = (bedAt(c + ivec2(1, 0)) - bedAt(c - ivec2(1, 0))) / (2.0 * uDx);
  float by = (bedAt(c + ivec2(0, 1)) - bedAt(c - ivec2(0, 1))) / (2.0 * uDx);
  vN = normalize(vec3(-bx * uVex, 1.0, by * uVex));
  vSlope = length(vec2(bx, by));
  // two-scale Laplacian, normalised per cell: > 0 in valleys/gullies, < 0 on ridges
  float l1 = bedAt(c + ivec2(1, 0)) + bedAt(c - ivec2(1, 0)) + bedAt(c + ivec2(0, 1)) + bedAt(c - ivec2(0, 1)) - 4.0 * b;
  float l2 = bedAt(c + ivec2(2, 0)) + bedAt(c - ivec2(2, 0)) + bedAt(c + ivec2(0, 2)) + bedAt(c - ivec2(0, 2)) - 4.0 * b;
  vCurv = (0.6 * l1 + 0.4 * l2 / 4.0) / uDx;
  vXY = vec2(position.x, -position.z) * 1000.0;
  vE = b;
  vValid = valid;
  vec4 mv = modelViewMatrix * vec4(position.x, (b - uZmin) * uVex / 1000.0, position.z, 1.0);
  vD = -mv.z;
  gl_Position = projectionMatrix * mv;
}`;

const TERRAIN_FS = /* glsl */ `
precision highp float;
uniform vec3 uScene, uLight, uLow, uMid, uHigh, uLine;
uniform float uFogNear, uFogFar, uZmin, uZmax, uContours, uInterval, uSurface, uTree, uMute;
in float vE;
in float vValid;
in vec3 vN;
in float vD;
in float vSlope;
in float vCurv;
in vec2 vXY;
out vec4 fragColor;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float vnoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

// Synthetic natural-colour relief derived from the DEM alone (not imagery):
// vegetation below a treeline, bare rock on steep slopes, ash towards the summit,
// darker incised gullies, lighter ridges, fine grain.
vec3 naturalColour(float rel) {
  float slopeDeg = degrees(atan(vSlope));
  float n1 = vnoise(vXY / 220.0);
  float n2 = vnoise(vXY / 55.0);
  float grain = hash(floor(vXY / 9.0));
  float concave = smoothstep(0.02, 0.22, vCurv);
  float ridge = smoothstep(0.02, 0.22, -vCurv);
  float veg = 1.0 - smoothstep(uTree - 180.0, uTree + 140.0, vE + (n1 - 0.5) * 160.0);
  veg *= 1.0 - smoothstep(36.0, 48.0, slopeDeg + (n2 - 0.5) * 6.0);
  vec3 forest = mix(vec3(0.22, 0.36, 0.15), vec3(0.34, 0.49, 0.22), 0.65 * n1 + 0.35 * n2);
  forest = mix(forest, vec3(0.45, 0.53, 0.30), ridge * 0.5);
  forest = mix(forest, vec3(0.09, 0.17, 0.08), concave * 0.85);
  vec3 rock = mix(vec3(0.40, 0.37, 0.33), vec3(0.58, 0.55, 0.50), n2);
  vec3 ash = mix(vec3(0.80, 0.78, 0.74), vec3(0.92, 0.91, 0.88), n1);
  vec3 bare = mix(rock, ash, smoothstep(uTree + 250.0, uTree + 650.0, vE));
  bare = mix(bare, bare * 0.62, concave * 0.6);
  vec3 col = mix(bare, forest, veg);
  return col * (0.9 + 0.18 * grain);
}

void main() {
  if (vValid < 0.5) discard;
  float t = clamp((vE - uZmin) / max(uZmax - uZmin, 1.0), 0.0, 1.0);
  vec3 n = normalize(vN);
  float sh = clamp(dot(n, uLight), 0.0, 1.0);
  vec3 col;
  if (uSurface > 0.5) {
    vec3 nat = naturalColour(t);
    // under data layers the vegetation is desaturated and lightened so no colour-map hue collides with it
    float lum = dot(nat, vec3(0.299, 0.587, 0.114));
    nat = mix(nat, vec3(lum) * 1.35 + 0.1, uMute);
    col = nat * (0.26 + 1.02 * sh) + vec3(0.012, 0.016, 0.022);
  } else {
    vec3 base = t < 0.5 ? mix(uLow, uMid, t * 2.0) : mix(uMid, uHigh, (t - 0.5) * 2.0);
    col = base * (0.30 + 0.92 * sh);
  }
  if (uContours > 0.5) {
    float c = vE / uInterval;
    float f = abs(fract(c - 0.5) - 0.5) / max(fwidth(c), 1e-4);
    float major = step(fract((vE + 1.0) / (uInterval * 5.0)), 0.205);
    float line = 1.0 - min(f / (major > 0.5 ? 1.3 : 0.8), 1.0);
    col = mix(col, uLine, line * (major > 0.5 ? 0.42 : 0.18));
  }
  float fog = smoothstep(uFogNear, uFogFar, vD);
  fragColor = vec4(mix(col, uScene, fog), 1.0);
}`;

const FLOW_VS = /* glsl */ `
in vec2 cell;
uniform sampler2D uBed, uF0, uF1, uHm;
uniform ivec2 uSize;
uniform float uVex, uZmin, uW, uHmax, uVmax, uBoost, uMode;
out float vH;
out float vS;
out float vM;
out vec3 vP;
out float vD;
void main() {
  ivec2 c = ivec2(cell);
  float b = texelFetch(uBed, c, 0).r;
  vec2 f0 = texelFetch(uF0, c, 0).rg;
  vec2 f1 = texelFetch(uF1, c, 0).rg;
  float h = mix(f0.r * f0.r, f1.r * f1.r, uW) * uHmax;
  float s = mix(f0.g, f1.g, uW) * uVmax;
  float hm = texelFetch(uHm, c, 0).r;
  float m = hm * hm * uHmax;
  float show = uMode > 1.5 ? m : h;
  vH = h; vS = s; vM = m;
  float y = b - uZmin + show + (uBoost - 1.0) * min(show, 10.0) + 0.3;
  vec4 mv = modelViewMatrix * vec4(position.x, y * uVex / 1000.0, position.z, 1.0);
  vP = mv.xyz;
  vD = -mv.z;
  gl_Position = projectionMatrix * mv;
}`;

const FLOW_FS = /* glsl */ `
precision highp float;
uniform sampler2D uRamp;
uniform float uMode, uHmax, uVmax, uEnvMax, uDepthMax, uFogNear, uFogFar, uOutline;
uniform vec3 uScene, uLight, uInk;
in float vH;
in float vS;
in float vM;
in vec3 vP;
in float vD;
out vec4 fragColor;
void main() {
  float show = uMode > 1.5 ? vM : vH;
  float thr = uMode > 1.5 ? 0.1 : 0.05;
  if (show < thr) discard;
  float v = uMode < 0.5 ? sqrt(vH / uDepthMax) : (uMode < 1.5 ? vS / uVmax : sqrt(vM / uEnvMax));
  vec3 col = texture(uRamp, vec2(clamp(v, 0.0, 1.0), 0.5)).rgb;
  vec3 n = normalize(cross(dFdx(vP), dFdy(vP)));
  vec3 l = normalize((viewMatrix * vec4(uLight, 0.0)).xyz);
  float sh = clamp(dot(n, l), 0.0, 1.0);
  vec3 r = reflect(-l, n);
  float sp = pow(clamp(dot(r, normalize(-vP)), 0.0, 1.0), 24.0) * 0.16;
  col = col * (0.5 + 0.62 * sh) + sp;
  // crisp 1 px paper-coloured line at the threshold contour (outside every colour map's range)
  float px = (show - thr) / max(fwidth(show), 1e-5);
  float line = 1.0 - clamp(px - 0.5, 0.0, 1.0);
  // plan view only: in 3D the hillshade already separates the flow and the line would stipple
  col = mix(col, uInk, line * 0.9 * uOutline);
  // soft edge between cells instead of a hard stepped cut-off
  float a = 0.96 * smoothstep(thr, thr * 1.6, show + 0.6 * fwidth(show));
  float fog = smoothstep(uFogNear, uFogFar, vD);
  fragColor = vec4(mix(col, uScene, fog), a);
}`;

interface GridGeom {
  geometry: THREE.BufferGeometry;
  meta: GridMeta;
}

function gridGeometry(meta: GridMeta, cx: number, cy: number, valid?: Uint8Array): GridGeom {
  const { nx, ny, dx, x0, y0 } = meta;
  const n = nx * ny;
  const pos = new Float32Array(n * 3);
  const cell = new Float32Array(n * 2);
  const val = new Float32Array(n);
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const k = j * nx + i;
      pos[3 * k] = (x0 + i * dx - cx) / 1000;
      pos[3 * k + 2] = -(y0 + j * dx - cy) / 1000;
      cell[2 * k] = i;
      cell[2 * k + 1] = j;
      val[k] = valid ? valid[k] : 1;
    }
  }
  const index = new Uint32Array((nx - 1) * (ny - 1) * 6);
  let p = 0;
  for (let j = 0; j < ny - 1; j++) {
    for (let i = 0; i < nx - 1; i++) {
      const a = j * nx + i;
      const b = a + 1;
      const c = a + nx;
      const d = c + 1;
      index.set([a, b, c, b, d, c], p); // counter-clockwise from above (Z = −north)
      p += 6;
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("cell", new THREE.BufferAttribute(cell, 2));
  g.setAttribute("valid", new THREE.BufferAttribute(val, 1));
  g.setIndex(new THREE.BufferAttribute(index, 1));
  // heights live in the shader; give culling a generous box
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 1, 0), Math.hypot(nx * dx, ny * dx) / 1000);
  return { geometry: g, meta };
}

function bedTexture(meta: GridMeta, bed: Float32Array): THREE.DataTexture {
  const t = new THREE.DataTexture(bed, meta.nx, meta.ny, THREE.RedFormat, THREE.FloatType);
  t.minFilter = t.magFilter = THREE.NearestFilter;
  t.needsUpdate = true;
  return t;
}

export class FlowScene {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly persp = new THREE.PerspectiveCamera(36, 1, 0.05, 400);
  readonly ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 2000);
  readonly controls: OrbitControls;
  view: ViewKind = "plan";
  /** Skip rendering while the stage is hidden (e.g. on the System page). */
  paused = false;
  surface: SurfaceKind = "natural";
  private contours = true;
  private mute = 0;
  private plan = { cx: 0, cz: 0, halfH: 5 };
  private aspect = 1;
  private fogRange: [number, number] = [10, 30];
  private canvas: HTMLCanvasElement;
  private terrainMesh?: THREE.Mesh;
  private flowMesh?: THREE.Mesh;
  private overlays = new THREE.Group();
  private grid?: GridMeta;
  private bed?: Float32Array;
  private result?: Result;
  private center = { x: 0, y: 0 };
  private vex = 1;
  private frameKeys: [number, number] = [-1, -1];
  private frameTex?: [THREE.DataTexture, THREE.DataTexture];
  private dTab: Float32Array = new Float32Array(256);
  private sTab: Float32Array = new Float32Array(256);
  private markers: Marker[] = [];
  private domain?: DomainBox;
  private lineMats: LineMaterial[] = [];
  private tickers = new Set<(dt: number) => void>();
  private shared = {
    uScene: { value: new THREE.Color() },
    uLight: { value: new THREE.Vector3(-0.55, 0.72, -0.42).normalize() },
    uFogNear: { value: 10 },
    uFogFar: { value: 30 },
    uVex: { value: 1 },
  };
  private theme = {
    low: new THREE.Color(),
    mid: new THREE.Color(),
    high: new THREE.Color(),
    line: new THREE.Color(),
    accent: new THREE.Color(),
    flux: new THREE.Color(),
    domain: new THREE.Color(),
  };
  readonly ramps: Record<FlowMode, THREE.DataTexture> = {
    depth: rampTexture("depth"),
    speed: rampTexture("speed"),
    max: rampTexture("max"),
  };

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.controls = new OrbitControls(this.persp, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI * 0.47;
    this.scene.add(this.overlays);
    this.readTheme();
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => this.readTheme());
    new MutationObserver(() => this.readTheme()).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement ?? canvas);
    this.installPlanControls();
    this.setView("plan");
    this.resize();
    let last = performance.now();
    this.renderer.setAnimationLoop((now) => {
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      if (this.paused) return;
      for (const f of this.tickers) f(dt);
      if (this.view === "oblique") this.controls.update();
      this.renderer.render(this.scene, this.camera);
    });
  }

  onTick(f: (dt: number) => void): () => void {
    this.tickers.add(f);
    return () => this.tickers.delete(f);
  }

  readTheme(): void {
    this.shared.uScene.value.set(css("--scene") || "#dde2da");
    this.theme.low.set(css("--terrain-low") || "#8fa77c");
    this.theme.mid.set(css("--terrain-mid") || "#c4b48a");
    this.theme.high.set(css("--terrain-high") || "#efebe3");
    this.theme.line.set(css("--contour") || "#3b4440");
    this.theme.accent.set(css("--pile") || "#15181c");
    this.theme.flux.set(css("--vent") || "#1d5a6c");
    this.theme.domain.set(css("--fg") || "#1c2220");
    const flowU = (this.flowMesh?.material as THREE.ShaderMaterial | undefined)?.uniforms;
    if (flowU) (flowU.uInk.value as THREE.Color).set(css("--panel") || "#ffffff");
    this.renderer.setClearColor(this.shared.uScene.value);
    this.rebuildOverlays();
  }

  private resize(): void {
    const el = this.canvas.parentElement ?? this.canvas;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    this.renderer.setSize(r.width, r.height, false);
    this.aspect = r.width / r.height;
    this.persp.aspect = this.aspect;
    this.persp.updateProjectionMatrix();
    this.updateOrtho();
    for (const m of this.lineMats) m.resolution.set(r.width, r.height);
  }

  // ------------------------------------------------------------- terrain
  setTerrain(t: Terrain, valid?: Uint8Array, refit = true): void {
    this.clearTerrain();
    this.grid = t.meta;
    this.bed = t.bed;
    const m = t.meta;
    this.center = { x: m.x0 + ((m.nx - 1) * m.dx) / 2, y: m.y0 + ((m.ny - 1) * m.dx) / 2 };
    const { geometry } = gridGeometry(m, this.center.x, this.center.y, valid);
    const relief = m.zmax - m.zmin;
    const interval = relief > 2500 ? 100 : relief > 800 ? 50 : 20;
    const mat = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: TERRAIN_VS,
      fragmentShader: TERRAIN_FS,
      uniforms: {
        ...this.shared,
        uBed: { value: bedTexture(m, t.bed) },
        uSize: { value: new THREE.Vector2(m.nx, m.ny) },
        uDx: { value: m.dx },
        uZmin: { value: m.zmin },
        uZmax: { value: m.zmax },
        uContours: { value: this.contours ? 1 : 0 },
        uInterval: { value: interval },
        uSurface: { value: this.surface === "natural" ? 1 : 0 },
        uMute: { value: this.mute },
        // treeline for the natural surface: 78 % of the relief (≈ 2,900 m on Semeru)
        uTree: { value: m.zmin + 0.78 * relief },
        uLow: { value: this.theme.low },
        uMid: { value: this.theme.mid },
        uHigh: { value: this.theme.high },
        uLine: { value: this.theme.line },
      },
    });
    this.terrainMesh = new THREE.Mesh(geometry, mat);
    this.terrainMesh.frustumCulled = false;
    this.scene.add(this.terrainMesh);
    if (refit) this.fit();
    this.rebuildOverlays();
  }

  get contourInterval(): number {
    const u = (this.terrainMesh?.material as THREE.ShaderMaterial | undefined)?.uniforms;
    return u ? (u.uInterval.value as number) : 50;
  }

  private clearTerrain(): void {
    this.clearFlow();
    if (this.terrainMesh) {
      this.scene.remove(this.terrainMesh);
      this.terrainMesh.geometry.dispose();
      const mat = this.terrainMesh.material as THREE.ShaderMaterial;
      (mat.uniforms.uBed.value as THREE.Texture).dispose();
      mat.dispose();
      this.terrainMesh = undefined;
    }
  }

  fit(): void {
    const m = this.grid;
    if (!m) return;
    const w = (m.nx * m.dx) / 1000;
    const h = (m.ny * m.dx) / 1000;
    const R = Math.max(w, h);
    const relief = ((m.zmax - m.zmin) * this.vex) / 1000;
    this.controls.target.set(0, relief * 0.35, 0);
    this.persp.position.set(R * 0.42, relief + R * 0.55, R * 0.78);
    this.persp.near = R / 400;
    this.persp.far = R * 8;
    this.persp.updateProjectionMatrix();
    this.plan = { cx: 0, cz: 0, halfH: Math.max(h / 2, w / 2 / this.aspect) * 1.04 };
    this.ortho.position.set(0, relief + R * 2, 0);
    this.ortho.far = relief + R * 4;
    this.updateOrtho();
    this.controls.minDistance = R * 0.08;
    this.controls.maxDistance = R * 2.6;
    this.fogRange = [R * 1.3, R * 3.2];
    this.applyFog();
    this.controls.update();
  }

  private applyFog(): void {
    // a plan view is a map: no aerial perspective
    const [near, far] = this.view === "plan" ? [1e6, 2e6] : this.fogRange;
    this.shared.uFogNear.value = near;
    this.shared.uFogFar.value = far;
  }

  get camera(): THREE.Camera {
    return this.view === "plan" ? this.ortho : this.persp;
  }

  setView(v: ViewKind): void {
    this.view = v;
    this.controls.enabled = v === "oblique";
    this.canvas.style.cursor = v === "plan" ? "crosshair" : "grab";
    this.applyFog();
    const fu = (this.flowMesh?.material as THREE.ShaderMaterial | undefined)?.uniforms;
    if (fu) fu.uOutline.value = v === "plan" ? 1 : 0;
  }

  private updateOrtho(): void {
    const { cx, cz, halfH } = this.plan;
    const halfW = halfH * this.aspect;
    // camera looks straight down with north (-Z) at the top of the screen
    this.ortho.position.x = 0;
    this.ortho.position.z = 0;
    this.ortho.up.set(0, 0, -1);
    this.ortho.lookAt(0, -1e3, 0);
    this.ortho.left = cx - halfW;
    this.ortho.right = cx + halfW;
    this.ortho.top = -cz + halfH;
    this.ortho.bottom = -cz - halfH;
    this.ortho.updateProjectionMatrix();
  }

  /** Metres per CSS pixel in plan view (undefined in perspective). */
  planMetresPerPixel(): number | undefined {
    if (this.view !== "plan") return undefined;
    const h = this.canvas.getBoundingClientRect().height || 1;
    return (this.plan.halfH * 2 * 1000) / h;
  }

  private installPlanControls(): void {
    const c = this.canvas;
    const pointers = new Map<number, { x: number; y: number }>();
    let pinch = 0;
    const kmPerPx = () => (this.plan.halfH * 2) / (c.getBoundingClientRect().height || 1);
    c.addEventListener("pointerdown", (e) => {
      if (this.view !== "plan") return;
      c.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = Math.hypot(a.x - b.x, a.y - b.y);
      }
    });
    c.addEventListener("pointermove", (e) => {
      if (this.view !== "plan" || !pointers.has(e.pointerId)) return;
      const prev = pointers.get(e.pointerId)!;
      if (pointers.size === 1) {
        const k = kmPerPx();
        this.plan.cx -= (e.clientX - prev.x) * k;
        this.plan.cz -= (e.clientY - prev.y) * k;
      }
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch > 0 && d > 0) this.zoomPlan(pinch / d);
        pinch = d;
      }
      this.updateOrtho();
    });
    const up = (e: PointerEvent) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = 0;
    };
    c.addEventListener("pointerup", up);
    c.addEventListener("pointercancel", up);
    c.addEventListener(
      "wheel",
      (e) => {
        if (this.view !== "plan") return;
        e.preventDefault();
        const r = c.getBoundingClientRect();
        const k = kmPerPx();
        // keep the point under the cursor fixed while zooming
        const px = this.plan.cx + (e.clientX - r.left - r.width / 2) * k;
        const pz = this.plan.cz + (e.clientY - r.top - r.height / 2) * k;
        this.zoomPlan(Math.exp(e.deltaY * 0.0015));
        const k2 = kmPerPx();
        this.plan.cx = px - (e.clientX - r.left - r.width / 2) * k2;
        this.plan.cz = pz - (e.clientY - r.top - r.height / 2) * k2;
        this.updateOrtho();
      },
      { passive: false },
    );
  }

  private zoomPlan(f: number): void {
    const m = this.grid;
    const span = m ? (Math.max(m.nx, m.ny) * m.dx) / 1000 : 20;
    this.plan.halfH = Math.min(Math.max(this.plan.halfH * f, span / 200), span * 1.5);
    this.updateOrtho();
  }

  /** Zoom in (f < 1) or out (f > 1) about the view centre (buttons, keyboard). */
  zoomBy(f: number): void {
    if (this.view === "plan") {
      this.zoomPlan(f);
      return;
    }
    const off = this.persp.position.clone().sub(this.controls.target).multiplyScalar(f);
    this.persp.position.copy(this.controls.target).add(off);
  }

  /** Project a grid point (CRS metres, elevation m) to CSS pixels in the stage. */
  worldToScreen(x: number, y: number, z?: number): { x: number; y: number; visible: boolean } {
    const m = this.grid;
    const r = this.canvas.getBoundingClientRect();
    const elev = z ?? this.bedAt(x, y)?.z ?? m?.zmin ?? 0;
    const v = new THREE.Vector3(
      (x - this.center.x) / 1000,
      ((elev - (m?.zmin ?? 0)) * this.vex) / 1000,
      -(y - this.center.y) / 1000,
    ).project(this.camera);
    return { x: ((v.x + 1) / 2) * r.width, y: ((1 - v.y) / 2) * r.height, visible: v.z < 1 && v.z > -1 };
  }

  /** Screen-space direction of north (unit vector in CSS pixels, y down). */
  northDirection(): { x: number; y: number } {
    const m = this.grid;
    if (!m) return { x: 0, y: -1 };
    const a = this.worldToScreen(this.center.x, this.center.y, m.zmin);
    const b = this.worldToScreen(this.center.x, this.center.y + m.dx * 20, m.zmin);
    const len = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    return { x: (b.x - a.x) / len, y: (b.y - a.y) / len };
  }

  /** Grid extent in CRS metres (cell edges). */
  get bounds(): DomainBox | undefined {
    const m = this.grid;
    if (!m) return undefined;
    return {
      west: m.x0 - m.dx / 2,
      south: m.y0 - m.dx / 2,
      east: m.x0 + (m.nx - 0.5) * m.dx,
      north: m.y0 + (m.ny - 0.5) * m.dx,
    };
  }

  get crs(): string | null {
    return this.grid?.crs ?? null;
  }

  get gridMeta(): GridMeta | undefined {
    return this.grid;
  }

  get verticalExaggeration(): number {
    return this.vex;
  }

  /** Render now and return the WebGL canvas (valid until the next frame). */
  snapshot(): HTMLCanvasElement {
    this.renderer.render(this.scene, this.camera);
    return this.canvas;
  }

  /** Frame a box (CRS metres) in both views, e.g. the computational domain. */
  focus(box: DomainBox, margin = 1.15): void {
    const m = this.grid;
    if (!m) return;
    const cx = ((box.west + box.east) / 2 - this.center.x) / 1000;
    const cz = -((box.south + box.north) / 2 - this.center.y) / 1000;
    const w = (box.east - box.west) / 1000;
    const hgt = (box.north - box.south) / 1000;
    this.plan = { cx, cz, halfH: Math.max(hgt / 2, w / 2 / this.aspect) * margin };
    this.updateOrtho();
    const R = Math.max(w, hgt);
    const relief = ((m.zmax - m.zmin) * this.vex) / 1000;
    this.controls.target.set(cx, relief * 0.3, cz);
    this.persp.position.set(cx + R * 0.45, relief + R * 0.6, cz + R * 0.85);
    this.fogRange = [R * 1.6, R * 4];
    this.applyFog();
    this.controls.update();
  }

  setVex(v: number): void {
    this.vex = v;
    this.shared.uVex.value = v;
    this.rebuildOverlays();
  }

  setContours(on: boolean): void {
    this.contours = on;
    const u = (this.terrainMesh?.material as THREE.ShaderMaterial | undefined)?.uniforms;
    if (u) u.uContours.value = on ? 1 : 0;
  }

  /** Terrain rendering: synthetic natural colour or greyscale hillshade. */
  setSurface(kind: SurfaceKind): void {
    this.surface = kind;
    const u = (this.terrainMesh?.material as THREE.ShaderMaterial | undefined)?.uniforms;
    if (u) u.uSurface.value = kind === "natural" ? 1 : 0;
  }

  /** Desaturate the natural surface (0 = full colour, 1 = grey) under data layers. */
  setTerrainMute(m: number): void {
    this.mute = m;
    const u = (this.terrainMesh?.material as THREE.ShaderMaterial | undefined)?.uniforms;
    if (u) u.uMute.value = m;
  }

  get contoursOn(): boolean {
    return this.contours;
  }

  /** Colour scale for depth playback [m] (e.g. the flow maximum outside the release area). */
  setDepthScale(v: number): void {
    if (!this.flowMesh) return;
    (this.flowMesh.material as THREE.ShaderMaterial).uniforms.uDepthMax.value = Math.max(v, 1e-3);
  }

  /** Whether a flow layer is drawn at a point (labels avoid covering data). */
  dataAt(x: number, y: number): boolean {
    const r = this.result;
    if (!r || !this.flowMesh) return false;
    const m = r.meta;
    const i = Math.round((x - m.x0) / m.dx);
    const j = Math.round((y - m.y0) / m.dx);
    if (i < 0 || j < 0 || i >= m.nx || j >= m.ny) return false;
    const k = j * m.nx + i;
    const u = (this.flowMesh.material as THREE.ShaderMaterial).uniforms;
    if (u.uMode.value > 1.5) {
      const q = (u.uHm.value as THREE.DataTexture).image.data as Uint8Array;
      return this.dTab[q[k]] >= 0.1;
    }
    const s = this.sample(k, this.currentTime);
    return !!s && s.h >= 0.05;
  }

  private currentTime = 0;

  /** Replace the maximum-depth envelope (e.g. with the release footprint masked). */
  setEnvelope(hmQ: Uint8Array, envMax: number): void {
    if (!this.flowMesh || !this.result) return;
    const u = (this.flowMesh.material as THREE.ShaderMaterial).uniforms;
    const tex = u.uHm.value as THREE.DataTexture;
    (tex.image.data as Uint8Array).set(hmQ);
    tex.needsUpdate = true;
    u.uEnvMax.value = Math.max(envMax, 1e-3);
  }

  // ---------------------------------------------------------------- flow
  setResult(r: Result): void {
    this.result = r;
    this.setTerrain(r, undefined, true);
    const m = r.meta;
    this.dTab = depthTable(m.hmax);
    this.sTab = speedTable(m.vmax);
    const n = m.nx * m.ny;
    const mk = () => {
      const t = new THREE.DataTexture(new Uint8Array(n * 2), m.nx, m.ny, THREE.RGFormat, THREE.UnsignedByteType);
      t.minFilter = t.magFilter = THREE.NearestFilter;
      t.needsUpdate = true;
      return t;
    };
    this.frameTex = [mk(), mk()];
    this.frameKeys = [-1, -1];
    const hm = new THREE.DataTexture(r.hmaxQ.slice(), m.nx, m.ny, THREE.RedFormat, THREE.UnsignedByteType);
    hm.minFilter = hm.magFilter = THREE.NearestFilter;
    hm.needsUpdate = true;
    const { geometry } = gridGeometry(m, this.center.x, this.center.y);
    const terrainUniforms = (this.terrainMesh!.material as THREE.ShaderMaterial).uniforms;
    const mat = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: FLOW_VS,
      fragmentShader: FLOW_FS,
      transparent: true,
      depthWrite: true,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
      uniforms: {
        ...this.shared,
        uBed: terrainUniforms.uBed,
        uSize: terrainUniforms.uSize,
        uZmin: { value: m.zmin },
        uF0: { value: this.frameTex[0] },
        uF1: { value: this.frameTex[1] },
        uHm: { value: hm },
        uW: { value: 0 },
        uHmax: { value: m.hmax },
        uEnvMax: { value: m.hmax },
        uDepthMax: { value: m.hmax },
        uOutline: { value: this.view === "plan" ? 1 : 0 },
        uInk: { value: new THREE.Color(css("--panel") || "#ffffff") },
        uVmax: { value: m.vmax },
        uBoost: { value: 1 },
        uMode: { value: 0 },
        uRamp: { value: this.ramps.depth },
      },
    });
    this.flowMesh = new THREE.Mesh(geometry, mat);
    this.flowMesh.renderOrder = 1;
    this.flowMesh.frustumCulled = false;
    this.scene.add(this.flowMesh);
    this.setTime(0);
  }

  private clearFlow(): void {
    if (!this.flowMesh) return;
    this.scene.remove(this.flowMesh);
    this.flowMesh.geometry.dispose();
    const mat = this.flowMesh.material as THREE.ShaderMaterial;
    (mat.uniforms.uHm.value as THREE.Texture).dispose();
    mat.dispose();
    this.frameTex?.forEach((t) => t.dispose());
    this.flowMesh = undefined;
    this.result = undefined;
  }

  private uploadFrame(slot: 0 | 1, f: number): void {
    if (!this.result || !this.frameTex || this.frameKeys[slot] === f) return;
    const n = this.result.meta.nx * this.result.meta.ny;
    const tex = this.frameTex[slot];
    const data = tex.image.data as Uint8Array;
    const d = this.result.depthQ.subarray(f * n, (f + 1) * n);
    const s = this.result.speedQ.subarray(f * n, (f + 1) * n);
    for (let k = 0; k < n; k++) {
      data[2 * k] = d[k];
      data[2 * k + 1] = s[k];
    }
    tex.needsUpdate = true;
    this.frameKeys[slot] = f;
  }

  /** Show the flow at simulated time t (seconds), interpolating between frames. */
  setTime(t: number): void {
    const r = this.result;
    if (!r || !this.flowMesh) return;
    const nf = r.meta.nframes;
    const fr = Math.min(Math.max(t / r.meta.every, 0), nf - 1);
    const f0 = Math.floor(fr);
    const f1 = Math.min(f0 + 1, nf - 1);
    // keep textures keyed so stepping forward reuses the previous upload
    if (this.frameKeys[1] === f0 && this.frameKeys[0] !== f0) {
      this.frameTex = [this.frameTex![1], this.frameTex![0]];
      this.frameKeys = [this.frameKeys[1], this.frameKeys[0]];
    }
    this.uploadFrame(0, f0);
    this.uploadFrame(1, f1);
    const u = (this.flowMesh.material as THREE.ShaderMaterial).uniforms;
    this.currentTime = t;
    u.uF0.value = this.frameTex![0];
    u.uF1.value = this.frameTex![1];
    u.uW.value = fr - f0;
  }

  setMode(mode: FlowMode): void {
    if (!this.flowMesh) return;
    const u = (this.flowMesh.material as THREE.ShaderMaterial).uniforms;
    u.uMode.value = { depth: 0, speed: 1, max: 2 }[mode];
    u.uRamp.value = this.ramps[mode];
  }

  setThinBoost(b: number): void {
    if (!this.flowMesh) return;
    (this.flowMesh.material as THREE.ShaderMaterial).uniforms.uBoost.value = b;
  }

  /** Depth and speed at a cell for time t (CPU copy of what the GPU shows). */
  sample(k: number, t: number): { h: number; u: number; hmax: number } | null {
    const r = this.result;
    if (!r) return null;
    const n = r.meta.nx * r.meta.ny;
    const nf = r.meta.nframes;
    const fr = Math.min(Math.max(t / r.meta.every, 0), nf - 1);
    const f0 = Math.floor(fr);
    const f1 = Math.min(f0 + 1, nf - 1);
    const w = fr - f0;
    const h = this.dTab[r.depthQ[f0 * n + k]] * (1 - w) + this.dTab[r.depthQ[f1 * n + k]] * w;
    const u = this.sTab[r.speedQ[f0 * n + k]] * (1 - w) + this.sTab[r.speedQ[f1 * n + k]] * w;
    return { h, u, hmax: this.dTab[r.hmaxQ[k]] };
  }

  // ------------------------------------------------------------ picking
  bedAt(x: number, y: number): { z: number; k: number } | null {
    const m = this.grid;
    const bed = this.bed;
    if (!m || !bed) return null;
    const fi = (x - m.x0) / m.dx;
    const fj = (y - m.y0) / m.dx;
    if (fi < 0 || fj < 0 || fi > m.nx - 1 || fj > m.ny - 1) return null;
    const i = Math.min(Math.floor(fi), m.nx - 2);
    const j = Math.min(Math.floor(fj), m.ny - 2);
    const a = fi - i;
    const b = fj - j;
    const k = j * m.nx + i;
    const z =
      bed[k] * (1 - a) * (1 - b) + bed[k + 1] * a * (1 - b) + bed[k + m.nx] * (1 - a) * b + bed[k + m.nx + 1] * a * b;
    return { z, k: Math.round(fj) * m.nx + Math.round(fi) };
  }

  /** Ray-march the camera ray over the heightfield (heights live in the shader). */
  pick(clientX: number, clientY: number): PickInfo | null {
    const m = this.grid;
    if (!m) return null;
    const r = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, this.camera);
    const o = ray.ray.origin;
    const d = ray.ray.direction;
    const span = Math.max(m.nx, m.ny) * (m.dx / 1000);
    const step = (m.dx / 1000) * 0.5;
    const toWorld = (s: number) => ({
      x: (o.x + d.x * s) * 1000 + this.center.x,
      y: -(o.z + d.z * s) * 1000 + this.center.y,
      h: ((o.y + d.y * s) * 1000) / this.vex + m.zmin,
    });
    let prev = 0;
    for (let s = 0; s < span * 4; s += step) {
      const p = toWorld(s);
      const b = this.bedAt(p.x, p.y);
      if (b && p.h <= b.z) {
        let lo = prev;
        let hi = s;
        for (let it = 0; it < 18; it++) {
          const mid = (lo + hi) / 2;
          const q = toWorld(mid);
          const bq = this.bedAt(q.x, q.y);
          if (bq && q.h <= bq.z) hi = mid;
          else lo = mid;
        }
        const q = toWorld(hi);
        const bq = this.bedAt(q.x, q.y);
        return bq ? { x: q.x, y: q.y, z: bq.z, k: bq.k } : null;
      }
      prev = s;
    }
    return null;
  }

  // ----------------------------------------------------------- overlays
  setMarkers(markers: Marker[], domain?: DomainBox): void {
    this.markers = markers;
    this.domain = domain;
    this.rebuildOverlays();
  }

  private drape(points: [number, number][], lift: number): number[] {
    const m = this.grid!;
    const out: number[] = [];
    for (const [x, y] of points) {
      const b = this.bedAt(Math.min(Math.max(x, m.x0), m.x0 + (m.nx - 1) * m.dx), Math.min(Math.max(y, m.y0), m.y0 + (m.ny - 1) * m.dx));
      const z = b ? b.z : m.zmin;
      out.push((x - this.center.x) / 1000, ((z - m.zmin + lift) * this.vex) / 1000, -(y - this.center.y) / 1000);
    }
    return out;
  }

  private line(points: number[], color: THREE.Color, width: number, dashed = false): Line2 {
    const g = new LineGeometry();
    g.setPositions(points);
    const mat = new LineMaterial({ color: color.getHex(), linewidth: width, dashed, dashSize: 0.12, gapSize: 0.08 });
    const r = this.canvas.getBoundingClientRect();
    mat.resolution.set(r.width || 1, r.height || 1);
    this.lineMats.push(mat);
    const l = new Line2(g, mat);
    if (dashed) l.computeLineDistances();
    l.renderOrder = 2;
    return l;
  }

  private rebuildOverlays(): void {
    for (const c of [...this.overlays.children]) {
      this.overlays.remove(c);
      const l = c as Line2;
      l.geometry?.dispose();
      (l.material as THREE.Material | undefined)?.dispose();
    }
    this.lineMats = [];
    if (!this.grid) return;
    const lift = 6;
    if (this.domain) {
      const { west: w, south: s, east: e, north: n } = this.domain;
      const pts: [number, number][] = [];
      const seg = (x0: number, y0: number, x1: number, y1: number) => {
        const steps = Math.max(2, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / (this.grid!.dx * 2)));
        for (let k = 0; k < steps; k++) pts.push([x0 + ((x1 - x0) * k) / steps, y0 + ((y1 - y0) * k) / steps]);
      };
      seg(w, s, e, s);
      seg(e, s, e, n);
      seg(e, n, w, n);
      seg(w, n, w, s);
      pts.push([w, s]);
      this.overlays.add(this.line(this.drape(pts, lift), this.theme.domain, 1.5, true));
    }
    for (const mk of this.markers) {
      const color = mk.kind === "pile" ? this.theme.accent : this.theme.flux;
      const ring: [number, number][] = [];
      for (let a = 0; a <= 72; a++) {
        const th = (a / 72) * Math.PI * 2;
        ring.push([mk.x + mk.radius * Math.cos(th), mk.y + mk.radius * Math.sin(th)]);
      }
      this.overlays.add(this.line(this.drape(ring, lift), color, mk.selected ? 3.5 : 2.5));
      if (mk.pin === false) continue;
      const base = this.drape([[mk.x, mk.y]], 0);
      const top = [base[0], base[1] + Math.max(0.25, (this.grid.nx * this.grid.dx) / 1000 / 40), base[2]];
      this.overlays.add(this.line([...base, ...top], color, mk.selected ? 3.5 : 2.5));
    }
  }

  dispose(): void {
    this.renderer.setAnimationLoop(null);
    this.clearTerrain();
    this.controls.dispose();
    this.renderer.dispose();
  }
}
