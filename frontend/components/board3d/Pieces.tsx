"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import { easing } from "maath";
import { PEDESTAL, PIECE_SHAPES, pieceEdges, pieceGeometry, sqWorld, TEAM } from "./scene";
import { SKINS, type Skin, type SkinId } from "./skins";
import type { Kind, MoveRecord, PieceT, Side } from "@/lib/types";

const STEP_S = 0.17; // durée d'une marche
const geometries = new Map<string, THREE.BufferGeometry>();
function geo(kind: Kind, bevel?: number) {
  const key = `${kind}:${bevel ?? "d"}`;
  if (!geometries.has(key)) geometries.set(key, pieceGeometry(kind, bevel));
  return geometries.get(key)!;
}

const SOCLE = 0.085; // hauteur du socle
const edgeGeometries = new Map<Kind, THREE.BufferGeometry>();
function edges(kind: Kind) {
  if (!edgeGeometries.has(kind)) edgeGeometries.set(kind, pieceEdges(kind));
  return edgeGeometries.get(kind)!;
}
const pedestalMats = {
  1: new THREE.MeshPhysicalMaterial({ color: TEAM[1].dark, roughness: 0.35, metalness: 0.3, clearcoat: 0.5 }),
  2: new THREE.MeshPhysicalMaterial({ color: TEAM[2].dark, roughness: 0.35, metalness: 0.3, clearcoat: 0.5 }),
};

const ringGeo = new THREE.TorusGeometry(0.34, 0.014, 8, 56);
const auraGeo = new THREE.CircleGeometry(0.62, 48);
const UP = new THREE.Vector3(0, 1, 0);

/**
 * Pièce facettée laquée : faces planes nettes, micro-biseau sur les arêtes (qui accroche
 * la lumière), liseré lumineux sur les arêtes vives, socle tourné aux couleurs du camp.
 * `skin` habille les pièces d'un bot (voir skins.ts) sans changer leur forme.
 */
export function PieceBody({
  owner,
  kind,
  highlight,
  dim,
  skin = "team",
}: {
  owner: Side;
  kind: Kind;
  highlight: number;
  dim?: boolean;
  skin?: SkinId;
}) {
  if (skin !== "team") return <SkinnedBody owner={owner} kind={kind} highlight={highlight} skin={skin} />;
  const team = TEAM[owner];
  return (
    <>
      <mesh geometry={PEDESTAL} material={pedestalMats[owner]} castShadow receiveShadow />
      <mesh geometry={geo(kind)} position={[0, SOCLE, 0]} castShadow>
        <meshPhysicalMaterial
          color={team.main}
          roughness={0.22}
          metalness={0.05}
          clearcoat={1}
          clearcoatRoughness={0.08}
          envMapIntensity={1.25}
          emissive={team.glow}
          emissiveIntensity={0.06 + highlight * 0.45}
          transparent={dim}
          opacity={dim ? 0.55 : 1}
        />
      </mesh>
      <lineSegments geometry={edges(kind)} position={[0, SOCLE, 0]} raycast={() => null}>
        <lineBasicMaterial color={team.glow} transparent opacity={0.75} toneMapped={false} />
      </lineSegments>
    </>
  );
}

/** Un pic : position de sa base (enfoncée dans la pièce) et orientation. */
interface Spike {
  pos: [number, number, number];
  quat: THREE.Quaternion;
  len: number;
  radius: number;
}

function spikeAt(base: THREE.Vector3, dir: THREE.Vector3, len: number, radius: number, sink: number): Spike {
  const d = dir.clone().normalize();
  // Le cône est centré sur sa hauteur : on le recule d'une demi-longueur, et on enfonce
  // sa base dans la pièce pour qu'il en sorte sans jour visible.
  const center = base.clone().addScaledVector(d, len / 2 - sink);
  return { pos: center.toArray() as [number, number, number], quat: new THREE.Quaternion().setFromUnitVectors(UP, d), len, radius };
}

