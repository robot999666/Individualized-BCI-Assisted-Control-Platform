import Link from "next/link";
import NeuralCore from "./NeuralCore";
import styles from "./hero.module.css";
import type { CSSProperties } from "react";

const stages = [
  ["01", "EEG ACQUISITION", "脑电信号采集"],
  ["02", "INTENT DECODING", "个体化意图识别"],
  ["03", "EOG CONFIRMATION", "眼电协同确认"],
  ["04", "DEVICE RESPONSE", "辅助设备响应"],
];

export default function Hero() {
  return <section className={styles.hero} data-hero aria-labelledby="neural-hero-title">
    <div className={styles.stage}>
    <div className={styles.ambient} aria-hidden="true" />
    <div className={styles.perspectiveGrid} aria-hidden="true" />
    <div className={styles.pointerGlow} aria-hidden="true" />
    <div className={styles.content}>
      <div className={styles.copy}>
        <div className={styles.kicker}><span /> EEG · EOG · BCI <i /> 个体化辅助交互</div>
        <p className={styles.brandline}>个体化脑机辅助控制平台</p>
        <h1 id="neural-hero-title" aria-label="让每一次意图，连接自主行动。"><span aria-hidden="true">{Array.from("让每一次意图，").map((char, i) => <span className={styles.titleChar} key={i} style={{ "--delay": `${i * 35}ms` } as CSSProperties}>{char}</span>)}</span><br /><em aria-hidden="true">{Array.from("连接自主行动。").map((char, i) => <span className={styles.titleChar} key={i} style={{ "--delay": `${180 + i * 35}ms` } as CSSProperties}>{char}</span>)}</em></h1>
        <p className={styles.english} lang="en">FROM NEURAL INTENT TO REAL-WORLD ACTION</p>
        <p className={styles.chinese}>脑电识别意图，眼电确认行动。</p>
        <p className={styles.description}>面向 ALS 等重度运动障碍人群，融合个体化 EEG 校准与 EOG 眨眼确认，让神经意图经过安全判断，连接辅助设备的仿真响应。</p>
        <div className={styles.actions}>
          <Link href="/lab" prefetch={false} className={styles.primary} data-magnetic><span>体验控制平台<small>Experience Platform</small></span><span aria-hidden="true">↗</span></Link>
          <a href="#architecture" className={styles.secondary} data-magnetic><span>探索技术流程<small>Explore Technology</small></span><span aria-hidden="true">↓</span></a>
        </div>
        <div className={styles.note}><span aria-hidden="true">◈</span> 个体化适配 <i /> 双模态确认 <i /> 全流程追溯</div>
      </div>
      <NeuralCore />
    </div>
    <div className={styles.unfoldHeading}><span>HOW IT WORKS / 从意图到响应</span><h2>神经意图，成为行动的起点。</h2><p>采集 · 解码 · 确认 · 响应</p></div>
    <a href="#architecture" className={styles.scrollCue}><span>向下探索信号如何成为行动</span><i aria-hidden="true" /></a>
    <div className={styles.pipeline} aria-label="脑机辅助控制流程">
      <div className={styles.pipelineIntro}><span>INTENT → ACTION</span><p>从神经意图到行动</p></div>
      <ol>{stages.map(([number, title, subtitle], i) => <li key={number} style={{ "--index": i } as CSSProperties}><span className={styles.stageNumber}>{number}</span><div><b>{subtitle}</b><small lang="en">{title}</small></div><span className={styles.stageArrow} aria-hidden="true">→</span></li>)}</ol>
    </div>
    </div>
  </section>;
}
