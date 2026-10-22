"use client";

import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { ThreeEvent } from "@react-three/fiber";
import { RoundedBox } from "@react-three/drei";
import { FLOOR, columnGeometry, topY, TEAM } from "./scene";
import { labelTexture } from "./labels";
import { LETTERS } from "@/lib/game";
import type { Side } from "@/lib/types";

interface Props {
  heights: number[];
  mode: string;
  orientation: Side;
  showHeights: boolean;
  shadows: boolean;
  /** Niveau réel des cases de hauteur 0 affichées (couleurs fidèles au relief d'origine). */
  colorOffset?: number;
  onSquareDown?: (sq: number, e: ThreeEvent<PointerEvent>) => void;
  onSquareHover?: (sq: number | null) => void;
}

const SLAB = 11.2;

/** Un groupe d'instances par hauteur : chaque colonne partage la géométrie de son niveau. */
function HeightGroup({
  mode,
  h,
  colorOffset,
  squares,
  shadows,
  onSquareDown,
  onSquareHover,
}: {
  mode: string;
  h: number;
  colorOffset: number;
  squares: number[];
  shadows: boolean;
  onSquareDown?: Props["onSquareDown"];
  onSquareHover?: Props["onSquareHover"];
}) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const geometry = useMemo(() => columnGeometry(mode, h, h + colorOffset), [mode, h, colorOffset]);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const m = new THREE.Matrix4();
    const c = new THREE.Color();
    squares.forEach((sq, i) => {
      const x = sq % 10;
      const y = Math.floor(sq / 10);
      m.makeTranslation(x - 4.5, 0, 4.5 - y);
      mesh.setMatrixAt(i, m);
      // Damier discret, comme les cases claires/foncées d'un échiquier.
      c.setScalar((x + y) % 2 === 0 ? 1 : 0.87);
      mesh.setColorAt(i, c);
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [squares]);
  useLayoutEffect(() => () => geometry.dispose(), [geometry]);

  return (
    <instancedMesh
      ref={ref}
      args={[geometry, undefined, squares.length]}
      castShadow={shadows}
      receiveShadow={shadows}
      onPointerDown={(e) => {
        if (e.instanceId === undefined) return;
        e.stopPropagation();
        onSquareDown?.(squares[e.instanceId], e);
      }}
      onPointerMove={(e) => {
        if (e.instanceId === undefined) return;
        e.stopPropagation();
        onSquareHover?.(squares[e.instanceId]);
      }}
    >
      <meshStandardMaterial vertexColors roughness={0.82} metalness={0.02} />
    </instancedMesh>
  );
}

export function Terrain({ heights, mode, orientation, showHeights, shadows, colorOffset = 0, onSquareDown, onSquareHover }: Props) {
  const groups = useMemo(() => {
    const byH = new Map<number, number[]>();
    heights.forEach((h, sq) => {
      if (!byH.has(h)) byH.set(h, []);
      byH.get(h)!.push(sq);
    });
    return [...byH.entries()];
  }, [heights]);

  const flip = orientation === 2 ? Math.PI : 0;

  return (
    <group onPointerLeave={() => onSquareHover?.(null)}>
      {groups.map(([h, squares]) => (
        <HeightGroup
          key={`${mode}-${h}-${colorOffset}`}
          mode={mode}
          h={h}
          colorOffset={colorOffset}
          squares={squares}
          shadows={shadows}
          onSquareDown={onSquareDown}
          onSquareHover={onSquareHover}
        />
      ))}

      {/* Socle */}
      <RoundedBox args={[SLAB, 0.5, SLAB]} radius={0.16} smoothness={4} position={[0, FLOOR - 0.25, 0]} receiveShadow={shadows}>
        <meshStandardMaterial color="#201d1a" roughness={0.55} metalness={0.25} />
      </RoundedBox>

      {/* Lignes d'arrivée : rouge sort par le fond (rangée 10), bleu par l'avant (rangée 1). */}
      <mesh position={[0, FLOOR + 0.02, -5.18]}>
        <boxGeometry args={[10, 0.05, 0.16]} />
        <meshStandardMaterial color={TEAM[1].main} emissive={TEAM[1].main} emissiveIntensity={1.6} toneMapped={false} />
      </mesh>
      <mesh position={[0, FLOOR + 0.02, 5.18]}>
        <boxGeometry args={[10, 0.05, 0.16]} />
        <meshStandardMaterial color={TEAM[2].main} emissive={TEAM[2].main} emissiveIntensity={1.6} toneMapped={false} />
      </mesh>

      {/* Coordonnées : lettres devant/derrière, chiffres à gauche/droite. */}
      {Array.from({ length: 10 }, (_, i) => (
        <group key={`c${i}`}>
          {[5.45, -5.45].map((z) => (
            <mesh key={z} position={[i - 4.5, FLOOR + 0.006, z]} rotation={[-Math.PI / 2, 0, flip]}>
              <planeGeometry args={[0.32, 0.32]} />
              <meshBasicMaterial map={labelTexture(LETTERS[i], "#8b8782")} transparent depthWrite={false} />
            </mesh>
          ))}
          {[-5.4, 5.4].map((x) => (
            <mesh key={x} position={[x, FLOOR + 0.006, 4.5 - i]} rotation={[-Math.PI / 2, 0, flip]}>
              <planeGeometry args={[0.32, 0.32]} />
              <meshBasicMaterial map={labelTexture(String(i + 1), "#8b8782")} transparent depthWrite={false} />
            </mesh>
          ))}
        </group>
      ))}

      {showHeights &&
        heights.map((h, sq) => (
          <mesh
            key={`h${sq}`}
            position={[(sq % 10) - 4.5 + 0.28, topY(h) + 0.006, 4.5 - Math.floor(sq / 10) + (orientation === 1 ? 0.28 : -0.28)]}
            rotation={[-Math.PI / 2, 0, flip]}
            raycast={() => null}
          >
            <planeGeometry args={[0.3, 0.3]} />
            <meshBasicMaterial map={labelTexture(String(h + colorOffset), "#ffffff", 800)} transparent opacity={0.75} depthWrite={false} />
          </mesh>
        ))}
    </group>
  );
}
