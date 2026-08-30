"use client";

import { useEffect, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { RoundedBox } from "@react-three/drei";
import * as THREE from "three";

type Piece = {
  position: [number, number, number];
  size: [number, number, number];
  accent?: boolean;
};

const PIECES: Piece[] = [
  { position: [0, 0, 0], size: [1.6, 1.6, 1.6] },
  { position: [1.15, 0.85, 0.35], size: [0.75, 0.75, 0.75] },
  { position: [-1.05, -0.6, 0.5], size: [0.62, 0.62, 0.62] },
  { position: [0.5, -1.05, -0.55], size: [0.68, 0.68, 0.68], accent: true },
  { position: [-0.85, 0.95, -0.4], size: [0.5, 0.5, 0.5] },
  { position: [1.0, -0.2, -0.95], size: [0.44, 0.44, 0.44], accent: true },
];

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const handler = () => setReduced(mq.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return reduced;
}

function CubeAssembly({ reducedMotion }: { reducedMotion: boolean }) {
  const tiltGroup = useRef<THREE.Group>(null);
  const spinGroup = useRef<THREE.Group>(null);
  const pointer = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const handleMove = (e: PointerEvent) => {
      pointer.current = {
        x: (e.clientX / window.innerWidth) * 2 - 1,
        y: (e.clientY / window.innerHeight) * 2 - 1,
      };
    };
    window.addEventListener("pointermove", handleMove);
    return () => window.removeEventListener("pointermove", handleMove);
  }, []);

  useFrame((_, delta) => {
    if (spinGroup.current && !reducedMotion) {
      spinGroup.current.rotation.y += delta * 0.18;
      spinGroup.current.rotation.x = Math.sin(Date.now() * 0.00008) * 0.08;
    }
    if (tiltGroup.current) {
      const targetX = pointer.current.y * 0.28;
      const targetY = pointer.current.x * 0.38;
      tiltGroup.current.rotation.x = THREE.MathUtils.lerp(
        tiltGroup.current.rotation.x,
        targetX,
        0.04,
      );
      tiltGroup.current.rotation.y = THREE.MathUtils.lerp(
        tiltGroup.current.rotation.y,
        targetY,
        0.04,
      );
    }
  });

  return (
    <group ref={tiltGroup}>
      <group ref={spinGroup} rotation={[0.35, 0.6, 0]}>
        {PIECES.map((piece, i) => (
          <RoundedBox
            key={i}
            args={piece.size}
            radius={0.06}
            smoothness={4}
            position={piece.position}
          >
            <meshStandardMaterial
              color={piece.accent ? "#d4af37" : "#0d0d0d"}
              metalness={piece.accent ? 0.9 : 0.75}
              roughness={piece.accent ? 0.25 : 0.32}
              emissive={piece.accent ? "#3a2a08" : "#000000"}
              emissiveIntensity={piece.accent ? 0.35 : 0}
            />
          </RoundedBox>
        ))}
      </group>
    </group>
  );
}

export default function HeroCube() {
  const reducedMotion = useReducedMotion();

  return (
    <div className="absolute inset-0">
      <Canvas
        dpr={[1, 2]}
        camera={{ position: [0, 0, 5.6], fov: 40 }}
        gl={{ antialias: true, alpha: true }}
      >
        <ambientLight intensity={0.35} />
        <directionalLight position={[3, 4, 5]} intensity={1.4} color="#ffffff" />
        <directionalLight position={[-4, -2, -3]} intensity={0.5} color="#f3ba2f" />
        <pointLight position={[-3, 1, -4]} intensity={6} color="#d4af37" distance={12} />
        <spotLight
          position={[2, 5, 3]}
          angle={0.4}
          penumbra={0.7}
          intensity={0.8}
          color="#ffffff"
        />
        <CubeAssembly reducedMotion={reducedMotion} />
      </Canvas>
    </div>
  );
}