/** Pics qui prolongent la forme : un par pointe du sommet, d'autres le long des arêtes. */
function buildSpikes(kind: Kind, s: Skin): Spike[] {
  const shape = PIECE_SHAPES[kind];
  const out: Spike[] = [];
  const lift = new THREE.Vector3(0, s.bevel, 0); // la géométrie est remontée du biseau
  const core = new THREE.Vector3(0, shape.height * 0.3, 0);
  if (s.tipSpikes) {
    for (const t of shape.tips) {
      const tip = t.clone().add(lift);
      // Dans l'axe « cœur → pointe » : les pointes s'allongent sans changer d'allure.
      const dir = tip.clone().sub(core);
      dir.y = Math.max(dir.y, 0.25);
      out.push(spikeAt(tip, dir, s.tipSpikes, 0.028 + s.tipSpikes * 0.1, 0.02));
    }
  }
  if (s.sideSpikes) {
    const n = s.sideCount ?? 1;
    for (const b of shape.base) {
      // Arête qui relie ce coin de la base à la pointe la plus proche.
      const tip = shape.tips.reduce((a, t) => (t.distanceTo(b) < a.distanceTo(b) ? t : a));
      for (let k = 1; k <= n; k++) {
        const p = b.clone().lerp(tip, k / (n + 1)).add(lift);
        const out2 = new THREE.Vector3(p.x, 0, p.z).normalize();
        const dir = out2.multiplyScalar(1).add(new THREE.Vector3(0, 0.55, 0));
        out.push(spikeAt(p, dir, s.sideSpikes * (k === 1 ? 1 : 0.8), 0.022 + s.sideSpikes * 0.12, 0.025));
      }
    }
  }
  return out;
}

const SPIKE_GEO = new THREE.ConeGeometry(1, 1, 6, 1);

/** Pièce d'un bot : même forme, matière et pics aux couleurs de son rang. */
function SkinnedBody({ owner, kind, highlight, skin }: { owner: Side; kind: Kind; highlight: number; skin: Exclude<SkinId, "team"> }) {
  const s = SKINS[skin];
  const team = TEAM[owner];
  const body = useRef<THREE.Group>(null);
  const aura = useRef<THREE.MeshBasicMaterial>(null);
  const animated = !!(s.pulse || s.float || s.aura);
  const phase = useMemo(() => Math.random() * Math.PI * 2, []);
  const spikes = useMemo(() => buildSpikes(kind, s), [kind, s]);

  // Une seule matière pour le corps ET les pics : ils font partie de la pièce.
  const material = useMemo(
    () =>
      new THREE.MeshPhysicalMaterial({
        color: s.color,
        roughness: s.roughness,
        metalness: s.metalness,
        clearcoat: s.clearcoat,
        clearcoatRoughness: 0.1,
        envMapIntensity: 1.25,
        emissive: new THREE.Color(s.emissive ?? team.glow),
        emissiveIntensity: s.emissiveIntensity ?? 0.02,
      }),
    [s, team.glow],
  );
  useEffect(() => () => material.dispose(), [material]);
  useEffect(() => {
    material.emissiveIntensity = (s.emissiveIntensity ?? 0.02) + highlight * 0.4;
  }, [highlight, material, s]);

  useFrame((state) => {
    if (!animated) return;
    const t = state.clock.elapsedTime + phase;
    if (s.pulse) {
      const [lo, hi] = s.pulse;
      material.emissiveIntensity = lo + (hi - lo) * (0.5 + 0.5 * Math.sin(t * 2.2)) + highlight * 0.4;
    }
    if (body.current && s.float) body.current.position.y = SOCLE + 0.05 + Math.sin(t * 1.8) * 0.03;
    if (aura.current) aura.current.opacity = 0.18 + 0.22 * (0.5 + 0.5 * Math.sin(t * 2.2));
    state.invalidate();
  });

  return (
    <>
      {s.aura && (
        <mesh geometry={auraGeo} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.004, 0]} raycast={() => null} renderOrder={1}>
          <meshBasicMaterial ref={aura} color={s.aura} transparent opacity={0.3} depthWrite={false} toneMapped={false} />
        </mesh>
      )}
      <mesh geometry={PEDESTAL} material={pedestalMats[owner]} castShadow receiveShadow />
      {/* Anneau aux couleurs du camp : le repère « à qui est cette pièce ». */}
      <mesh geometry={ringGeo} position={[0, SOCLE + 0.002, 0]} rotation={[Math.PI / 2, 0, 0]} raycast={() => null}>
        <meshBasicMaterial color={team.main} toneMapped={false} />
      </mesh>
      <group ref={body} position={[0, s.float ? SOCLE + 0.05 : SOCLE, 0]}>
        <mesh geometry={geo(kind, s.bevel)} material={material} castShadow />
        {s.edgeOpacity > 0 && (
          <lineSegments geometry={edges(kind)} raycast={() => null}>
            <lineBasicMaterial color={s.edgeColor ?? team.glow} transparent opacity={s.edgeOpacity} toneMapped={!s.edgeGlow} />
          </lineSegments>
        )}
        {spikes.map((sp, i) => (
          <mesh
            key={i}
            geometry={SPIKE_GEO}
            material={material}
            position={sp.pos}
            quaternion={sp.quat}
            scale={[sp.radius, sp.len, sp.radius]}
            castShadow
          />
        ))}
      </group>
    </>
  );
}

