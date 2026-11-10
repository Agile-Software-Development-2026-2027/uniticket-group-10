import { useRef, type RefObject, type PointerEvent, type KeyboardEvent } from "react";

export function usePanelResize(panel: RefObject<HTMLElement | null>) {
  const drag = useRef<{ x: number; y: number; width: number; height: number; id: number } | null>(
    null,
  );
  function size(width: number, height: number) {
    if (!panel.current || window.matchMedia("(max-width: 576px)").matches) return;
    const bounds = panel.current.getBoundingClientRect();
    const margin = Math.max(16, window.innerWidth - bounds.right);
    panel.current.style.setProperty(
      "--assistant-panel-width",
      `${Math.min(bounds.right - margin, Math.max(320, width))}px`,
    );
    panel.current.style.setProperty(
      "--assistant-panel-height",
      `${Math.min(bounds.bottom - margin, Math.max(320, height))}px`,
    );
  }
  const stop = () => {
    drag.current = null;
  };
  return {
    onPointerDown(event: PointerEvent<HTMLButtonElement>) {
      if (!event.isPrimary || event.button !== 0 || !panel.current) return;
      event.preventDefault();
      event.currentTarget.focus({ preventScroll: true });
      event.currentTarget.setPointerCapture(event.pointerId);
      const bounds = panel.current.getBoundingClientRect();
      drag.current = {
        x: event.clientX,
        y: event.clientY,
        width: bounds.width,
        height: bounds.height,
        id: event.pointerId,
      };
    },
    onPointerMove(event: PointerEvent<HTMLButtonElement>) {
      const start = drag.current;
      if (start?.id === event.pointerId)
        size(start.width + start.x - event.clientX, start.height + start.y - event.clientY);
    },
    onPointerUp: stop,
    onPointerCancel: stop,
    onLostPointerCapture: stop,
    onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
      const deltas: Record<string, [number, number]> = {
        ArrowLeft: [20, 0],
        ArrowRight: [-20, 0],
        ArrowUp: [0, 20],
        ArrowDown: [0, -20],
      };
      const delta = deltas[event.key];
      if (!delta || !panel.current) return;
      event.preventDefault();
      const bounds = panel.current.getBoundingClientRect();
      size(bounds.width + delta[0], bounds.height + delta[1]);
    },
  };
}
