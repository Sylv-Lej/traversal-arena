"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { ContactShadows, Environment, Lightformer, Line, OrbitControls } from "@react-three/drei";
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing";
import { easing } from "maath";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { Terrain } from "./Terrain";
import { Pieces } from "./Pieces";
import type { SkinId } from "./skins";
import { FLOOR, sqWorld, topY } from "./scene";
import type { LegalMove, MoveRecord, PieceT, Side } from "@/lib/types";
import { resolveQuality, useSettings } from "@/lib/settings";
import { useT } from "@/lib/i18n/client";

type BubbleInfo = { attack: number; defense: number; charge: boolean } | null;

export interface Board3DProps {
  heights: number[];
  terrainMode: string;
  pieces: PieceT[];
  orientation: Side;
  legalMoves?: LegalMove[];
  lastMove?: MoveRecord | null;
  animate?: boolean;
  interactive?: boolean;
  autoRotate?: boolean;
  /** Angle de caméra prédéfini (boutons au-dessus du plateau). */
  view?: CameraView;
  intro?: boolean;
  recenterKey?: number;
  /** Cadrage sur une zone du plateau (coordonnées de cases), pour les situations de jeu. */
  focus?: { x: number; y: number; radius: number };
  /** Pièce sélectionnée d'office (et attaque montrée d'office) à chaque nouvelle position. */
  autoSelect?: string | null;
  autoPreview?: number | null;
  /** Habillage des pièces par camp (pièces des bots). */
  skins?: Partial<Record<Side, SkinId>>;
  /** Coup conseillé par l'analyse, tracé en doré par-dessus la position. */
  hint?: { path: number[]; kind: string; owner: Side } | null;
  onMove?: (move: LegalMove) => void;
  onPreview?: (move: LegalMove | null) => void;
  className?: string;
}

// --- Caméra --------------------------------------------------------------------------
const TARGET: [number, number, number] = [0, 0.4, 0];

export type CameraView = "default" | "top" | "left" | "right" | "low";

/**
 * Angles fixes, vus depuis le camp du joueur : élévation au-dessus de l'horizon et
 * azimut (négatif = à sa gauche), plus les rayons à faire tenir dans le cadre.
 */
const VIEWS: Record<CameraView, { elev: number; azim: number; fit: [number, number] }> = {
  default: { elev: 40, azim: 0, fit: [7.9, 6.6] },
  top: { elev: 89.9, azim: 0, fit: [6.3, 6.3] },
  left: { elev: 34, azim: -62, fit: [8.4, 6.8] },
  right: { elev: 34, azim: 62, fit: [8.4, 6.8] },
  low: { elev: 16, azim: 0, fit: [8.2, 5.4] },
};

/** Correction de la vue 3/4 en portrait : élévation ajoutée et rayon horizontal retiré. */
const PORTRAIT = { elev: 22, fitH: 1.7 };

/** Déplacement de la vue : à la souris, clic gauche = rotation, clic molette (ou droit) =
 * translation, molette = zoom ; au doigt, un doigt = translation, deux doigts = rotation
 * et pincement. Le centre de la vue reste au-dessus du plateau (± PAN_LIMIT). */
const MOUSE_BUTTONS = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.PAN };
const TOUCHES = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_ROTATE };
const PAN_LIMIT = 5;

