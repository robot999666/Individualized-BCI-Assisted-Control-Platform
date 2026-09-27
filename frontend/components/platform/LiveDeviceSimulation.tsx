"use client";

import dynamic from "next/dynamic";
import { Component, useState, type ReactNode } from "react";
import type { Device, Tick } from "@/lib/platform";

const Scene=dynamic(()=>import("./LiveDeviceScene"),{ssr:false,loading:()=> <p className="live-scene-loading">正在加载3D模拟设备…</p>});
const names:Record<string,string>={wheelchair:"电动轮椅",care_bed:"护理床",emergency_call:"紧急呼叫",smart_home:"智能家居"};
const states:Record<string,string>={ONLINE:"在线",OFFLINE:"离线",ERROR:"故障",BUSY:"处理中"};
const actions:Record<string,string>={LEFT:"左转",RIGHT:"右转",FORWARD:"直行",STOP:"停止"};
class SceneBoundary extends Component<{children:ReactNode},{failed:boolean}> {
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  render(){return this.state.failed?<div className="live-scene-loading"><p>3D渲染暂不可用，下方设备卡片仍可使用。</p><button className="secondary" onClick={()=>this.setState({failed:false})}>重新加载3D</button></div>:this.props.children;}
}
export function LiveDeviceSimulation({tick,connected,busy,onSelect,onEmergency,onControl}:{tick:Tick|null;connected:boolean;busy:boolean;onSelect:(device:Device)=>void;onEmergency:()=>void;onControl:(action:"play"|"pause"|"reset")=>void}) {
  const [viewReset,setViewReset]=useState(0);
  const current=tick?.devices.find(d=>d.id===tick.selected_device);
  const active=Boolean(tick&&connected);
  return <section className="panel live-device-panel" aria-label="3D模拟设备演示">
    <div className="card-top"><div><p className="eyebrow">实时模拟 · 设备选择与执行反馈</p><h2>3D 模拟接入设备</h2></div><span className="tag mock">软件仿真 · 非真实硬件</span></div>
    <p className="muted">先选择目标设备，再开始回放。EEG 意图 → EOG 双眨眼确认 → 安全放行 → 设备回执，画面跟随服务器实际执行结果。</p>
    <div className="actions live-device-select">{Object.entries(names).map(([kind,name])=>{const d=tick?.devices.find(row=>row.kind===kind);return <button key={kind} className={current?.kind===kind?"primary":"secondary"} disabled={!d||!active||busy||tick?.emergency_latched} aria-pressed={current?.kind===kind} onClick={()=>d&&onSelect(d)}>{name}{d?` · ${states[d.state]||d.state}`:""}</button>})}<button className="danger" disabled={!tick} onClick={onEmergency}>人工急停 · 全部设备</button></div>
    <div className="actions"><button className="primary" disabled={!active||busy||tick?.running||tick?.emergency_latched||tick?.status==="COMPLETE"} onClick={()=>onControl("play")}>▶ 开始 / 继续回放</button><button className="secondary" disabled={!tick?.running||busy} onClick={()=>onControl("pause")}>Ⅱ 暂停回放</button><button className="secondary" disabled={!tick||busy} onClick={()=>onControl("reset")}>↺ 重置回放与设备</button><button className="text-button" onClick={()=>setViewReset(value=>value+1)}>↺ 重置视角</button></div>
    <div className="live-scene"><SceneBoundary key={tick?.id||"idle"}><Scene key={viewReset} tick={tick}/></SceneBoundary><span className="live-scene-overlay">{!tick?"请完成校准并创建会话":!connected?"连接恢复中 · 请核对设备状态":tick.emergency_latched?"人工急停已锁定 · 重置后可继续":tick.status==="COMPLETE"?"回放完成 · 重置后可重新演示":tick.running?"真实信号回放中":"已暂停 · 设备保持当前位置"}</span></div>
    <div className="live-device-evidence"><div><span>当前目标</span><b>{current?names[current.kind]:"待创建会话"}</b><small>{current?`${states[current.state]||current.state} · 当前${actions[current.data.action]||current.data.action}`:"四种模拟设备随会话创建"}</small></div><div><span>最近成功回执</span><b>{current?.data.ack_action?`${actions[current.data.ack_action]||current.data.ack_action} · ACK`:"尚无动作回执"}</b><small>{current?.data.ack_command_id?`${current.data.ack_command_id.slice(0,8)} · ${current.data.ack_latency_ms?.toFixed(2)} ms`:"仅安全放行并执行成功后更新"}</small></div><div><span>操作与观察</span><b>拖动旋转 · 滚轮缩放</b><small>青色环标记当前目标；故障场景在下方卡片设置。重置恢复姿态。</small></div></div>
    <p className="small muted">轮椅每次转向30°、直行0.8演示单位；护理床每次调节5°。STOP保留当前位置、床角度和灯光状态。完整命令原因与耗时见执行记录。</p>
  </section>;
}
