import { Component, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { Canvas, useThree } from "@react-three/fiber";
import { PlaneGeometry } from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const stages = ["Terrain", "Release", "Cell grid", "Illustrative flow"];
const elevation = (x: number, z: number) => .08 + .7 * Math.exp(-((x + 1.1) ** 2 + (z + .8) ** 2) / 2) + .07 * Math.cos(z * 1.4);
type Palette = { ground: string; ink: string; accent: string; line: string; surface: string };
function palette(): Palette {
  const css = getComputedStyle(document.documentElement);
  const token = (name: string) => css.getPropertyValue(name).trim();
  return { ground: token("--panel-2"), ink: token("--fg"), accent: token("--accent"), line: token("--control"), surface: token("--terrain-mid") };
}

function Camera({ reset, plan }: { reset: number; plan: boolean }) {
  const { camera, gl, invalidate } = useThree();
  useEffect(() => {
    const controls = new OrbitControls(camera, gl.domElement);
    controls.enableDamping = false;
    controls.enablePan = false;
    controls.minDistance = 4;
    controls.maxDistance = 16;
    controls.maxPolarAngle = Math.PI / 2.1;
    controls.target.set(0, .25, 0);
    const wake = () => invalidate();
    controls.addEventListener("change", wake);
    return () => { controls.removeEventListener("change", wake); controls.dispose(); };
  }, [camera, gl, invalidate]);
  useEffect(() => {
    camera.position.set(...(plan ? [0, 10, .001] : [7, 6, 7]) as [number, number, number]);
    camera.lookAt(0, .25, 0);
    invalidate();
  }, [camera, reset, plan, invalidate]);
  return null;
}

function Landscape({ stage, time, radius, source, colors, onPlace }: {
  stage: number; time: number; radius: number; source: [number, number]; colors: Palette; onPlace: (p: [number, number]) => void;
}) {
  const terrain = useMemo(() => {
    const geometry = new PlaneGeometry(6, 6, 40, 40);
    geometry.rotateX(-Math.PI / 2);
    const positions = geometry.attributes.position;
    for (let i = 0; i < positions.count; i++) positions.setY(i, elevation(positions.getX(i), positions.getZ(i)));
    geometry.computeVertexNormals();
    return geometry;
  }, []);
  const flow = useMemo(() => {
    const geometry = new PlaneGeometry(6, 6, 60, 60);
    geometry.rotateX(-Math.PI / 2);
    const positions = geometry.attributes.position;
    const spread = radius / 100;
    const offset = stage === 3 ? time / 60 : 0;
    for (let i = 0; i < positions.count; i++) {
      const x = positions.getX(i), z = positions.getZ(i);
      const r2 = ((x - source[0] - offset * .5) / (spread + offset * .25)) ** 2 + ((z - source[1] - offset * 1.7) / (spread + offset * .65)) ** 2;
      const height = .25 / (1 + offset * 2) * Math.max(1 - r2, 0);
      positions.setY(i, elevation(x, z) + (height > 0 ? height + .008 : -.025));
    }
    geometry.computeVertexNormals();
    return geometry;
  }, [stage, time, radius, source]);
  useEffect(() => () => terrain.dispose(), [terrain]);
  useEffect(() => () => flow.dispose(), [flow]);
  return <>
    <mesh onClick={event => { if (stage === 1 && event.delta < 5) { event.stopPropagation(); onPlace([Math.max(-2, Math.min(2, event.point.x)), Math.max(-2, Math.min(2, event.point.z))]); } }}>
      <primitive object={terrain} attach="geometry" />
      <meshStandardMaterial color={colors.surface} roughness={1} />
    </mesh>
    {stage > 0 && <mesh><primitive object={flow} attach="geometry" /><meshStandardMaterial color={colors.accent} roughness={1} /></mesh>}
    {stage === 2 && <mesh position={[0, .005, 0]}><primitive object={terrain} attach="geometry" /><meshBasicMaterial color={colors.line} wireframe /></mesh>}
    <mesh position={[0, -.12, 0]}><boxGeometry args={[6, .24, 6]} /><meshStandardMaterial color={colors.surface} roughness={1} /></mesh>
  </>;
}

class GraphicsBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <p role="alert" className="model3d-error">The interactive view could not start. Use the modelling-stage diagrams below, or reload in a browser with WebGL 2 enabled.</p> : this.props.children; }
}

