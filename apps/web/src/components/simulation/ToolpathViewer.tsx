import { Suspense, useMemo, useRef } from "react";
import { Canvas, useFrame, useLoader } from "@react-three/fiber";
import { Bounds, Center, OrbitControls } from "@react-three/drei";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import * as THREE from "three";
import type { SegmentoTrayectoria } from "../../lib/gcodeParser";

const COLOR_RAPIDO = "#726f69";
const COLOR_CORTE = "#d97757";
const COLOR_ARCO = "#e2926f";
const COLOR_TALADRO = "#ef4444";

function colorDe(tipo: SegmentoTrayectoria["tipo"]): string {
  if (tipo === "rapido") return COLOR_RAPIDO;
  if (tipo === "taladro") return COLOR_TALADRO;
  if (tipo === "arco") return COLOR_ARCO;
  return COLOR_CORTE;
}

function StlMesh({ url }: { url: string }) {
  const geometry = useLoader(STLLoader, url);
  const material = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#c2beb4", metalness: 0.35, roughness: 0.4, transparent: true, opacity: 0.55 }),
    []
  );
  return <mesh geometry={geometry} material={material} />;
}

function LineasTrayectoria({ segmentos }: { segmentos: SegmentoTrayectoria[] }) {
  const grupos = useMemo(() => {
    const porTipo = new Map<SegmentoTrayectoria["tipo"], number[]>();
    for (const s of segmentos) {
      const arr = porTipo.get(s.tipo) ?? [];
      arr.push(...s.desde, ...s.hasta);
      porTipo.set(s.tipo, arr);
    }
    return Array.from(porTipo.entries());
  }, [segmentos]);

  return (
    <>
      {grupos.map(([tipo, coords]) => (
        <lineSegments key={tipo}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[new Float32Array(coords), 3]} />
          </bufferGeometry>
          <lineBasicMaterial color={colorDe(tipo)} linewidth={tipo === "rapido" ? 1 : 2} transparent opacity={tipo === "rapido" ? 0.5 : 0.95} />
        </lineSegments>
      ))}
    </>
  );
}

interface CursorTrayectoriaProps {
  segmentos: SegmentoTrayectoria[];
  longitudesAcumuladas: number[];
  longitudTotal: number;
  progresoRef: React.MutableRefObject<number>;
  reproduciendo: boolean;
  velocidad: number;
  onProgreso: (p: number) => void;
}

function CursorTrayectoria({ segmentos, longitudesAcumuladas, longitudTotal, progresoRef, reproduciendo, velocidad, onProgreso }: CursorTrayectoriaProps) {
  const ref = useRef<THREE.Mesh>(null);

  useFrame((_, delta) => {
    if (segmentos.length === 0) return;
    if (reproduciendo && longitudTotal > 0) {
      const avance = velocidad * delta * (longitudTotal / 8); // ~8s a velocidad 1x para toda la trayectoria
      let nuevo = progresoRef.current + avance;
      if (nuevo >= longitudTotal) nuevo = longitudTotal;
      progresoRef.current = nuevo;
      onProgreso(nuevo);
    }

    const objetivo = progresoRef.current;
    let idx = 0;
    while (idx < longitudesAcumuladas.length - 1 && longitudesAcumuladas[idx + 1] < objetivo) idx++;
    const seg = segmentos[Math.min(idx, segmentos.length - 1)];
    if (!seg || !ref.current) return;

    const inicioSeg = idx === 0 ? 0 : longitudesAcumuladas[idx - 1];
    const largoSeg = longitudesAcumuladas[idx] - inicioSeg;
    const t = largoSeg > 0 ? Math.min(1, Math.max(0, (objetivo - inicioSeg) / largoSeg)) : 1;

    ref.current.position.set(
      seg.desde[0] + (seg.hasta[0] - seg.desde[0]) * t,
      seg.desde[1] + (seg.hasta[1] - seg.desde[1]) * t,
      seg.desde[2] + (seg.hasta[2] - seg.desde[2]) * t
    );
  });

  return (
    <mesh ref={ref}>
      <sphereGeometry args={[1.6, 16, 16]} />
      <meshStandardMaterial color="#34d399" emissive="#34d399" emissiveIntensity={0.6} />
    </mesh>
  );
}

interface ToolpathViewerProps {
  stlUrl: string | null;
  segmentos: SegmentoTrayectoria[];
  reproduciendo: boolean;
  velocidad: number;
  progreso: number;
  progresoRef: React.MutableRefObject<number>;
  onProgreso: (p: number) => void;
}

export function ToolpathViewer({ stlUrl, segmentos, reproduciendo, velocidad, progresoRef, onProgreso }: ToolpathViewerProps) {
  const { longitudesAcumuladas, longitudTotal } = useMemo(() => {
    const acumuladas: number[] = [];
    let total = 0;
    for (const s of segmentos) {
      const largo = Math.hypot(s.hasta[0] - s.desde[0], s.hasta[1] - s.desde[1], s.hasta[2] - s.desde[2]);
      total += largo;
      acumuladas.push(total);
    }
    return { longitudesAcumuladas: acumuladas, longitudTotal: total };
  }, [segmentos]);

  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg bg-gradient-to-b from-[var(--color-surface-2)] to-[var(--color-surface)]">
      <Canvas shadows camera={{ position: [120, 100, 120], fov: 40 }}>
        <color attach="background" args={["#2d2c2a"]} />
        <ambientLight intensity={0.7} />
        <directionalLight position={[80, 120, 60]} intensity={1.2} />
        <directionalLight position={[-70, 40, -60]} intensity={0.4} />
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.3}>
            <Center>
              <group>
                {stlUrl && <StlMesh url={stlUrl} />}
                {segmentos.length > 0 && <LineasTrayectoria segmentos={segmentos} />}
                {segmentos.length > 0 && (
                  <CursorTrayectoria
                    segmentos={segmentos}
                    longitudesAcumuladas={longitudesAcumuladas}
                    longitudTotal={longitudTotal}
                    progresoRef={progresoRef}
                    reproduciendo={reproduciendo}
                    velocidad={velocidad}
                    onProgreso={onProgreso}
                  />
                )}
              </group>
            </Center>
          </Bounds>
        </Suspense>
        <OrbitControls enablePan makeDefault />
      </Canvas>
      <div className="pointer-events-none absolute bottom-2 left-2 flex flex-wrap gap-x-3 gap-y-1 rounded-md bg-black/40 px-2 py-1 text-[10px] text-[var(--color-text-muted)] backdrop-blur">
        <Leyenda color={COLOR_CORTE} texto="corte (G1)" />
        <Leyenda color={COLOR_ARCO} texto="arco (G2/G3)" />
        <Leyenda color={COLOR_TALADRO} texto="taladro" />
        <Leyenda color={COLOR_RAPIDO} texto="rápido (G0)" />
      </div>
    </div>
  );
}

function Leyenda({ color, texto }: { color: string; texto: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      {texto}
    </span>
  );
}
