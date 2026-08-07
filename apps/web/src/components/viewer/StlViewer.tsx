import { Suspense, useMemo } from "react";
import { Canvas, useLoader } from "@react-three/fiber";
import { Bounds, Center, OrbitControls } from "@react-three/drei";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import * as THREE from "three";

function StlMesh({ url }: { url: string }) {
  const geometry = useLoader(STLLoader, url);
  const material = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#c2beb4", metalness: 0.4, roughness: 0.38 }),
    []
  );
  return <mesh geometry={geometry} material={material} castShadow receiveShadow />;
}

// No @react-three/drei <Stage>/<Environment> here on purpose: those fetch an
// HDR map from a third-party CDN by default, which fails (and crashes the
// WebGL context) on a network without access to it - not a safe assumption
// for a shop tool that may run on an isolated network. Lighting is manual
// and self-contained instead; <Bounds> auto-fits the camera without any
// network dependency.
export function StlViewer({ url }: { url: string }) {
  return (
    <div className="relative h-72 w-full overflow-hidden rounded-lg bg-gradient-to-b from-[var(--color-surface-2)] to-[var(--color-surface)]">
      <Canvas key={url} shadows camera={{ position: [90, 70, 90], fov: 38 }}>
        <color attach="background" args={["#2d2c2a"]} />
        <ambientLight intensity={0.7} />
        <directionalLight position={[80, 120, 60]} intensity={1.3} castShadow shadow-mapSize={[1024, 1024]} />
        <directionalLight position={[-70, 40, -60]} intensity={0.45} />
        <pointLight position={[0, -60, 0]} intensity={0.15} />
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.35}>
            <Center>
              <StlMesh url={url} />
            </Center>
          </Bounds>
        </Suspense>
        <OrbitControls autoRotate autoRotateSpeed={1.1} enablePan={false} makeDefault />
      </Canvas>
      <div className="pointer-events-none absolute bottom-2 left-2 rounded-md bg-black/40 px-2 py-1 text-[10px] text-[var(--color-text-muted)] backdrop-blur">
        Vista previa generada por el motor de geometría · arrastra para rotar
      </div>
    </div>
  );
}
