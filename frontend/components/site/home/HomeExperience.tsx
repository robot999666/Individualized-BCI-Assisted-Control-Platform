"use client";

import { createContext, useContext, useEffect, useRef, type ReactNode, type RefObject } from "react";
import styles from "./hero.module.css";

export interface HeroInput {
  x: number; y: number; active: boolean; scroll: number; paused: boolean;
  hero: HTMLElement | null; surface: HTMLElement | null; invalidate: (() => void) | null;
}
const InputContext = createContext<RefObject<HeroInput> | null>(null);
export function useHeroInputRef() { return useContext(InputContext)!; }

/** DOM motion only; all Three.js updates are handled by useFrame. */
export default function HomeExperience({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HeroInput>({ x: 0, y: 0, active: false, scroll: 0, paused: false, hero: null, surface: null, invalidate: null });
  useEffect(() => {
    const element = root.current!;
    const hero = element.querySelector<HTMLElement>("[data-hero]")!;
    const visual = hero.querySelector<HTMLElement>("[data-neural-status]");
    const state = input.current;
    state.hero = hero;
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const coarse = matchMedia("(pointer: coarse)");
    const surfaces = Array.from(element.querySelectorAll<HTMLElement>("[data-magnetic], [data-tilt]"));
    const motion = surfaces.map(node => ({ node, x: 0, y: 0, tx: 0, ty: 0, gx: 50, gy: 50, tgx: 50, tgy: 50 }));
    let frame = 0, previous = 0, mx = 50, my = 45, activity = 0, progress = 0;
    let inView = true, busyUntil = 0;
    const observers = new IntersectionObserver(entries => {
      inView = entries[0].isIntersecting;
      if (inView) wake();
    });
    observers.observe(element);
    function frameStep(now: number) {
      frame = 0;
      if (document.hidden || !inView) return;
      const delta = previous ? Math.min((now - previous) / 1000, .045) : .016;
      previous = now;
      const rect = hero.getBoundingClientRect();
      const scroll = media.matches || innerWidth <= 700 || visual?.dataset.neuralStatus === "fallback" ? 0 : Math.min(1, Math.max(0, (88 - rect.top) / Math.max(1, rect.height - innerHeight + 88)));
      const factor = 1 - Math.exp(-delta * 11);
      progress += (scroll - progress) * factor;
      state.scroll = progress;
      hero.style.setProperty("--scroll", progress.toFixed(4));
      hero.dataset.scrollProgress = progress.toFixed(3);
      hero.dataset.flowMode = String(progress > .4);
      const interactive = !media.matches && !coarse.matches && !state.paused;
      const tx = interactive && state.active ? (state.x - rect.left) / rect.width * 100 : 50;
      const ty = interactive && state.active ? (state.y - Math.max(88, rect.top)) / Math.max(1, innerHeight - 88) * 100 : 45;
      mx += (tx - mx) * factor; my += (ty - my) * factor;
      activity += ((interactive && state.active ? 1 : 0) - activity) * factor;
      hero.style.setProperty("--pointer-x", `${mx.toFixed(2)}%`);
      hero.style.setProperty("--pointer-y", `${my.toFixed(2)}%`);
      hero.style.setProperty("--field-x", `${((mx - 50) * .26).toFixed(2)}px`);
      hero.style.setProperty("--field-y", `${((my - 45) * .18).toFixed(2)}px`);
      hero.style.setProperty("--activity", activity.toFixed(3));
      for (const m of motion) {
        m.x += (m.tx - m.x) * factor; m.y += (m.ty - m.y) * factor;
        m.gx += (m.tgx - m.gx) * factor; m.gy += (m.tgy - m.gy) * factor;
        m.node.style.setProperty("--motion-x", `${m.x.toFixed(2)}px`);
        m.node.style.setProperty("--motion-y", `${m.y.toFixed(2)}px`);
        m.node.style.setProperty("--tilt-x", `${(-m.y * .55).toFixed(2)}deg`);
        m.node.style.setProperty("--tilt-y", `${(m.x * .55).toFixed(2)}deg`);
        m.node.style.setProperty("--glow-x", `${m.gx.toFixed(2)}%`);
        m.node.style.setProperty("--glow-y", `${m.gy.toFixed(2)}%`);
      }
      if (!media.matches) state.invalidate?.();
      if (now < busyUntil || Math.abs(scroll - progress) > .0005 || Math.abs(activity - Number(state.active && interactive)) > .001) frame = requestAnimationFrame(frameStep);
    }
    function wake() { busyUntil = performance.now() + 850; if (!frame && !document.hidden) frame = requestAnimationFrame(frameStep); }
    function pointer(event: PointerEvent) {
      if (event.pointerType === "touch" || media.matches || coarse.matches) return;
      state.x = event.clientX; state.y = event.clientY; state.active = true;
      for (const m of motion) {
        const rect = m.node.getBoundingClientRect();
        const x = event.clientX - rect.left - rect.width / 2, y = event.clientY - rect.top - rect.height / 2;
        const near = Math.abs(x) < rect.width / 2 + 28 && Math.abs(y) < rect.height / 2 + 28;
        const amount = m.node.hasAttribute("data-magnetic") ? .13 : .025;
        m.tx = near && !state.paused ? Math.max(-10, Math.min(10, x * amount)) : 0;
        m.ty = near && !state.paused ? Math.max(-7, Math.min(7, y * amount)) : 0;
        m.tgx = near ? Math.max(0, Math.min(100, (x / rect.width + .5) * 100)) : 50;
        m.tgy = near ? Math.max(0, Math.min(100, (y / rect.height + .5) * 100)) : 50;
      }
      wake();
    }
    function leave() { state.active = false; motion.forEach(m => { m.tx = 0; m.ty = 0; }); wake(); }
    function spring(event: PointerEvent) {
      if (media.matches || state.paused) return;
      const target = (event.target as HTMLElement).closest<HTMLElement>("[data-magnetic]");
      target?.animate([{ scale: ".96" }, { scale: "1.025", offset: .55 }, { scale: "1" }], { duration: 380, easing: "cubic-bezier(.2,.8,.3,1)" });
    }
    element.addEventListener("pointermove", pointer, { passive: true });
    element.addEventListener("pointerleave", leave);
    element.addEventListener("pointerup", spring);
    window.addEventListener("scroll", wake, { passive: true });
    window.addEventListener("resize", wake, { passive: true });
    document.addEventListener("visibilitychange", wake);
    media.addEventListener("change", leave);
    wake();
    return () => {
      cancelAnimationFrame(frame); observers.disconnect();
      element.removeEventListener("pointermove", pointer); element.removeEventListener("pointerleave", leave); element.removeEventListener("pointerup", spring);
      window.removeEventListener("scroll", wake); window.removeEventListener("resize", wake); document.removeEventListener("visibilitychange", wake); media.removeEventListener("change", leave);
      state.hero = null; state.invalidate = null;
    };
  }, []);
  return <InputContext.Provider value={input}><div ref={root} className={styles.experience}>{children}</div></InputContext.Provider>;
}