interface Anim {
  key: number; // numéro du coup : une animation ne joue qu'une fois
  points: THREE.Vector3[];
  start: number;
  delay: number;
  // Après le chemin : sortie (glisse hors du plateau) ou éjection (capture).
  tail?: "exit" | "capture";
  owner: Side;
}

/** Position le long d'un chemin case par case, avec un petit saut à chaque marche. */
function along(points: THREE.Vector3[], t: number, out: THREE.Vector3): boolean {
  const steps = points.length - 1;
  if (steps <= 0) {
    out.copy(points[0]);
    return true;
  }
  const f = Math.min(t / STEP_S, steps);
  const i = Math.min(Math.floor(f), steps - 1);
  const k = f - i;
  const a = points[i];
  const b = points[i + 1];
  const ease = k * k * (3 - 2 * k);
  out.lerpVectors(a, b, ease);
  const hop = 0.22 + Math.abs(b.y - a.y) * 0.6;
  out.y = a.y + (b.y - a.y) * ease + Math.sin(Math.PI * k) * hop;
  return f >= steps;
}

function PieceMesh({
  piece,
  heights,
  anim,
  selected,
  movable,
  intro,
  introDelay,
  onDown,
  onHover,
  skin = "team",
}: {
  skin?: SkinId;
  piece: PieceT;
  heights: number[];
  anim: Anim | null;
  selected: boolean;
  movable: boolean;
  intro: boolean;
  introDelay: number;
  onDown?: (piece: PieceT, e: ThreeEvent<PointerEvent>) => void;
  onHover?: (sq: number | null) => void;
}) {
  const group = useRef<THREE.Group>(null);
  const target = useMemo(() => sqWorld(piece.sq, heights), [piece.sq, heights]);
  const animRef = useRef<Anim | null>(null);
  const born = useRef(performance.now() / 1000);
  const [hover, setHover] = useState(false);

  const mounted = useRef(false);
  const playedKey = useRef<number | null>(null);
  useLayoutEffect(() => {
    const g = group.current;
    if (!g) return;
    if (anim && anim.key !== playedKey.current) {
      playedKey.current = anim.key;
      animRef.current = { ...anim, start: performance.now() / 1000 };
    } else if (!mounted.current) {
      // Première apparition : posée sur sa case (ou lâchée d'en haut pour l'intro).
      g.position.copy(target);
      if (intro) g.position.y += 5;
    }
    // Sinon (navigation dans l'historique) : la pièce glisse vers sa case via useFrame.
    mounted.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anim, target]);

  const tmp = useMemo(() => new THREE.Vector3(), []);
  useFrame((state, delta) => {
    const g = group.current;
    if (!g) return;
    const a = animRef.current;
    const now = performance.now() / 1000;
    if (a) {
      const done = along(a.points, Math.max(0, now - a.start - a.delay), tmp);
      g.position.copy(tmp);
      if (done) animRef.current = null;
      state.invalidate();
      return;
    }
    if (intro && now - born.current < introDelay) {
      state.invalidate();
      return;
    }
    const lift = selected ? 0.22 : hover && movable ? 0.1 : 0;
    tmp.set(target.x, target.y + lift, target.z);
    if (easing.damp3(g.position, tmp, intro ? 0.18 : 0.08, delta)) state.invalidate();
    const spin = selected ? g.rotation.y + delta * 1.2 : Math.round(g.rotation.y / (Math.PI * 2)) * Math.PI * 2;
    if (easing.damp(g.rotation, "y", spin, 0.25, delta)) state.invalidate();
  });

  return (
    <group
      ref={group}
      onPointerDown={(e) => {
        e.stopPropagation();
        onDown?.(piece, e);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHover(true);
        onHover?.(piece.sq);
        document.body.style.cursor = movable ? "pointer" : "";
      }}
      onPointerOut={() => {
        setHover(false);
        document.body.style.cursor = "";
      }}
    >
      <PieceBody owner={piece.owner} kind={piece.kind} highlight={selected ? 1 : hover && movable ? 0.5 : 0} skin={skin} />
      {selected && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]} raycast={() => null}>
          <ringGeometry args={[0.44, 0.52, 48]} />
          <meshBasicMaterial color="#f7ec74" toneMapped={false} />
        </mesh>
      )}
    </group>
  );
}

