import { lazy, Suspense, useEffect, useRef, useState, type PointerEvent } from "react";

import LimyIcon from "./LimyIcon";

const LimyPanel = lazy(() => import("./LimyPanel"));

const SIZE = 56; // button diameter, px
const EDGE = 16; // minimum distance from the window edge
const GAP = 12; // space between button and panel
const DRAG_THRESHOLD = 5; // px of movement before a press counts as a drag, not a click
const PANEL_W = 380;
const PANEL_H = 540;
const POS_KEY = "limy-position";

/** Distance of the button from the bottom-right corner, so it stays there when the window resizes. */
interface Pos {
  right: number;
  bottom: number;
}

const DEFAULT_POS: Pos = { right: 24, bottom: 24 };

function clamp(p: Pos): Pos {
  return {
    right: Math.min(Math.max(EDGE, p.right), window.innerWidth - SIZE - EDGE),
    bottom: Math.min(Math.max(EDGE, p.bottom), window.innerHeight - SIZE - EDGE),
  };
}

function loadPos(): Pos {
  try {
    const p = JSON.parse(localStorage.getItem(POS_KEY) ?? "null");
    if (typeof p?.right === "number" && typeof p?.bottom === "number") return clamp(p);
  } catch {
    // storage unavailable or corrupt: fall back to the corner
  }
  return clamp(DEFAULT_POS);
}

function savePos(p: Pos) {
  try {
    localStorage.setItem(POS_KEY, JSON.stringify(p));
  } catch {
    // position just won't be remembered
  }
}

const within = (value: number, min: number, max: number) => Math.min(Math.max(min, value), max);

/**
 * Place the panel next to the button without covering it: above, else below, else to the
 * left, else to the right. Only on a screen too small for any of those may it overlap.
 */
export function panelStyle(pos: Pos, vw: number, vh: number) {
  const width = Math.min(PANEL_W, vw - 2 * EDGE);
  const height = Math.min(PANEL_H, vh - 2 * EDGE);
  const bTop = vh - pos.bottom - SIZE;
  const bLeft = vw - pos.right - SIZE;
  // Horizontally: right edges aligned; vertically: bottom edges aligned (kept on screen).
  const alignedLeft = within(bLeft + SIZE - width, EDGE, vw - width - EDGE);
  const alignedTop = within(bTop + SIZE - height, EDGE, vh - height - EDGE);

  if (bTop - GAP - height >= EDGE) return { left: alignedLeft, top: bTop - GAP - height, width, height };
  if (bTop + SIZE + GAP + height <= vh - EDGE) return { left: alignedLeft, top: bTop + SIZE + GAP, width, height };
  if (bLeft - GAP - width >= EDGE) return { left: bLeft - GAP - width, top: alignedTop, width, height };
  if (bLeft + SIZE + GAP + width <= vw - EDGE) return { left: bLeft + SIZE + GAP, top: alignedTop, width, height };
  return { left: alignedLeft, top: within(bTop - GAP - height, EDGE, vh - height - EDGE), width, height };
}

/**
 * Floating "Limy" chat button. Click to open a small chat; drag (while closed) to move it.
 * The position is remembered per browser.
 */
export default function LimyWidget() {
  const [pos, setPos] = useState<Pos>(loadPos);
  const [open, setOpen] = useState(false);
  const [viewport, setViewport] = useState({ w: window.innerWidth, h: window.innerHeight });
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ x: number; y: number; start: Pos; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Keep the button on screen when the window shrinks.
  useEffect(() => {
    const onResize = () => {
      setViewport({ w: window.innerWidth, h: window.innerHeight });
      setPos((p) => clamp(p));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  function onPointerDown(e: PointerEvent<HTMLButtonElement>) {
    if (open || e.button !== 0) return; // only movable while collapsed
    drag.current = { x: e.clientX, y: e.clientY, start: pos, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: PointerEvent<HTMLButtonElement>) {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    if (!d.moved) {
      d.moved = true;
      setDragging(true);
    }
    // Moving right/down means a smaller distance from the right/bottom edge.
    setPos(clamp({ right: d.start.right - dx, bottom: d.start.bottom - dy }));
  }

  function onPointerUp(e: PointerEvent<HTMLButtonElement>) {
    const d = drag.current;
    drag.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
    if (d?.moved) {
      suppressClick.current = true; // the click that follows a drag must not open the chat
      setDragging(false);
      setPos((p) => {
        savePos(p);
        return p;
      });
    }
  }

  function onClick() {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    setOpen((o) => !o);
  }

  return (
    <>
      {open && (
        <Suspense fallback={null}>
          <LimyPanel style={panelStyle(pos, viewport.w, viewport.h)} onClose={() => setOpen(false)} />
        </Suspense>
      )}
      <button
        ref={buttonRef}
        type="button"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onClick={onClick}
        aria-label={open ? "Close Limy chat" : "Chat with Limy"}
        aria-expanded={open}
        title={open ? "Close Limy" : "Chat with Limy (drag to move)"}
        style={{ right: pos.right, bottom: pos.bottom, width: SIZE, height: SIZE, touchAction: "none" }}
        className={`fixed z-[1100] flex select-none items-center justify-center rounded-full bg-brand text-white shadow-lg ring-4 ring-white transition-transform focus:outline-none focus-visible:ring-brand-dark ${
          dragging ? "scale-110 cursor-grabbing" : open ? "cursor-pointer" : "cursor-grab hover:scale-105"
        }`}
      >
        {open ? <span className="text-xl leading-none">✕</span> : <LimyIcon />}
      </button>
    </>
  );
}