function CameraRig({
  orientation,
  view,
  autoRotate,
  intro,
  recenterKey,
  focus,
}: {
  orientation: Side;
  view: CameraView;
  autoRotate: boolean;
  intro: boolean;
  recenterKey: number;
  focus?: Board3DProps["focus"];
}) {
  const { camera, size, invalidate } = useThree();
  const controls = useRef<OrbitControlsImpl>(null);
  const goal = useRef<THREE.Vector3 | null>(null);
  const first = useRef(true);
  const fx = focus?.x;
  const fy = focus?.y;
  const fr = focus?.radius;
  const center = useMemo(
    () => (fx !== undefined && fy !== undefined ? new THREE.Vector3(fx - 4.5, 0.6, 4.5 - fy) : new THREE.Vector3(...TARGET)),
    [fx, fy],
  );

  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera;
    const aspect = size.width / Math.max(1, size.height);
    const halfV = THREE.MathUtils.degToRad(cam.fov / 2);
    const halfH = Math.atan(Math.tan(halfV) * aspect);
    const dir = orientation === 1 ? 1 : -1;
    // Distance pour que le plateau tienne dans le cadre, quelle que soit la forme de
    // l'écran : en vue 3/4 il paraît plus large que haut, d'où deux rayons distincts.
    const preset = VIEWS[view];
    // Écran en portrait (téléphone) : la vue 3/4 se redresse pour que le plateau occupe
    // la hauteur disponible au lieu de flotter dans une bande étroite.
    const portrait = view === "default" && !fr ? THREE.MathUtils.clamp((1.1 - aspect) / 0.45, 0, 1) : 0;
    const [rH, rV] = fr ? [fr * 1.2, fr] : [preset.fit[0] - PORTRAIT.fitH * portrait, preset.fit[1]];
    const dist = Math.max(rH / Math.tan(halfH), rV / Math.tan(halfV));
    const e = THREE.MathUtils.degToRad(preset.elev + PORTRAIT.elev * portrait);
    const a = THREE.MathUtils.degToRad(preset.azim);
    // Le camp bleu regarde le plateau depuis l'autre bout : tout est mis en miroir.
    goal.current = new THREE.Vector3(
      Math.sin(a) * Math.cos(e) * dist * dir,
      Math.sin(e) * dist,
      Math.max(0.001, Math.cos(a) * Math.cos(e) * dist) * dir,
    ).add(center);
    if (first.current && intro) {
      camera.position.set(goal.current.x + 6 * dir, goal.current.y + 6, goal.current.z * 1.4);
    } else if (first.current) {
      camera.position.copy(goal.current);
    }
    first.current = false;
    invalidate();
  }, [orientation, view, size.width, size.height, recenterKey, camera, intro, invalidate, center, fr]);

  useFrame((state, delta) => {
    const c = controls.current;
    if (goal.current) {
      const moving = easing.damp3(camera.position, goal.current, 0.35, delta);
      c?.target.copy(center);
      c?.update();
      if (!moving || camera.position.distanceTo(goal.current) < 0.02) goal.current = null;
      state.invalidate();
    }
    if (autoRotate) {
      c?.update();
      state.invalidate();
    }
  });

  // Translation bornée : on déplace cible ET caméra du même écart, la vue garde son angle.
  const clampPan = () => {
    const c = controls.current;
    if (!c) return;
    const t = c.target;
    const dx = THREE.MathUtils.clamp(t.x, center.x - PAN_LIMIT, center.x + PAN_LIMIT) - t.x;
    const dz = THREE.MathUtils.clamp(t.z, center.z - PAN_LIMIT, center.z + PAN_LIMIT) - t.z;
    if (dx || dz) {
      t.x += dx;
      t.z += dz;
      camera.position.x += dx;
      camera.position.z += dz;
    }
  };

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enablePan
      screenSpacePanning={false}
      mouseButtons={MOUSE_BUTTONS}
      touches={TOUCHES}
      onChange={clampPan}
      enableDamping
      dampingFactor={0.12}
      minDistance={fr ? 3 : 8}
      maxDistance={34}
      minPolarAngle={0}
      maxPolarAngle={Math.PI * 0.43}
      autoRotate={autoRotate}
      autoRotateSpeed={0.6}
      target={center.toArray() as [number, number, number]}
      onStart={() => {
        goal.current = null;
      }}
    />
  );
}

// --- Surbrillances -------------------------------------------------------------------

