import Link from "next/link";
import NeuralCore from "./NeuralCore";
import styles from "./hero.module.css";

const stages = [
  ["01", "EEG ACQUISITION", "脑电信号采集"],
  ["02", "INTENT DECODING", "个体化意图识别"],
  ["03", "EOG CONFIRMATION", "眼电协同确认"],
  ["04", "DEVICE RESPONSE", "辅助设备响应"],
];

export default function Hero() {
  return <section className={styles.hero} aria-labelledby="neural-hero-title">
    <div className={styles.ambient} aria-hidden="true" />
    <div className={styles.content}>
      <div className={styles.copy}>
        <div className={styles.kicker}><span /> EEG · EOG · BCI <i /> 个体化辅助交互</div>
        <p className={styles.brandline}>个体化脑机辅助控制平台</p>
        <h1 id="neural-hero-title">让每一次意图，<br /><em>连接自主行动。</em></h1>
        <p className={styles.english} lang="en">FROM NEURAL INTENT TO REAL-WORLD ACTION</p>
        <p className={styles.chinese}>脑电识别意图，眼电确认行动。</p>
        <p className={styles.description}>面向 ALS 等重度运动障碍人群，融合个体化 EEG 校准与 EOG 眨眼确认，让神经意图经过安全判断，连接辅助设备的仿真响应。</p>
        <div className={styles.actions}>
          <Link href="/lab" prefetch={false} className={styles.primary}><span>体验控制平台<small>Experience Platform</small></span><span aria-hidden="true">↗</span></Link>
          <a href="#architecture" className={styles.secondary}><span>探索技术流程<small>Explore Technology</small></span><span aria-hidden="true">↓</span></a>
        </div>
        <div className={styles.note}><span aria-hidden="true">◈</span> 个体化适配 <i /> 双模态确认 <i /> 全流程追溯</div>
      </div>
      <NeuralCore />
    </div>
    <div className={styles.pipeline} aria-label="脑机辅助控制流程">
      <div className={styles.pipelineIntro}><span>INTENT → ACTION</span><p>从神经意图到行动</p></div>
      <ol>{stages.map(([number, title, subtitle]) => <li key={number}><span className={styles.stageNumber}>{number}</span><div><b>{subtitle}</b><small lang="en">{title}</small></div><span className={styles.stageArrow} aria-hidden="true">→</span></li>)}</ol>
    </div>
  </section>;
}
