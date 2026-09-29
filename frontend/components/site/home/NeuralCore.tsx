"use client";
import { Component, useCallback, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import dynamic from "next/dynamic";
import { useHeroInputRef } from "./HomeExperience";
import NeuralFallback from "./NeuralFallback";

import styles from "./hero.module.css";
const regions = [
  { id: "eeg", title: "脑电采集", name: "EEG Signal", detail: "运动想象脑电信号", className: styles.eeg },
  { id: "intent", title: "意图解码", name: "Intent Decoder", detail: "个体化校准 · 四类意图", className: styles.intent },
  { id: "eog", title: "眼电确认", name: "EOG Confirmation", detail: "眨眼确认 · 双模态协同", className: styles.eog },
  { id: "device", title: "设备控制", name: "Device Control", detail: "安全判断 · 仿真响应", className: styles.device },
];
const NeuralCanvas = dynamic(() => import("./NeuralCanvas"), { ssr: false });
function subscribeMotion(callback:()=>void){const m=matchMedia("(prefers-reduced-motion: reduce)");m.addEventListener("change",callback);return()=>m.removeEventListener("change",callback);}
class SceneBoundary extends Component<{children:ReactNode;onFailure:(reason?:string)=>void},{failed:boolean}>{
  state={failed:false};static getDerivedStateFromError(){return{failed:true};}
  componentDidCatch(error:Error){this.props.onFailure(error.message);}
  render(){return this.state.failed?null:this.props.children;}
}
export default function NeuralCore() {
  const host=useRef<HTMLDivElement>(null), inputRef=useHeroInputRef();
  const [status,setStatus]=useState("loading"),[enabled,setEnabled]=useState(false),[visible,setVisible]=useState(true);
  const [paused,setPaused]=useState(false),[selected,setSelected]=useState<string|null>(null);
  const reduced=useSyncExternalStore(subscribeMotion,()=>matchMedia("(prefers-reduced-motion: reduce)").matches,()=>false);
  const onReady=useCallback(()=>setStatus("ready"),[]),onFailure=useCallback((reason="WebGL unavailable")=>{if(host.current)host.current.dataset.fallbackReason=reason;setStatus("fallback");},[]);
  useEffect(()=>{
    const element=host.current!, input=inputRef.current;input.surface=element;
    const idle=setTimeout(()=>{
      try{
        const probe=document.createElement("canvas"),context=probe.getContext("webgl2");
        if(!context){onFailure("WebGL 2 unavailable");return;}
        context.getExtension("WEBGL_lose_context")?.loseContext();
        setEnabled(true);
      }catch{onFailure("WebGL initialization unavailable");}
    },120);
    let intersecting=true;
    const update=()=>setVisible(intersecting&&!document.hidden);
    const observer=new IntersectionObserver(entries=>{intersecting=entries[0].isIntersecting;update();},{threshold:.01});observer.observe(element);
    document.addEventListener("visibilitychange",update);
    return()=>{clearTimeout(idle);observer.disconnect();document.removeEventListener("visibilitychange",update);input.surface=null;};
  },[inputRef,onFailure]);
  useEffect(()=>{inputRef.current.paused=paused;inputRef.current.invalidate?.();},[paused,inputRef]);
  return <div className={styles.visual} data-neural-status={status}>
    <div className={styles.visualHeading}><span><i /> NEURAL CORE / 神经核心</span><small>意图与行动，在此连接</small></div>
    <div className={styles.sceneWrap}>
      <NeuralFallback />
      <div ref={host} className={`${styles.canvasHost} ${status === "ready" ? styles.ready : ""}`} aria-hidden="true">{enabled && status !== "fallback" && <SceneBoundary onFailure={onFailure}><NeuralCanvas inputRef={inputRef} reduced={reduced} paused={paused} visible={visible} focus={selected} onReady={onReady} onFailure={onFailure}/></SceneBoundary>}</div>
      <div className={styles.coreCaption}><span>NEURAL INTENT</span><small>个体化神经解码</small></div>
      {regions.map(region => <button key={region.id} type="button" className={`${styles.region} ${region.className} ${selected === region.id ? styles.selected : ""}`} data-node={region.id} aria-pressed={selected === region.id}
        onPointerEnter={() => setSelected(region.id)} onPointerLeave={() => setSelected(null)} onFocus={() => setSelected(region.id)} onBlur={() => setSelected(null)} onClick={() => setSelected(region.id)}>
        <span className={styles.regionDot} /><b>{region.title}<em>{region.name}</em></b><small>{region.detail}</small>
      </button>)}
    </div>
    <div className={styles.visualFooter}><span>{status === "fallback" ? "静态神经结构视图" : "交互式神经核心"}<i />流程概念可视化</span>
      {status === "ready" && <button type="button" className={styles.motionButton} onClick={() => setPaused(!paused)} aria-pressed={paused} aria-label={paused ? "继续神经核心动画" : "暂停神经核心动画"}>{paused ? "▷" : "Ⅱ"}<span>{paused ? "继续" : "暂停"}</span></button>}
    </div><p className={styles.visualHint}>移动鼠标激活神经场 · 滚动展开信号链路</p>
  </div>;
}
