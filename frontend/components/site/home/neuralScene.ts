import * as THREE from "three";
import { cortexPoint, seededRandom } from "./neuralGeometry";

export interface NeuralRuntime {
  setPaused(value: boolean): void;
  setFocus(value: string | null): void;
  dispose(): void;
}

const pointVertex = `
  attribute float aSize;
  attribute vec3 aColor;
  uniform float uTime;
  uniform float uDpr;
  uniform vec2 uMouse;
  varying vec3 vColor;
  varying float vPulse;
  void main() {
    vec3 p = position;
    float distanceToMouse = length(p.xy - uMouse * vec2(2.0, 1.8));
    p.xy += normalize(p.xy - uMouse * vec2(2.0, 1.8) + .001) * .035 * exp(-distanceToMouse * 2.0);
    p += normal * sin(uTime * .5 + position.y * 2.0) * .014;
    float wave = fract(uTime * .13 - position.x * .16 + position.z * .03);
    vPulse = pow(max(0.0, 1.0 - abs(wave - .5) * 10.0), 3.0);
    vColor = aColor;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = aSize * uDpr * (30.0 / -mv.z) * (1.0 + vPulse * .7);
  }
`;
const pointFragment = `
  varying vec3 vColor;
  varying float vPulse;
  void main() {
    float d = length(gl_PointCoord - .5) * 2.0;
    if (d > 1.0) discard;
    float alpha = exp(-d * d * 4.5) * .75;
    gl_FragColor = vec4(vColor * (.75 + vPulse * 1.65), alpha);
  }
`;