/** Pièce qui quitte le plateau : sortie (vers l'arrivée) ou capture (éjectée). */
function Ghost({ piece, anim, onDone, skin = "team" }: { piece: PieceT; anim: Anim; onDone: () => void; skin?: SkinId }) {
  const group = useRef<THREE.Group>(null);
  const start = useRef(performance.now() / 1000);
  const tmp = useMemo(() => new THREE.Vector3(), []);
  const flingDir = useMemo(() => {
    const p = anim.points[anim.points.length - 1];
    return new THREE.Vector3(p.x >= 0 ? 1 : -1, 0, 0);
  }, [anim]);
  const doneRef = useRef(false);

  useFrame((state) => {
    const g = group.current;
    if (!g || doneRef.current) return;
    const t = performance.now() / 1000 - start.current - anim.delay;
    state.invalidate();
    if (t < 0) {
      g.position.copy(anim.points[0]);
      return;
    }
    const last = anim.points[anim.points.length - 1];
    if (anim.tail === "exit") {
      const pathDone = along(anim.points, t, tmp);
      if (!pathDone) {
        g.position.copy(tmp);
        return;
      }
      const k = (t - (anim.points.length - 1) * STEP_S) / 0.9;
      const dir = anim.owner === 1 ? -1 : 1;
      g.position.set(last.x, last.y + k * k * 4, last.z + dir * k * 2.2);
      g.scale.setScalar(Math.max(0.001, 1 - k));
      g.rotation.y += 0.25;
      if (k >= 1) {
        doneRef.current = true;
        onDone();
      }
    } else {
      // Capture : la pièce vaincue est projetée hors du plateau en tournoyant.
      const k = t / 0.9;
      g.position.set(last.x + flingDir.x * k * 5, last.y + Math.sin(Math.min(k, 1) * Math.PI) * 2.2 - k * k * 2, last.z);
      g.rotation.z = flingDir.x * -k * 6;
      g.rotation.x = k * 3;
      g.scale.setScalar(Math.max(0.001, 1 - k * 0.8));
      if (k >= 1) {
        doneRef.current = true;
        onDone();
      }
    }
  });

  return (
    <group ref={group} position={anim.points[0]}>
      <PieceBody owner={piece.owner} kind={piece.kind} highlight={anim.tail === "exit" ? 1 : 0} skin={skin} />
    </group>
  );
}

