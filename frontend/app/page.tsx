import Link from "next/link";

const capabilities = [
  ["01", "个体化冷启动", "为每位用户保存真实 EA 对齐参考。模型版本、通道布局与校准来源可追溯。", "REAL"],
  ["02", "EEG 流式回放", "真实 EEG 按 250 Hz 释放，窗口收齐后执行 EA + FBCSP + LDA CPU 推理。", "REAL"],
  ["03", "安全决策", "置信度、连续稳定性、确认、在线状态与超时联合检查；异常默认 STOP。", "REAL"],
  ["04", "EOG 辅助确认", "真实SVM眨眼模型处理EOG回放，双眨眼事件经安全层确认；当前未接入真实采集硬件，不宣称独立验证准确率。", "REAL"],
  ["05", "统一设备网关", "轮椅、护理床、紧急呼叫与智能家居模拟器。统一 Adapter 为未来硬件接入保留接口。", "SIMULATED"],
  ["06", "系统运行中心", "用户权限、实验、告警与审计。真实计算指标与设备模拟指标分开呈现。", "REAL"],
];
export default function Home() {
  return <div className="platform-home">
    <section className="hero-grid">
      <div><p className="eyebrow">ALS–BCI / PERSONALIZED ASSISTIVE CONTROL</p>
        <h1>让每一次意图，<br/><em>得到谨慎的回应。</em></h1>
        <p className="hero-subtitle">面向重度运动障碍人群的<br/>个体化脑机辅助控制软件平台</p>
        <p className="muted">面向 ALS 中晚期、重度脑卒中后遗症等人群的辅助交互研究。以真实 EEG 推理为起点，连接个体化校准、安全确认与虚拟设备响应。</p>
        <div className="actions"><Link className="primary" href="/lab">进入控制工作台 ↗</Link><a className="secondary" href="#architecture">查看系统流程 ↓</a></div>
        <p className="small muted">科研与比赛软件原型 · 非医疗器械 · 不提供诊断、治疗或临床有效性承诺</p>
      </div>
      <div className="hero-diagram"><span className="tag real">REAL EEG → SAFE CONTROL</span>
        <svg viewBox="0 0 500 260" role="img" aria-label="脑电信号经安全控制到设备模拟器的架构示意，非实时数据">
          <defs><linearGradient id="wave"><stop stopColor="#34d399"/><stop offset="1" stopColor="#38bdf8"/></linearGradient></defs>
          {[0,1,2].map(i=><path key={i} d={`M20 ${65+i*65} l40 0 10 -8 10 16 10 -38 10 60 10 -38 10 8 25 0 10 -15 10 30 10 -15 40 0`} fill="none" stroke="url(#wave)" strokeWidth="2" opacity={1-i*.2}/>)}
          <path d="M250 130 H285 M380 130 H430" stroke="#334155" strokeWidth="2"/>
          <rect x="285" y="85" width="95" height="90" rx="18" fill="#102b2d" stroke="#34d399"/>
          <text x="332" y="122" fill="#6ee7b7" textAnchor="middle" fontSize="13">SAFETY</text><text x="332" y="147" fill="#cbd5e1" textAnchor="middle" fontSize="12">STOP / GO</text>
          <circle cx="452" cy="130" r="22" fill="#162438" stroke="#38bdf8"/>
        </svg>
        <div className="diagram-bottom"><span>EA → FBCSP → LDA<br/><small>真实模型 / CPU 推理</small></span><span>EOG + Devices<br/><small>REAL MODEL / SIMULATED</small></span></div>
        <p className="small muted">架构示意；波形图案不是实验数据</p>
      </div>
    </section>
    <section id="architecture" className="flow-section"><p className="eyebrow">A COMPLETE, TRACEABLE LOOP</p><h2>从用户开始，到响应与审计结束</h2><div className="flow">用户 → 校准 Profile → EEG 实时推理 → 安全决策 → EOG 确认 → Device Gateway → 虚拟设备 → 告警与审计</div></section>
    <section id="capabilities" className="capability-grid">{capabilities.map(([n,title,desc,mode])=><article className="panel" key={n}><div className="card-top"><span className="number">{n}</span><span className={`tag ${mode==='REAL'?'real':'mock'}`}>{mode}</span></div><h3>{title}</h3><p className="muted">{desc}</p></article>)}</section>
    <section className="panel evidence"><h2>让数据边界与结果同样清晰</h2><p>校准使用 A01T，回放使用 A01E，逐 trial 来源和 checksum 可追溯。现有模型的完整训练会话清单无法确认，因此此 Demo 验证软件闭环，不报告独立泛化准确率。</p><p className="muted">生理数据尽可能在本地或端侧处理是设计目标；本部署上传的数据在服务器处理。EOG算法已接入；采集硬件、轮椅和其他物理设备尚未接入。当前 HTTP 演示站点不用于真实患者敏感数据。</p></section>
  </div>;
}
