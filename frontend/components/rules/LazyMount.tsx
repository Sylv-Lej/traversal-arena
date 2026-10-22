"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Ne monte son contenu (un canvas 3D) que lorsqu'il approche de l'écran, et le démonte
 * quand il s'en éloigne : une page de règles compte une dizaine de vues 3D, et les
 * navigateurs plafonnent le nombre de contextes WebGL actifs (surtout sur mobile).
 */
export function LazyMount({ children, className, minHeight }: { children: React.ReactNode; className?: string; minHeight?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: "400px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <div ref={ref} className={className} style={{ minHeight }}>
      {visible ? children : null}
    </div>
  );
}