/** Small procedural scene. No models, textures, React frame updates or raycasting. */
export async function createNeuralScene(host: HTMLDivElement, onFailure: () => void): Promise<NeuralRuntime> {
  const mobile = matchMedia("(max-width: 700px)").matches;
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const lowPower = mobile || (navigator.hardwareConcurrency || 4) <= 4;
  const renderer = new THREE.WebGLRenderer({ alpha: false, antialias: !lowPower, powerPreference: "low-power" });
  renderer.setClearColor("#060d16");
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  let dpr = Math.min(devicePixelRatio || 1, lowPower ? 1 : 1.6);
  renderer.setPixelRatio(dpr);
  const canvas = renderer.domElement;
  host.appendChild(canvas);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(39, 1, .1, 30);
  camera.position.set(.15, .12, 8.7);
  const core = new THREE.Group();
  core.rotation.set(.1, -.36, -.07);
  scene.add(core);
  const random = seededRandom();
  const nodeCount = lowPower ? 1050 : 2600;
  const positions = new Float32Array(nodeCount * 3), normals = new Float32Array(nodeCount * 3);
  const colors = new Float32Array(nodeCount * 3), sizes = new Float32Array(nodeCount);
  const nodes: THREE.Vector3[] = [];
  const green = new THREE.Color("#72e4bc"), blue = new THREE.Color("#6dcfe9"), purple = new THREE.Color("#a09ddd");
  const scratchColor = new THREE.Color();
  for (let i = 0; i < nodeCount; i++) {
    // Equal-area sampling avoids bright particle clumps at the cortical poles.
    const p = cortexPoint(random(), .04 + Math.acos(1 - 2 * random()) / Math.PI * .92, i % 2 ? -1 : 1);
    const node = new THREE.Vector3(...p);
    if (i % 5 === 0) node.multiplyScalar(.35 + random() * .6);
    nodes.push(node);
    node.toArray(positions, i * 3);
    node.clone().normalize().toArray(normals, i * 3);
    scratchColor.copy(green).lerp(i % 2 ? blue : purple, (p[0] + 1.8) / 3.6).toArray(colors, i * 3);
    sizes[i] = i % 19 === 0 ? 1.4 : .36 + random() * .52;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
  geometry.setAttribute("aColor", new THREE.BufferAttribute(colors, 3));
  geometry.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
  const uniforms = { uTime: { value: 0 }, uDpr: { value: dpr }, uMouse: { value: new THREE.Vector2(10, 10) } };
  const pointsMaterial = new THREE.ShaderMaterial({ uniforms, vertexShader: pointVertex, fragmentShader: pointFragment, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  core.add(new THREE.Points(geometry, pointsMaterial));

  function line(points: THREE.Vector3[], color: THREE.Color | string, opacity: number, parent: THREE.Group | THREE.Scene = core) {
    const g = new THREE.BufferGeometry().setFromPoints(points);
    const m = new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false, blending: THREE.AdditiveBlending });
    const object = new THREE.Line(g, m);
    parent.add(object);
    return object;
  }
  // Folded cortical filaments expose the hemisphere structure without a solid mesh.
  for (const side of [-1, 1]) {
    for (let j = 1; j < (lowPower ? 17 : 26); j++) {
      const v = j / (lowPower ? 17 : 26);
      line(Array.from({ length: 100 }, (_, i) => new THREE.Vector3(...cortexPoint(i / 99, v, side))), side < 0 ? green : blue, .17);
    }
    for (let j = 0; j < 9; j++) {
      line(Array.from({ length: 70 }, (_, i) => new THREE.Vector3(...cortexPoint(j / 9, i / 69, side))), side < 0 ? blue : purple, .11);
    }
  }
  const edges: number[] = [], edgeColors: number[] = [];
  // Bounded local links keep this a neural graph, not a star field.
  for (let i = 0; i < nodes.length; i += lowPower ? 4 : 3) {
    let linked = 0;
    for (let j = i + 1; j < Math.min(nodes.length, i + 95); j++) {
      const distance = nodes[i].distanceToSquared(nodes[j]);
      if (distance > .025 && distance < .28) {
        edges.push(...nodes[i].toArray(), ...nodes[j].toArray());
        edgeColors.push(...colors.slice(i * 3, i * 3 + 3), ...colors.slice(j * 3, j * 3 + 3));
        if (++linked === 3) break;
      }
    }
  }
  const edgeGeometry = new THREE.BufferGeometry();
  edgeGeometry.setAttribute("position", new THREE.Float32BufferAttribute(edges, 3));
  edgeGeometry.setAttribute("color", new THREE.Float32BufferAttribute(edgeColors, 3));
  core.add(new THREE.LineSegments(edgeGeometry, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: .18, depthWrite: false, blending: THREE.AdditiveBlending })));

  // A few axonal bundles pass through the interior and carry bright impulses.
  const bundles: THREE.CatmullRomCurve3[] = [];
  for (let i = 0; i < (lowPower ? 14 : 26); i++) {
    const y = (random() - .5) * 2.1, z = (random() - .5) * 1.3;
    const curve = new THREE.CatmullRomCurve3([new THREE.Vector3(-1.2, y, z), new THREE.Vector3(-.6, y + .35, z - .25), new THREE.Vector3(.1, y * .6, z + .4), new THREE.Vector3(.8, y - .25, z - .1), new THREE.Vector3(1.25, y * .8, z)]);
    bundles.push(curve);
    line(curve.getPoints(52), i % 3 ? green : purple, .1);
  }

  const orbit = new THREE.Group();
  orbit.rotation.set(.85, .2, -.28);
  scene.add(orbit);
  const orbitPoints = Array.from({ length: 180 }, (_, i) => {
    const a = i / 179 * Math.PI * 2;
    return new THREE.Vector3(Math.cos(a) * 2.25, Math.sin(a) * 2.25, 0);
  });
  line(orbitPoints, "#488f8a", .27, orbit);
  const arc = new THREE.Group();
  arc.rotation.set(-.5, -.65, .32);
  scene.add(arc);
  line(Array.from({ length: 95 }, (_, i) => {
    const a = i / 94 * Math.PI * 1.55;
    return new THREE.Vector3(Math.cos(a) * 2.08, Math.sin(a) * 2.08, 0);
  }), "#827daa", .16, arc);

  type Route = { curve: THREE.CatmullRomCurve3; object: THREE.Line; stage: string };
  const routes: Route[] = [];
  function route(stage: string, p: number[][], color: string) {
    const curve = new THREE.CatmullRomCurve3(p.map(v => new THREE.Vector3(v[0], v[1], v[2])));
    routes.push({ curve, object: line(curve.getPoints(80), color, .35, scene), stage });
  }
  for (let i = 0; i < 3; i++) route("eeg", [[-3.6, -.55 - i * .14, .1], [-2.4, -.3 - i * .15, .2], [-1.7, -.48 + i * .12, .3], [-.9, -.2 + i * .09, .1]], "#64d9b8");
  route("eog", [[1.05, .4, .15], [1.65, .85, .1], [2.35, 1.12, 0], [3.1, 1.12, .1]], "#9f95e1");
  route("device", [[1.1, -.4, .15], [1.95, -.8, .3], [2.4, -1.25, .1], [3.2, -1.25, .1]], "#72cced");
  // EEG is a waveform entering the decoder rather than a generic particle emitter.
  for (let row = 0; row < 2; row++) {
    line(Array.from({ length: 160 }, (_, i) => {
      const t = i / 159, envelope = Math.sin(t * Math.PI) ** 4;
      return new THREE.Vector3(-3.65 + t * 1.5, -.18 - row * .23 + Math.sin(t * 62 + row) * .14 * envelope + Math.sin(t * 23) * .045, 0);
    }), row ? "#5299a5" : "#6cdcbc", .55, scene);
  }
  for (const [x, y, color] of [[3.1, 1.12, "#afa0e8"], [3.2, -1.25, "#77d6e9"]] as const) {
    const ring = new THREE.Mesh(new THREE.RingGeometry(.105, .12, 40), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: .6, side: THREE.DoubleSide }));
    ring.position.set(x, y, .1); scene.add(ring);
  }
  const pulseCount = bundles.length * 2 + routes.length * 5;
  const pulsePositions = new Float32Array(pulseCount * 3), pulseColors = new Float32Array(pulseCount * 3);
  const pulseGeometry = new THREE.BufferGeometry();
  pulseGeometry.setAttribute("position", new THREE.BufferAttribute(pulsePositions, 3).setUsage(THREE.DynamicDrawUsage));
  pulseGeometry.setAttribute("color", new THREE.BufferAttribute(pulseColors, 3).setUsage(THREE.DynamicDrawUsage));
  const pulseMaterial = new THREE.PointsMaterial({ size: .046, vertexColors: true, transparent: true, opacity: .92, depthWrite: false, blending: THREE.AdditiveBlending });
  const pulsePoints = new THREE.Points(pulseGeometry, pulseMaterial);
  pulsePoints.frustumCulled = false;
  scene.add(pulsePoints);
  // Sparse nearby neural nodes give the middle layer depth without a star field.
  const middle = new Float32Array((lowPower ? 20 : 42) * 3);
  for (let i = 0; i < middle.length; i += 3) {
    const angle = random() * Math.PI * 2, radius = 2.2 + random() * .65;
    middle.set([Math.cos(angle) * radius, Math.sin(angle) * radius * .68, -1.4 - random() * 2], i);
  }
  const middleGeometry = new THREE.BufferGeometry();
  middleGeometry.setAttribute("position", new THREE.BufferAttribute(middle, 3));
  scene.add(new THREE.Points(middleGeometry, new THREE.PointsMaterial({ color: "#69959b", size: .019, transparent: true, opacity: .38 })));

  let composer: import("three/examples/jsm/postprocessing/EffectComposer.js").EffectComposer | null = null;
  // Desktop-only half-resolution bloom; CSS provides low-cost vignette and grain.
  if (!lowPower && !motion.matches) {
    try {
      const [{ EffectComposer }, { RenderPass }, { UnrealBloomPass }, { OutputPass }] = await Promise.all([
        import("three/examples/jsm/postprocessing/EffectComposer.js"), import("three/examples/jsm/postprocessing/RenderPass.js"),
        import("three/examples/jsm/postprocessing/UnrealBloomPass.js"), import("three/examples/jsm/postprocessing/OutputPass.js"),
      ]);
      composer = new EffectComposer(renderer);
      composer.setPixelRatio(Math.min(dpr, 1));
      composer.addPass(new RenderPass(scene, camera));
      composer.addPass(new UnrealBloomPass(new THREE.Vector2(320, 260), .52, .45, .9));
      composer.addPass(new OutputPass());
    } catch { composer?.dispose(); composer = null; }
  }
  let disposed = false, failed = false, paused = false, visible = true, focus: string | null = null;
  let frameId = 0, time = 1.4, previous = 0, sampleStart = 0, sampleFrames = 0, slowSamples = 0;
  const mouse = new THREE.Vector2(), targetMouse = new THREE.Vector2(), pulse = new THREE.Vector3();
  let hovering = false;
  const surface = host.parentElement!;

  function resize() {
    const { width, height } = host.getBoundingClientRect();
    if (!width || !height || disposed) return;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    composer?.setSize(width, height);
    uniforms.uDpr.value = dpr;
    draw();
  }
  function updatePulses() {
    core.updateMatrixWorld();
    let index = 0;
    bundles.forEach((curve, i) => {
      for (let j = 0; j < 2; j++) {
        curve.getPoint((time * .075 + i * .071 + j * .5) % 1, pulse).applyMatrix4(core.matrixWorld);
        pulse.toArray(pulsePositions, index * 3);
        scratchColor.copy(i % 3 ? green : purple).multiplyScalar(focus === "intent" ? 2 : 1.3).toArray(pulseColors, index++ * 3);
      }
    });
    routes.forEach((r, i) => {
      for (let j = 0; j < 5; j++) {
        r.curve.getPoint((time * .095 + i * .08 + j * .2) % 1, pulse).toArray(pulsePositions, index * 3);
        scratchColor.set(r.stage === "eog" ? "#c4b1ff" : r.stage === "device" ? "#88dcf9" : "#8af5d0").multiplyScalar(focus === r.stage ? 1.9 : 1.15).toArray(pulseColors, index++ * 3);
      }
      (r.object.material as THREE.LineBasicMaterial).opacity = focus === r.stage ? .8 : .3;
    });
    pulseGeometry.attributes.position.needsUpdate = true;
    pulseGeometry.attributes.color.needsUpdate = true;
  }
  function draw() {
    if (disposed || failed) return;
    try {
      uniforms.uTime.value = time;
      updatePulses();
      if (composer && !motion.matches) composer.render(); else renderer.render(scene, camera);
    } catch { failed = true; stop(); onFailure(); }
  }
  function stop() { cancelAnimationFrame(frameId); frameId = 0; previous = 0; sampleStart = 0; sampleFrames = 0; }
  function shouldAnimate() { return !disposed && !failed && visible && !document.hidden && !paused && !motion.matches; }
  function frame(now: number) {
    frameId = 0;
    if (!shouldAnimate()) return;
    const elapsed = previous ? (now - previous) / 1000 : 0;
    const delta = Math.min(elapsed, .05);
    // Some browsers throttle a hidden panel to 1 FPS without visibilitychange.
    // Such scheduling gaps are not GPU pressure and must not lower quality.
    const throttled = elapsed > .2;
    if (throttled) { sampleStart = 0; sampleFrames = 0; slowSamples = 0; host.dataset.fps = "throttled"; }
    previous = now;
    time += delta;
    mouse.lerp(targetMouse, 1 - Math.exp(-delta * 4));
    core.rotation.y = -.36 + mouse.x * .12 + Math.sin(time * .17) * .045;
    core.rotation.x = .1 - mouse.y * .065;
    core.rotation.z = -.07 + Math.sin(time * .12) * .018;
    camera.position.x = .15 + mouse.x * .09;
    camera.position.y = .12 + mouse.y * .06;
    uniforms.uMouse.value.set(hovering ? mouse.x : 10, hovering ? mouse.y : 10);
    draw();
    if (!sampleStart && !throttled) sampleStart = now;
    if (!throttled) sampleFrames++;
    if (sampleStart && now - sampleStart > 2500) {
      const fps = sampleFrames * 1000 / (now - sampleStart);
      host.dataset.fps = fps.toFixed(1);
      host.dataset.dpr = dpr.toFixed(2);
      host.dataset.bloom = String(Boolean(composer));
      slowSamples = fps < 42 ? slowSamples + 1 : 0;
      if (slowSamples >= 2) {
        if (composer) { composer.passes.forEach(p => p.dispose()); composer.dispose(); composer = null; }
        dpr = Math.max(.75, dpr - .25);
        renderer.setPixelRatio(dpr);
        resize(); slowSamples = 0;
      }
      sampleStart = now; sampleFrames = 0;
    }
    if (shouldAnimate()) frameId = requestAnimationFrame(frame);
  }
  function resume() { if (shouldAnimate() && !frameId) frameId = requestAnimationFrame(frame); else if (!shouldAnimate()) { stop(); draw(); } }
  function onPointer(e: PointerEvent) {
    if (motion.matches || e.pointerType === "touch") return;
    const rect = surface.getBoundingClientRect();
    targetMouse.set((e.clientX - rect.left) / rect.width * 2 - 1, -((e.clientY - rect.top) / rect.height * 2 - 1));
    hovering = true;
  }
  function onLeave() { targetMouse.set(0, 0); hovering = false; }
  function onContextLost(event: Event) { event.preventDefault(); failed = true; stop(); onFailure(); }
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(host);
  const intersection = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; resume(); }, { threshold: .04 });
  intersection.observe(host);
  surface.addEventListener("pointermove", onPointer, { passive: true });
  surface.addEventListener("pointerleave", onLeave);
  canvas.addEventListener("webglcontextlost", onContextLost);
  document.addEventListener("visibilitychange", resume);
  motion.addEventListener("change", resume);
  host.dataset.particles = String(nodeCount);
  host.dataset.reducedMotion = String(motion.matches);
  resize(); resume();
  return {
    setPaused(value) { paused = value; resume(); },
    setFocus(value) { focus = value; if (!shouldAnimate()) draw(); },
    dispose() {
      disposed = true; stop(); resizeObserver.disconnect(); intersection.disconnect();
      surface.removeEventListener("pointermove", onPointer); surface.removeEventListener("pointerleave", onLeave);
      canvas.removeEventListener("webglcontextlost", onContextLost); document.removeEventListener("visibilitychange", resume); motion.removeEventListener("change", resume);
      scene.traverse(object => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Points || object instanceof THREE.Line) {
          object.geometry.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach(material => material.dispose());
        }
      });
      composer?.passes.forEach(pass => pass.dispose()); composer?.dispose();
      renderer.dispose(); renderer.forceContextLoss(); canvas.remove();
    },
  };
}
