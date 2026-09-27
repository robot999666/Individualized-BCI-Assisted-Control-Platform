import Link from "next/link";

const capabilities = [
  ["01", "个体化 EEG 校准", "为每位使用者保存脑电对齐参考、模型版本与通道布局，形成可追溯的个体化档案。", "真实模型"],
  ["02", "脑电意图识别", "实时释放 250 赫兹 EEG（脑电）信号，窗口完整后运行 EA、FBCSP 与 LDA 分类流程。", "真实模型"],
  ["03", "脑电与眼电协同确认", "EEG（脑电）识别运动意图，EOG（眼电）眨眼模型提供确认信号，安全控制器检查稳定性和设备状态。", "双模态"],
  ["04", "闭环安全控制", "从意图预测、连续稳定判断、眼电确认到设备回执和告警处理，保留完整的运行记录。", "闭环运行"],
  ["05", "多类辅助设备演示", "提供轮椅、护理床、紧急呼叫和智能家居场景，统一展示指令执行与异常响应。", "设备模拟"],
  ["06", "结果和告警可追溯", "工作台展示信号、分类概率与安全决策；运行中心汇总告警处理人和响应耗时。", "运行统计"],
];
export default function Home() {
  return <div className="platform-home">
    <section className="hero-grid">
      <div><p className="eyebrow">ALS 脑机辅助控制平台</p>
        <h1>让每一次意图，<br/><em>得到谨慎的回应。</em></h1>
        <p className="hero-subtitle">面向重度运动障碍人群的<br/>个体化脑机辅助控制软件平台</p>
        <p className="muted">面向 ALS 中晚期、重度脑卒中后遗症等重度运动障碍人群。融合 EEG（脑电）意图识别与 EOG（眼电）眨眼确认，串联个体化校准、安全控制和设备响应。</p>
        <div className="actions"><Link className="primary" href="/lab">进入控制工作台 ↗</Link><a className="secondary" href="#architecture">查看系统流程 ↓</a></div>
        <p className="small muted">科研与比赛软件原型 · 非医疗器械 · 不提供诊断、治疗或临床有效性承诺</p>
      </div>
      <div className="hero-diagram"><span className="tag real">脑电识别 → 眼电确认 → 安全响应</span>
        <svg viewBox="0 0 500 260" role="img" aria-label="脑电信号经安全控制到设备模拟器的架构示意，非实时数据">
          <defs><linearGradient id="wave"><stop stopColor="#34d399"/><stop offset="1" stopColor="#38bdf8"/></linearGradient></defs>
          {[0,1,2].map(i=><path key={i} d={`M20 ${65+i*65} l40 0 10 -8 10 16 10 -38 10 60 10 -38 10 8 25 0 10 -15 10 30 10 -15 40 0`} fill="none" stroke="url(#wave)" strokeWidth="2" opacity={1-i*.2}/>)}
          <path d="M250 130 H285 M380 130 H430" stroke="#334155" strokeWidth="2"/>
          <rect x="285" y="85" width="95" height="90" rx="18" fill="#102b2d" stroke="#34d399"/>
          <text x="332" y="122" fill="#6ee7b7" textAnchor="middle" fontSize="13">安全判断</text><text x="332" y="147" fill="#cbd5e1" textAnchor="middle" fontSize="12">停止 / 执行</text>
          <circle cx="452" cy="130" r="22" fill="#162438" stroke="#38bdf8"/>
        </svg>
        <div className="diagram-bottom"><span>EEG（脑电）<br/><small>个体化校准与四分类识别</small></span><span>EOG（眼电）+ 设备<br/><small>眨眼模型与设备闭环</small></span></div>
        <p className="small muted">架构示意；波形图案不是实验数据</p>
      </div>
    </section>
    <section id="architecture" className="flow-section"><p className="eyebrow">四步完成演示</p><h2>从个体化校准，到设备响应结果</h2><div className="flow">① 选择演示用户 → ② 生成脑电校准档案 → ③ 创建 EEG（脑电）实验 → ④ 查看脑电预测、眼电确认、设备响应与告警处理</div></section>
    <section id="capabilities" className="capability-grid">{capabilities.map(([n,title,desc,mode])=><article className="panel" key={n}><div className="card-top"><span className="number">{n}</span><span className="tag real">{mode}</span></div><h3>{title}</h3><p className="muted">{desc}</p></article>)}</section>
    <section className="panel evidence"><h2>在一个工作台查看完整闭环</h2><p>项目已接入实际 EEG 分类算法和 EOG（眼电）眨眼模型。工作台展示连续脑电波形、四类意图概率、分阶段计算耗时、安全控制决策和虚拟设备回执；运行中心展示告警响应时间与审计记录。</p><p className="muted">本平台用于辅助交互研究与比赛演示。设备响应使用模拟器，适合逐步体验和评估软件闭环。</p></section>
  </div>;
}
