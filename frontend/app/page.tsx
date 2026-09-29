import Hero from "@/components/site/home/Hero";

const capabilities = [
  ["01", "个体化 EEG 校准", "为每位使用者保存脑电对齐参考、模型版本与通道布局，形成可复用、可追溯的个体化档案。", "个体适配"],
  ["02", "脑电意图识别", "按 250 Hz 回放脑电信号，通过 EA、FBCSP 与 LDA 输出左转、右转、直行和停止四类意图。", "四类意图"],
  ["03", "脑电与眼电协同确认", "EEG（脑电）识别运动意图，EOG（眼电）眨眼模型提供确认信号，安全控制器检查稳定性和设备状态。", "双模态"],
  ["04", "闭环安全控制", "从意图预测、连续稳定判断、眼电确认到设备回执和告警处理，保留完整的运行记录。", "闭环运行"],
  ["05", "多类辅助设备演示", "提供轮椅、护理床、紧急呼叫和智能家居场景，统一展示指令执行与异常响应。", "设备模拟"],
  ["06", "结果和告警可追溯", "工作台展示信号、分类概率与安全决策；运行中心汇总告警处理人和响应耗时。", "运行统计"],
];
export default function Home() {
  return <><Hero /><div className="platform-home">
    <section id="architecture" className="flow-section"><p className="eyebrow">四步完成演示</p><h2>从个体化校准，到设备响应结果</h2><div className="flow">① 选择演示用户 → ② 生成脑电校准档案 → ③ 创建 EEG（脑电）实验 → ④ 查看脑电预测、眼电确认、设备响应与告警处理</div></section>
    <section id="capabilities" className="capability-grid">{capabilities.map(([n,title,desc,mode])=><article className="panel" key={n}><div className="card-top"><span className="number">{n}</span><span className="tag real">{mode}</span></div><h3>{title}</h3><p className="muted">{desc}</p></article>)}</section>
    <section className="panel evidence"><h2>在一个工作台掌握完整控制闭环</h2><p>融合 EEG 意图识别与 EOG 眨眼确认，从个体化校准到辅助设备响应贯通全流程。工作台同步展示脑电波形、四类意图概率、各阶段计算耗时、安全决策和设备仿真回执；运行中心集中呈现命令、告警与处理记录。</p><p className="muted">覆盖轮椅、护理床、紧急呼叫和智能家居四类仿真场景，支持多来源回放、异常场景验证与运行过程追溯。</p></section>
  </div></>;
}