function Tile({ sq, heights, color, opacity = 0.5, size = 0.9 }: { sq: number; heights: number[]; color: string; opacity?: number; size?: number }) {
  const p = sqWorld(sq, heights);
  return (
    <mesh position={[p.x, p.y + 0.012, p.z]} rotation={[-Math.PI / 2, 0, 0]} raycast={() => null} renderOrder={2}>
      <planeGeometry args={[size, size]} />
      <meshBasicMaterial color={color} transparent opacity={opacity} depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

function Marker({ move, heights, hovered }: { move: LegalMove; heights: number[]; hovered: boolean }) {
  if (move.to === null) return null;
  const p = sqWorld(move.to, heights);
  const special = move.special !== null;
  if (move.kind === "attack") return <AttackMarker move={move} heights={heights} hovered={hovered} />;
  return (
    <>
      {hovered && <Tile sq={move.to} heights={heights} color={special ? "#b48cff" : "#9be07a"} opacity={0.45} />}
      <mesh position={[p.x, p.y + 0.02, p.z]} rotation={[-Math.PI / 2, 0, 0]} raycast={() => null} renderOrder={3}>
        <circleGeometry args={[hovered ? 0.19 : 0.15, 28]} />
        <meshBasicMaterial color={special ? "#c9a8ff" : "#b6f08f"} transparent opacity={0.9} depthWrite={false} toneMapped={false} />
      </mesh>
    </>
  );
}

/** Cible d'une attaque : la case occupée se teinte (les coins dépassent du socle) et un
 * chevron flotte au-dessus de la pièce visée — un marqueur au sol serait caché par elle. */
function AttackMarker({ move, heights, hovered }: { move: LegalMove; heights: number[]; hovered: boolean }) {
  const p = sqWorld(move.to!, heights);
  const ok = move.combat ? move.combat.attack >= move.combat.defense : true;
  const color = ok ? "#ff5a4f" : "#9a9a9a";
  const ref = useRef<THREE.Group>(null);
  useFrame((state) => {
    if (!ref.current) return;
    ref.current.position.y = p.y + 1.25 + Math.sin(state.clock.elapsedTime * 3) * 0.06;
    state.invalidate();
  });
  return (
    <>
      <Tile sq={move.to!} heights={heights} color={color} opacity={hovered ? 0.7 : 0.5} size={0.94} />
      <mesh position={[p.x, p.y + 0.02, p.z]} rotation={[-Math.PI / 2, 0, 0]} raycast={() => null} renderOrder={3}>
        <ringGeometry args={[0.44, 0.49, 40]} />
        <meshBasicMaterial color={color} transparent opacity={0.95} depthWrite={false} toneMapped={false} />
      </mesh>
      <group ref={ref} position={[p.x, p.y + 1.25, p.z]} scale={hovered ? 1.2 : 1}>
        <mesh rotation={[Math.PI, 0, 0]} raycast={() => null}>
          <coneGeometry args={[0.16, 0.3, 4]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={hovered ? 1.6 : 0.9} toneMapped={false} />
        </mesh>
      </group>
    </>
  );
}

/** Portail de sortie au bord du plateau, dans l'axe de la colonne d'arrivée. */
function ExitPortal({
  move,
  heights,
  owner,
  hovered,
  onPick,
  onHover,
}: {
  move: LegalMove;
  heights: number[];
  owner: Side;
  hovered: boolean;
  onPick: (pointerType: string) => void;
  onHover: (h: boolean) => void;
}) {
  const last = move.path[move.path.length - 1];
  const p = sqWorld(last, heights);
  const dir = owner === 1 ? -1 : 1;
  const ref = useRef<THREE.Group>(null);
  useFrame((state) => {
    if (!ref.current) return;
    ref.current.position.y = Math.max(p.y, topY(0)) + 0.55 + Math.sin(state.clock.elapsedTime * 3) * 0.08;
    state.invalidate();
  });
  return (
    <group
      ref={ref}
      position={[p.x, p.y + 0.55, p.z + dir * 0.95]}
      onPointerDown={(e) => {
        e.stopPropagation();
        onPick(e.nativeEvent.pointerType);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        onHover(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        onHover(false);
        document.body.style.cursor = "";
      }}
    >
      <mesh rotation={[(dir * Math.PI) / 2, 0, 0]}>
        <coneGeometry args={[0.26, 0.5, 4]} />
        <meshStandardMaterial color="#ffe066" emissive="#ffd23f" emissiveIntensity={hovered ? 2.4 : 1.4} toneMapped={false} />
      </mesh>
      <mesh rotation={[0, 0, 0]}>
        <torusGeometry args={[0.42, 0.04, 12, 48]} />
        <meshStandardMaterial color="#ffe066" emissive="#ffd23f" emissiveIntensity={hovered ? 2 : 1} toneMapped={false} />
      </mesh>
      {/* Zone de clic généreuse (doigts). */}
      <mesh visible={false}>
        <sphereGeometry args={[0.6, 8, 8]} />
      </mesh>
    </group>
  );
}

function PathLine({
  move,
  heights,
  owner,
  color = "#ffffff",
}: {
  move: { path: number[]; kind: string };
  heights: number[];
  owner: Side | null;
  color?: string;
}) {
  const pts = useMemo(() => {
    const out = move.path.map((s) => {
      const v = sqWorld(s, heights);
      v.y += 0.14;
      return v;
    });
    if (move.kind === "exit" && out.length) {
      const last = out[out.length - 1].clone();
      last.z += (owner === 1 ? -1 : 1) * 0.9;
      out.push(last);
    }
    return out;
  }, [move, heights, owner]);
  if (pts.length < 2) return null;
  return <Line points={pts} color={color} lineWidth={3} dashed dashSize={0.18} gapSize={0.1} transparent opacity={0.9} />;
}

/**
 * Bulle « ⚔ 3 vs 3 » au-dessus de la cible. Élément DOM ordinaire posé par-dessus le
 * canvas et déplacé à chaque image par projection caméra — plutôt que <Html> de drei,
 * qui crée/détruit une racine React à chaque apparition (erreur React 19 au démontage).
 */
function BubbleTracker({ target, el }: { target: THREE.Vector3 | null; el: React.RefObject<HTMLDivElement | null> }) {
  const { camera, size } = useThree();
  const v = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    const node = el.current;
    if (!node) return;
    if (!target) {
      node.style.opacity = "0";
      return;
    }
    v.copy(target).project(camera);
    const x = (v.x * 0.5 + 0.5) * size.width;
    const y = (-v.y * 0.5 + 0.5) * size.height;
    node.style.opacity = "1";
    node.style.transform = `translate(${x}px, ${y}px) translate(-50%, -100%)`;
  });
  return null;
}

// --- Scène ---------------------------------------------------------------------------

function Scene(
  props: Board3DProps & {
    heightOffset: number;
    quality: "high" | "medium" | "low";
    showHeights: boolean;
    bubbleEl: React.RefObject<HTMLDivElement | null>;
    onBubble: (b: BubbleInfo) => void;
    onConfirming: (c: boolean) => void;
  },
) {
  const {
    heights,
    terrainMode,
    pieces,
    orientation,
    legalMoves = [],
    lastMove = null,
    animate = true,
    interactive = false,
    autoRotate = false,
    view = "default",
    intro = false,
    recenterKey = 0,
    focus,
    autoSelect = null,
    autoPreview = null,
    hint = null,
    skins,
    onMove,
    onPreview,
    quality,
    showHeights,
    bubbleEl,
    onBubble,
    onConfirming,
    heightOffset,
  } = props;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverSq, setHoverSq] = useState<number | null>(null);
  const [hoverExit, setHoverExit] = useState(false);
  // Coup « armé » : case visée (ou la sortie) en attente de confirmation au doigt, ou
  // attaque montrée d'office (`autoPreview`).
  const [armed, setArmed] = useState<number | "exit" | null>(null);
  const [touchArmed, setTouchArmed] = useState(false); // armé au doigt : « touchez encore »
  const [busy, setBusy] = useState(false);

  const movesByPiece = useMemo(() => {
    const m = new Map<string, LegalMove[]>();
    for (const mv of legalMoves) {
      if (mv.kind === "pass") continue;
      if (!m.has(mv.pieceId)) m.set(mv.pieceId, []);
      m.get(mv.pieceId)!.push(mv);
    }
    return m;
  }, [legalMoves]);
  const movableIds = useMemo(() => new Set(interactive ? movesByPiece.keys() : []), [movesByPiece, interactive]);

  // Nouvelle position : on oublie la sélection (ou on reprend la sélection imposée).
  useEffect(() => {
    const keep = autoSelect && movesByPiece.has(autoSelect) ? autoSelect : null;
    setSelectedId(keep);
    setArmed(keep && autoPreview !== null ? autoPreview : null);
    setTouchArmed(false);
  }, [legalMoves, autoSelect, autoPreview, movesByPiece]);

  const selectedMoves = selectedId ? movesByPiece.get(selectedId) ?? [] : [];
  const bySquare = useMemo(() => new Map(selectedMoves.filter((m) => m.to !== null).map((m) => [m.to as number, m])), [selectedMoves]);
  const exitMove = selectedMoves.find((m) => m.kind === "exit") ?? null;
  const hovered = hoverExit ? exitMove : hoverSq !== null ? bySquare.get(hoverSq) ?? null : null;
  // Le survol prime ; sinon le coup « armé » (tap au doigt, ou aperçu imposé).
  const preview = hovered ?? (armed === "exit" ? exitMove : armed !== null ? bySquare.get(armed) ?? null : null);
  const occupied = useMemo(() => new Map(pieces.map((p) => [p.sq, p])), [pieces]);
  const selectedPiece = pieces.find((p) => p.id === selectedId) ?? null;

  useEffect(() => {
    onPreview?.(preview ?? null);
    const c = preview?.kind === "attack" ? preview.combat : null;
    onBubble(c ? { attack: c.attack, defense: c.defense, charge: c.attackTerms.some((x) => x.label === "charge") } : null);
  }, [preview, onPreview, onBubble]);
  const bubbleTarget = useMemo(() => {
    if (!preview || preview.kind !== "attack" || preview.to === null) return null;
    const p = sqWorld(preview.to, heights);
    return p.setY(p.y + 1.25);
  }, [preview, heights]);

  useEffect(() => onConfirming(touchArmed && armed !== null), [touchArmed, armed, onConfirming]);

  function disarm() {
    setArmed(null);
    setTouchArmed(false);
  }

  function play(move: LegalMove) {
    setSelectedId(null);
    disarm();
    onMove?.(move);
  }

  /** Au doigt, tout coup se confirme d'un second tap sur la même cible (évite les coups
   * joués par erreur sur un petit écran) ; à la souris, un clic suffit. */
  function pick(move: LegalMove, key: number | "exit", pointerType: string) {
    if (pointerType === "touch" && armed !== key) {
      setArmed(key);
      setTouchArmed(true);
      return;
    }
    play(move);
  }

  function pickSquare(sq: number, pointerType: string) {
    if (!interactive || busy) return;
    const move = bySquare.get(sq);
    if (move) {
      pick(move, sq, pointerType);
      return;
    }
    const piece = occupied.get(sq);
    if (piece && movableIds.has(piece.id)) {
      setSelectedId(piece.id === selectedId ? null : piece.id);
      disarm();
      return;
    }
    setSelectedId(null);
    disarm();
  }

  const lastSquares = useMemo(() => {
    if (!lastMove || lastMove.kind === "pass") return [];
    const out: number[] = [];
    if (lastMove.from !== null) out.push(lastMove.from);
    if (lastMove.to !== null) out.push(lastMove.to);
    return out;
  }, [lastMove]);

  const shadows = quality === "high";

  return (
    <>
      <CameraRig
        orientation={orientation}
        view={view}
        autoRotate={autoRotate}
        intro={intro}
        recenterKey={recenterKey}
        focus={focus}
      />

      <hemisphereLight args={["#dfe8ff", "#3a2f25", 0.55]} />
      <ambientLight intensity={0.25} />
      <directionalLight
        position={[6, 14, 8]}
        intensity={2.3}
        castShadow={shadows}
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-8}
        shadow-camera-right={8}
        shadow-camera-top={8}
        shadow-camera-bottom={-8}
        shadow-camera-near={1}
        shadow-camera-far={40}
        shadow-bias={-0.0004}
        shadow-normalBias={0.03}
      />
      <directionalLight position={[-8, 6, -6]} intensity={0.5} color="#9ab8ff" />

      {quality !== "low" && (
        <Environment resolution={128} frames={1}>
          <Lightformer intensity={2.2} position={[0, 6, 6]} scale={[12, 4, 1]} />
          <Lightformer intensity={1.2} position={[-6, 3, -4]} rotation-y={Math.PI / 2} scale={[8, 3, 1]} color="#a9c4ff" />
          <Lightformer intensity={1} position={[6, 3, -4]} rotation-y={-Math.PI / 2} scale={[8, 3, 1]} color="#ffd9b0" />
        </Environment>
      )}

      <Terrain
        heights={heights}
        mode={terrainMode}
        orientation={orientation}
        showHeights={showHeights}
        shadows={shadows}
        colorOffset={heightOffset}
        onSquareDown={(sq, e: ThreeEvent<PointerEvent>) => pickSquare(sq, e.nativeEvent.pointerType)}
        onSquareHover={interactive ? setHoverSq : undefined}
      />

      {lastSquares.map((sq) => (
        <Tile key={`last${sq}`} sq={sq} heights={heights} color="#f7ec74" opacity={0.42} />
      ))}
      {selectedPiece && <Tile sq={selectedPiece.sq} heights={heights} color="#f7ec74" opacity={0.55} />}

      {selectedMoves.map((m) =>
        m.kind === "exit" ? null : (
          <Marker key={`${m.kind}${m.to}`} move={m} heights={heights} hovered={preview === m} />
        ),
      )}
      {exitMove && selectedPiece && (
        <ExitPortal
          move={exitMove}
          heights={heights}
          owner={selectedPiece.owner}
          hovered={hoverExit}
          onPick={(pointerType) => pick(exitMove, "exit", pointerType)}
          onHover={setHoverExit}
        />
      )}
      {preview && <PathLine move={preview} heights={heights} owner={selectedPiece?.owner ?? null} />}
      {hint && hint.path.length > 0 && (
        <>
          <PathLine move={hint} heights={heights} owner={hint.owner} color="#f7c631" />
          {hint.kind !== "exit" && (
            <mesh
              position={(() => {
                const p = sqWorld(hint.path[hint.path.length - 1], heights);
                return [p.x, p.y + 0.03, p.z] as [number, number, number];
              })()}
              rotation={[-Math.PI / 2, 0, 0]}
              raycast={() => null}
              renderOrder={3}
            >
              <ringGeometry args={[0.3, 0.42, 40]} />
              <meshBasicMaterial color="#f7c631" transparent opacity={0.95} depthWrite={false} toneMapped={false} />
            </mesh>
          )}
        </>
      )}
      <BubbleTracker target={bubbleTarget} el={bubbleEl} />

      <Pieces
        pieces={pieces}
        heights={heights}
        lastMove={lastMove}
        animate={animate}
        selectedId={selectedId}
        movableIds={movableIds}
        intro={intro}
        onAnimating={setBusy}
        skins={skins}
        onHover={interactive ? setHoverSq : undefined}
        onPieceDown={(p, e) => pickSquare(p.sq, e.nativeEvent.pointerType)}
      />

      {quality !== "low" && (
        <ContactShadows position={[0, FLOOR - 0.52, 0]} opacity={0.55} scale={18} blur={2.6} far={4} frames={1} />
      )}

      {quality === "high" && (
        <EffectComposer multisampling={4}>
          <Bloom mipmapBlur luminanceThreshold={0.95} intensity={0.45} />
          <Vignette offset={0.25} darkness={0.55} />
        </EffectComposer>
      )}
    </>
  );
}