export function Pieces({
  pieces,
  heights,
  lastMove,
  animate,
  selectedId,
  movableIds,
  intro,
  onPieceDown,
  onHover,
  onAnimating,
  skins,
}: {
  skins?: Partial<Record<Side, SkinId>>;
  pieces: PieceT[];
  heights: number[];
  lastMove: MoveRecord | null;
  animate: boolean;
  selectedId: string | null;
  movableIds: Set<string>;
  intro: boolean;
  onPieceDown?: (piece: PieceT, e: ThreeEvent<PointerEvent>) => void;
  onHover?: (sq: number | null) => void;
  onAnimating?: (busy: boolean) => void;
}) {
  const prev = useRef<Map<string, PieceT>>(new Map());
  const [ghosts, setGhosts] = useState<{ key: string; piece: PieceT; anim: Anim }[]>([]);
  const animKey = useRef<number>(-1);
  const [anims, setAnims] = useState<Record<string, Anim>>({});

  useLayoutEffect(() => {
    const before = prev.current;
    const now = new Map(pieces.map((p) => [p.id, p]));
    const fresh = animate && lastMove && lastMove.ply !== animKey.current && before.size > 0;
    if (fresh && lastMove) {
      animKey.current = lastMove.ply;
      const pts = lastMove.path.map((s) => sqWorld(s, heights));
      const walk = Math.max(0, lastMove.path.length - 1) * STEP_S;
      const next: Record<string, Anim> = {};
      const newGhosts: typeof ghosts = [];
      if (lastMove.kind === "move" || lastMove.kind === "attack") {
        next[lastMove.pieceId] = { key: lastMove.ply, points: pts, start: 0, delay: 0, owner: lastMove.side };
      }
      for (const [id, p] of before) {
        if (now.has(id)) continue;
        if (lastMove.kind === "exit" && id === lastMove.pieceId) {
          newGhosts.push({ key: `${id}-${lastMove.ply}`, piece: p, anim: { key: lastMove.ply, points: pts, start: 0, delay: 0, tail: "exit", owner: p.owner } });
        } else if (lastMove.capturedId === id) {
          newGhosts.push({
            key: `${id}-${lastMove.ply}`,
            piece: p,
            anim: { key: lastMove.ply, points: [sqWorld(p.sq, heights)], start: 0, delay: walk - STEP_S * 0.4, tail: "capture", owner: p.owner },
          });
        }
      }
      setAnims(next);
      if (newGhosts.length) setGhosts((g) => [...g, ...newGhosts]);
      onAnimating?.(true);
      const t = setTimeout(() => onAnimating?.(false), (walk + 0.15) * 1000);
      prev.current = now;
      return () => clearTimeout(t);
    }
    if (!animate && Object.keys(anims).length) setAnims({});
    // Coup déjà connu (montage, retour d'historique, simple rafraîchissement) : on ne
    // le rejoue pas.
    animKey.current = lastMove?.ply ?? -1;
    prev.current = now;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pieces, lastMove, animate, heights]);

  return (
    <group>
      {pieces.map((p, i) => (
        <PieceMesh
          key={p.id}
          piece={p}
          heights={heights}
          anim={anims[p.id] ?? null}
          selected={selectedId === p.id}
          movable={movableIds.has(p.id)}
          intro={intro}
          introDelay={0.15 + i * 0.06}
          onDown={onPieceDown}
          onHover={onHover}
          skin={skins?.[p.owner]}
        />
      ))}
      {ghosts.map((g) => (
        <Ghost key={g.key} piece={g.piece} anim={g.anim} skin={skins?.[g.piece.owner]} onDone={() => setGhosts((all) => all.filter((x) => x.key !== g.key))} />
      ))}
    </group>
  );
}