function InteractiveModel() {
  const [stage, setStage] = useState(0);
  const [time, setTime] = useState(0);
  const [radius, setRadius] = useState(60);
  const [source, setSource] = useState<[number, number]>([-1.1, -.8]);
  const [colors, setColors] = useState(palette);
  const [reset, setReset] = useState(0);
  const [plan, setPlan] = useState(false);
  useEffect(() => {
    const observer = new MutationObserver(() => setColors(palette()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const media = matchMedia("(prefers-color-scheme: dark)");
    const update = () => setColors(palette());
    media.addEventListener("change", update);
    return () => { observer.disconnect(); media.removeEventListener("change", update); };
  }, []);
  const description = [
    "Ground elevation defines the bed. Orbit the surface to see the relief; this is synthetic terrain, not a DEM from a real location.",
    "The blue paraboloid is released material above the bed. Change its radius or click the terrain to move its centre. The peak height is fixed at 25 m.",
    "The wireframe shows 15 m terrain sampling on this 600 × 600 m domain. Solver cells store depth and horizontal momentum; this display is an educational mesh, not a running solver.",
    "Scrub the slider to see an authored change in the footprint. It illustrates how frames can represent flow evolution. It does not calculate gravity, friction, mass conservation or runout.",
  ][stage];
  return <section className="model3d-section guide-learning" aria-labelledby="interactiveModelTitle">
    <h2 id="interactiveModelTitle">Explore the model in 3D</h2>
    <p>Orbit the terrain, place a release and inspect the grid. These objects connect the pipeline to the fields the solver works with.</p>
    <div className="model3d-layout">
      <div>
        <div className="model3d-canvas" role="img" aria-label="Interactive synthetic terrain with optional release and grid. Equivalent explanations and controls follow.">
          <GraphicsBoundary><Canvas frameloop="demand" dpr={[1, 1.5]} camera={{ position: [7, 6, 7], fov: 40 }} fallback={<p className="model3d-error">3D graphics are unavailable. Use the diagrams below.</p>}>
            <color attach="background" args={[colors.ground]} />
            <ambientLight intensity={.6} />
            <directionalLight position={[4, 8, 3]} intensity={1.5} />
            <Landscape stage={stage} time={time} radius={radius} source={source} colors={colors} onPlace={setSource} />
            <Camera reset={reset} plan={plan} />
          </Canvas></GraphicsBoundary>
        </div>
        <p className="guide-note">Synthetic terrain · blue = material · grey = bed · equal horizontal and vertical scale (VE 1×). Drag to orbit; scroll or pinch to zoom. North is −Z; east is +X. This is an illustration, not a simulation.</p>
      </div>
      <div className="model3d-controls">
        <div className="model3d-stages" role="group" aria-label="3D modelling stages">{stages.map((name, i) => <button key={name} type="button" className="btn" aria-pressed={stage === i} onClick={() => setStage(i)}>{name}</button>)}</div>
        <p aria-live="polite">{description}</p>
        {stage > 0 && <><label htmlFor="modelRadius">Release radius <output>{radius} m</output></label><input id="modelRadius" type="range" min="40" max="100" step="5" value={radius} onChange={event => setRadius(Number(event.target.value))} /><p className="guide-note">Ideal initial pile volume: {(Math.PI * radius ** 2 * 25 / 2).toLocaleString(undefined, { maximumFractionDigits: 0 })} m³. The mesh samples the shape; its discrete volume may differ.</p></>}
        {stage === 1 && <button type="button" className="btn" onClick={() => setSource(source[0] < 0 ? [1, .7] : [-1.1, -.8])}>Move release to {source[0] < 0 ? "lower slope" : "upper slope"}</button>}
        {stage === 3 && <><label htmlFor="modelTime">Illustrative frame <output>{time} / 60</output></label><input id="modelTime" type="range" min="0" max="60" value={time} onChange={event => setTime(Number(event.target.value))} /></>}
        <div className="model3d-stages"><button type="button" className="btn" aria-pressed={plan} onClick={() => setPlan(!plan)}>{plan ? "Use 3D view" : "Use plan view"}</button><button type="button" className="btn" onClick={() => setReset(reset + 1)}>Reset camera</button></div>
        <button type="button" className="btn" onClick={() => { setStage(0); setTime(0); setRadius(60); setSource([-1.1, -.8]); setPlan(false); setReset(reset + 1); }}>Reset demonstration</button>
      </div>
    </div>
  </section>;
}

export function mountInteractiveModel(host: HTMLElement): () => void {
  const root = createRoot(host);
  root.render(<InteractiveModel />);
  return () => root.unmount();
}
