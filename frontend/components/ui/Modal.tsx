"use client";

import { useEffect } from "react";
import { useT } from "@/lib/i18n/client";
import { IconClose } from "./icons";

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose?: () => void;
  title?: React.ReactNode;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const t = useT();
  useEffect(() => {
    if (!open || !onClose) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modalBackdrop" onClick={onClose} role="presentation">
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal onClick={(e) => e.stopPropagation()}>
        {(title || onClose) && (
          <div className="modalHead">
            <h2>{title}</h2>
            {onClose && (
              <button className="iconBtn" onClick={onClose} aria-label={t.common.actions.close}>
                <IconClose />
              </button>
            )}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