export default function Board3D(props: Board3DProps) {
  const t = useT();
  const settings = useSettings();
  // Calculée au premier rendu (composant client uniquement) : changer de qualité recrée
  // le canvas, on ne veut pas de ce flash au chargement.
  const quality = useMemo(() => resolveQuality(settings.quality), [settings.quality]);
  const bubbleEl = useRef<HTMLDivElement>(null);
  const [bubble, setBubble] = useState<BubbleInfo>(null);
  const [confirming, setConfirming] = useState(false);
  // Les cases les plus basses de chaque plateau reposent toujours à la même hauteur sur le
  // socle, quel que soit le niveau de départ du terrain (0, 1 ou 2 selon la carte). Le jeu
  // ne dépend que des écarts de hauteur : décaler tout le relief ne change aucune règle.
  const low = useMemo(() => Math.max(0, Math.min(...props.heights)), [props.heights]);
  const heights = useMemo(() => (low > 0 ? props.heights.map((h) => h - low) : props.heights), [props.heights, low]);

  return (
    <div className={props.className ?? "board3d"}>
      <div ref={bubbleEl} className="combatBubble floating" aria-hidden={!bubble}>
        {bubble && (
          <>
            <span className="atk">
              {bubble.charge && <span className="charge">⚡</span>}⚔ {bubble.attack}
            </span>
            <span className="vs">{t.board.versus}</span>
            <span className="def">🛡 {bubble.defense}</span>
            <span className={bubble.attack >= bubble.defense ? "ok" : "ko"}>{bubble.attack >= bubble.defense ? "✓" : "✗"}</span>
          </>
        )}
      </div>
      {confirming && <div className="tapConfirm">{t.board.tapAgain}</div>}
      <Canvas
        key={quality === "high" ? "hq" : "lq"}
        frameloop="demand"
        shadows={quality === "high"}
        dpr={quality === "low" ? 1 : quality === "medium" ? [1, 1.75] : [1, 2]}
        camera={{ fov: 38, near: 0.1, far: 200, position: [0, 16, 16] }}
        gl={{ antialias: quality !== "high", alpha: true, powerPreference: "high-performance" }}
        onCreated={({ gl }) => {
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.05;
        }}
        onPointerMissed={() => undefined}
        // Clic molette : pas de défilement automatique du navigateur (il sert à translater).
        onMouseDown={(e) => {
          if (e.button === 1) e.preventDefault();
        }}
      >
        <Scene {...props} heights={heights} heightOffset={low} quality={quality} showHeights={settings.showHeights} bubbleEl={bubbleEl} onBubble={setBubble} onConfirming={setConfirming} />
      </Canvas>
    </div>
  );
}
