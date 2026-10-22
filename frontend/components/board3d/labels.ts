import * as THREE from "three";

// Textes du plateau (coordonnées, hauteurs) dessinés sur canvas : aucune police à
// télécharger, une texture partagée par libellé.

const cache = new Map<string, THREE.CanvasTexture>();

export function labelTexture(text: string, color = "#e8e6e3", weight = 700): THREE.CanvasTexture {
  const key = `${text}|${color}|${weight}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext("2d")!;
  ctx.clearRect(0, 0, 128, 128);
  ctx.fillStyle = color;
  ctx.font = `${weight} 84px system-ui, -apple-system, "Segoe UI", sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 64, 70);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  cache.set(key, tex);
  return tex;
}
