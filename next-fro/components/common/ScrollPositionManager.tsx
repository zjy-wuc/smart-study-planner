"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

/** Remember the window position separately for each workspace page. */
export function ScrollPositionManager() {
  const pathname = usePathname();

  useEffect(() => {
    const key = `workspace-scroll:${pathname}`;
    let saved: string | null = null;
    try {
      saved = sessionStorage.getItem(key);
    } catch {
      // Storage can be disabled in the browser.
    }
    const target = saved === null ? null : Number(saved);
    let restoring = target !== null && Number.isFinite(target) && target > 0;
    let frame = 0;
    let observer: ResizeObserver | undefined;

    const save = () => {
      if (restoring) return;
      try {
        sessionStorage.setItem(key, String(window.scrollY));
      } catch {
        // Keep navigation usable even when storage is unavailable.
      }
    };

    const stopRestoring = () => {
      restoring = false;
      observer?.disconnect();
    };

    const restore = () => {
      if (!restoring || target === null) return;
      const maxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      window.scrollTo({ top: Math.min(target, maxScroll), behavior: "instant" });
      if (maxScroll >= target && Math.abs(window.scrollY - target) < 2) {
        stopRestoring();
      }
    };

    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(save);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      const element = event.target as HTMLElement | null;
      if (element?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(element?.tagName ?? "")) return;
      if (["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End", " "].includes(event.key)) {
        stopRestoring();
      }
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("wheel", stopRestoring, { passive: true });
    window.addEventListener("touchstart", stopRestoring, { passive: true });
    window.addEventListener("pointerdown", stopRestoring, { passive: true });
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("pagehide", save);

    if (restoring) {
      observer = new ResizeObserver(restore);
      observer.observe(document.body);
      frame = requestAnimationFrame(restore);
    }
    const timeout = window.setTimeout(stopRestoring, 8000);

    return () => {
      window.clearTimeout(timeout);
      cancelAnimationFrame(frame);
      save();
      observer?.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("wheel", stopRestoring);
      window.removeEventListener("touchstart", stopRestoring);
      window.removeEventListener("pointerdown", stopRestoring);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("pagehide", save);
    };
  }, [pathname]);

  return null;
}
