"use client";

import { useRef } from "react";
import * as THREE from "three";
import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, Environment, Lightformer, OrbitControls, RoundedBox } from "@react-three/drei";
import { PieceBody } from "@/components/board3d/Pieces";
import type { Kind } from "@/lib/types";

function Turntable({ kind }: { kind: Kind }) {
  const group = useRef<THREE.Group>(null);
  useFrame((_, delta) => {
    if (group.current) group.current.rotation.y += delta * 0.6;
  });
  return (
    <group ref={group}>
      {/* Rouge et bleu côte à côte, sur un socle comme une case du plateau. */}
      <RoundedBox args={[2.3, 0.3, 1.2]} radius={0.08} smoothness={4} position={[0, -0.15, 0]} receiveShadow>
        <meshStandardMaterial color="#5f7d42" roughness={0.8} />
      </RoundedBox>
      <group position={[-0.55, 0, 0]} scale={1.15}>
        <PieceBody owner={1} kind={kind} highlight={0} />
      </group>
      <group position={[0.55, 0, 0]} scale={1.15}>
        <PieceBody owner={2} kind={kind} highlight={0} />
      </group>
    </group>
  );
}

/** Vitrine 3D d'une pièce (rouge + bleue) qui tourne sur elle-même ; orbite au doigt. */
export default function PieceViewer({ kind }: { kind: Kind }) {
  return (
    <div className="pieceViewer">
      <Canvas dpr={[1, 1.75]} camera={{ fov: 32, position: [0, 1.6, 3.6] }} gl={{ alpha: true, antialias: true }}>
        <hemisphereLight args={["#dfe8ff", "#3a2f25", 0.7]} />
        <directionalLight position={[3, 5, 4]} intensity={2.4} />
        <directionalLight position={[-3, 2, -3]} intensity={1.2} color="#ffd9b0" />
        {/* Studio : grandes sources douces qui dessinent les reflets de la laque. */}
        <Environment resolution={128} frames={1}>
          <Lightformer intensity={3} position={[0, 4, 4]} scale={[8, 3, 1]} />
          <Lightformer intensity={2} position={[0, 3, -4]} scale={[8, 2, 1]} color="#ffe8cc" />
          <Lightformer intensity={1.4} position={[-4, 2, 0]} rotation-y={Math.PI / 2} scale={[6, 2, 1]} color="#a9c4ff" />
          <Lightformer intensity={1.4} position={[4, 2, 0]} rotation-y={-Math.PI / 2} scale={[6, 2, 1]} color="#ffd0b0" />
        </Environment>
        <group position={[0, -0.25, 0]}>
          <Turntable kind={kind} />
        </group>
        <ContactShadows position={[0, -0.56, 0]} opacity={0.5} scale={5} blur={2.2} far={2} />
        <OrbitControls enablePan={false} enableZoom={false} minPolarAngle={0.6} maxPolarAngle={1.4} target={[0, 0.15, 0]} />
      </Canvas>
    </div>
  );
}
