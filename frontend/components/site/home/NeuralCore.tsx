"use client";
import { useEffect, useRef, useState } from "react";
import NeuralFallback from "./NeuralFallback";
import type { NeuralRuntime } from "./neuralScene";
import styles from "./hero.module.css";
const regions = [
  { id: "eeg", title: "脑电采集", name: "EEG Signal", detail: "运动想象脑电信号", className: styles.eeg },
  { id: "intent", title: "意图解码", name: "Intent Decoder", detail: "个体化校准 · 四类意图", className: styles.intent },
  { id: "eog", title: "眼电确认", name: "EOG Confirmation", detail: "眨眼确认 · 双模态协同", className: styles.eog },
  { id: "device", title: "设备控制", name: "Device Control", detail: "安全判断 · 仿真响应", className: styles.device },
];
export default function NeuralCore() {
  const host = useRef<HTMLDivElement>(null), runtime = useRef<NeuralRuntime | null>(null);
  const [status, setStatus] = useState("loading"), [paused, setPaused] = useState(false), [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let disposed = false;
    let cancelStart = () => {};
    const start = async () => {
      try {
        const { createNeuralScene } = await import("./neuralScene");
        if (disposed) return;
        runtime.current = await createNeuralScene(element, () => setStatus("fallback"));
        if (disposed) { runtime.current.dispose(); runtime.current = null; return; }
        setStatus("ready");
      } catch { if (!disposed) setStatus("fallback"); }
    };
    if ("requestIdleCallback" in window) {
      const id = window.requestIdleCallback(() => { void start(); }, { timeout: 1400 });
      cancelStart = () => window.cancelIdleCallback(id);
    } else { const id = setTimeout(() => { void start(); }, 160); cancelStart = () => clearTimeout(id); }
    return () => { disposed = true; cancelStart(); runtime.current?.dispose(); runtime.current = null; };
  }, []);
  useEffect(() => { runtime.current?.setPaused(paused); }, [paused, status]);
  useEffect(() => { runtime.current?.setFocus(selected); }, [selected, status]);
  return <div className={styles.visual} data-neural-status={status}>
    <div className={styles.visualHeading}><span><i /> NEURAL CORE / 神经核心</span><small>意图与行动，在此连接</small></div>
    <div className={styles.sceneWrap}>
      <NeuralFallback />
      <div ref={host} className={`${styles.canvasHost} ${status === "ready" ? styles.ready : ""}`} aria-hidden="true" />
      <div className={styles.coreCaption}><span>NEURAL INTENT</span><small>个体化神经解码</small></div>
      {regions.map(region => <button key={region.id} type="button" className={`${styles.region} ${region.className} ${selected === region.id ? styles.selected : ""}`} aria-pressed={selected === region.id}
        onPointerEnter={() => setSelected(region.id)} onPointerLeave={() => setSelected(null)} onFocus={() => setSelected(region.id)} onBlur={() => setSelected(null)} onClick={() => setSelected(region.id)}>
        <span className={styles.regionDot} /><b>{region.title}<em>{region.name}</em></b><small>{region.detail}</small>
      </button>)}
    </div>
    <div className={styles.visualFooter}><span>{status === "fallback" ? "静态神经结构视图" : "交互式神经结构"}<i />流程概念可视化</span>
      {status === "ready" && <button type="button" className={styles.motionButton} onClick={() => setPaused(!paused)} aria-pressed={paused} aria-label={paused ? "继续神经核心动画" : "暂停神经核心动画"}>{paused ? "▷" : "Ⅱ"}<span>{paused ? "继续" : "暂停"}</span></button>}
    </div><p className={styles.visualHint}>悬停或轻触节点，探索信号路径</p>
  </div>;
}
