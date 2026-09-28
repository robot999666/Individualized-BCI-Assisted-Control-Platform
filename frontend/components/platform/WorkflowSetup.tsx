"use client";
import { useState } from "react";
import { compatible, provenance, sourceLabel, type DataSource, type Experiment, type Profile, type Subject } from "@/lib/platform";

type Props = {
  guest:boolean;busy:boolean;session:string;subjects:Subject[];profiles:Profile[];experiments:Experiment[];sources:DataSource[];
  subject:string;profile:string;experiment:string;source:string;uploadSource:string;speed:number;eogPrefiltered:boolean;
  selectSubject:(id:string)=>void;selectProfile:(id:string)=>void;selectExperiment:(id:string)=>void;
  selectSource:(id:string)=>void;setUploadSource:(value:string)=>void;setSpeed:(value:number)=>void;setEogPrefiltered:(value:boolean)=>void;
  createSubject:(name:string,isDemo:boolean)=>void;calibrate:()=>void;createExperiment:()=>void;makeSession:()=>void;
  upload:(file:File|undefined,calibration:boolean)=>void;uploadEog:(file:File|undefined)=>void;revoke:()=>void;evaluate:()=>void;
};

function Upload({label,disabled,onFile}:{label:string;disabled:boolean;onFile:(file:File|undefined)=>void}){
  return <label>{label}<input type="file" accept=".npz" disabled={disabled} onChange={e=>{const file=e.target.files?.[0];e.target.value="";onFile(file)}}/></label>;
}

export function WorkflowSetup(p:Props){
  const [name,setName]=useState("");const [isDemo,setIsDemo]=useState(true);
  const subject=p.subjects.find(s=>s.id===p.subject);
  const profile=p.profiles.find(s=>s.id===p.profile);
  const experiment=p.experiments.find(s=>s.id===p.experiment);
  const source=p.sources.find(s=>s.id===p.source);
  const locked=p.busy||!!p.session;
  const readyProfiles=p.profiles.filter(row=>row.user_id===p.subject&&row.status==="READY"&&(!subject?.is_demo||provenance(row.source,row.user_id,row.channel_layout.length)===p.source));
  const readyExperiments=p.experiments.filter(row=>row.subject_id===p.subject&&profile&&compatible(profile,row));
  const step=p.session?4:profile&&experiment?3:profile?2:subject?1:0;
  return <>
    <ol className="workflow-steps" aria-label="操作顺序">{["选择用户和来源","完成个体化校准","准备同源数据","开始实时模拟"].map((title,i)=><li key={title} className={step>i?"done":step===i?"current":""} aria-current={step===i?"step":undefined}><b>{step>i?"✓":i+1}</b>{title}</li>)}</ol>
    <p className="notice small" role="status">{p.session?"会话已锁定用户、来源与校准档案。更换数据请先关闭会话。":!subject?"先选择已有用户，或创建一位演示 / 私有研究用户。":!profile?"选择来源并完成校准，或复用该来源的已保存档案。":!experiment?"校准已就绪。准备同一用户、同一来源、同一通道的独立回放数据。":"数据已就绪。创建会话后点击“开始”，观察 EEG → EOG → 安全判断 → 设备回执。"}</p>
    <div className="setup-grid">
      <section className="panel"><p className="eyebrow">第1步 · 用户与来源</p><h2>选择使用对象</h2>
        <label>用户<select value={p.subject} disabled={locked} onChange={e=>p.selectSubject(e.target.value)}><option value="">请选择用户</option>{p.subjects.map(s=><option key={s.id} value={s.id}>{s.name} · {s.is_demo?"内置演示":"私有研究"}</option>)}</select></label>
        <form onSubmit={e=>{e.preventDefault();if(name.trim())p.createSubject(name.trim(),p.guest||isDemo)}}>
          <label>新用户名称<input value={name} disabled={locked} onChange={e=>setName(e.target.value)} placeholder="参与者名称或匿名编号" required maxLength={80}/></label>
          {!p.guest&&<label>用户类型<select value={String(isDemo)} disabled={locked} onChange={e=>setIsDemo(e.target.value==="true")}><option value="true">内置演示数据</option><option value="false">私有研究 · 上传本人的数据</option></select></label>}
          <button className="secondary" disabled={locked||!name.trim()}>＋ 创建并选择用户</button>
        </form>
        {subject?.is_demo&&<><label>内置数据来源<select value={p.source} disabled={locked} onChange={e=>p.selectSource(e.target.value)}>{p.sources.map(s=><option key={s.id} value={s.id} disabled={!s.available}>{s.name}{!s.available?" · 未准备":""}</option>)}</select></label><p className="small muted">{source?.calibration_trials||"—"} 条 T 会话校准 → {source?.evaluation_trials||"—"} 条 E 会话回放 · {source?.channels||"—"} 通道。后续实验自动沿用此来源。</p></>}
        {subject&&!subject.is_demo&&<><label>采集来源标识<input value={p.uploadSource} maxLength={80} disabled={locked||!!profile} onChange={e=>p.setUploadSource(e.target.value)} placeholder="例如：participant-01-device-a"/></label><p className="small muted">使用同一参与者、同一采集来源的校准与回放数据，统一保存来源标识与通道布局。</p></>}
        {p.guest&&<p className="small muted">访客可体验全部内置来源。上传私有数据需研究人员或管理员账号。</p>}
      </section>
      <section className="panel" aria-label="个体化校准设置"><p className="eyebrow">第2步 · 个体化校准</p><h2>{profile?"校准档案已就绪":"适配当前用户"}</h2>
        <p className="small muted">无标签数据：计算并保存 EA 对齐参考。含类别标签且每类≥10条：训练个人 CSP / LDA 分类器。回放复用已保存结果。</p>
        {subject?.is_demo&&<button className="primary" disabled={locked||!source?.available} onClick={p.calibrate}>开始个体化校准</button>}
        {subject&&!subject.is_demo&&<Upload label="上传校准 EEG · NPZ" disabled={locked||!p.uploadSource.trim()} onFile={f=>p.upload(f,true)}/>}
        <label>已保存校准档案<select value={p.profile} disabled={locked||!subject} onChange={e=>p.selectProfile(e.target.value)}><option value="">请选择校准档案</option>{readyProfiles.map(row=><option key={row.id} value={row.id}>{row.id.slice(0,8)} · {row.calibration_sample_count}条 · {row.channel_layout.length}通道 · {row.source?.classifier_retrained?"个人分类器":"EA对齐"}</option>)}</select></label>
        {profile&&<div className="profile-info"><span className="tag real">{profile.source?.classifier_retrained?"个体化 CSP / LDA 分类器":"EA 对齐参考"}</span><p>来源：{sourceLabel(provenance(profile.source,profile.user_id,profile.channel_layout.length),p.sources)}</p><p>通道：{profile.channel_layout.join(" / ")}</p><p>校准样本：{profile.calibration_sample_count} 条 · {new Date(profile.created_at).toLocaleString("zh-CN")}</p><details><summary>查看模型校验值</summary>{profile.model_version}</details><button className="text-button" disabled={locked} onClick={p.revoke}>撤销此档案并重新校准</button></div>}
        <details className="format-help"><summary>EEG 上传格式与标签要求</summary><p>仅 .npz，压缩≤20MiB，解压≤64MiB。X 为数值数组 (N,3,501) 或 (N,22,501)，N≥2，250Hz，μV，无 NaN / Inf。校准与回放通道顺序须相同。</p><p>3通道顺序 C3/Cz/C4；22通道顺序 Fz/FC3/FC1/FCz/FC2/FC4/C5/C3/C1/Cz/C2/C4/C6/CP3/CP1/CPz/CP2/CP4/P1/Pz/P2/POz。可选 y 为长度 N 的整数数组：0左手、1右手、2双脚、3舌头。仅含 X 和可选 y；禁止 pickle。</p><p>校准和回放应为分开的采集数据，重复 trial 会被拒绝。</p><code>{'np.savez_compressed("calibration.npz", X=X, y=y)'}</code></details>
      </section>
      <section className="panel"><p className="eyebrow">第3步 · 同源回放数据</p><h2>准备实时模拟</h2>
        {!subject?<p className="small muted">选择用户后显示对应的数据准备入口。</p>:subject.is_demo?<><p className="small muted">使用所选来源的 E 会话，自动配对该来源指定的 EOG。校准集不参与回放。</p><button className="secondary" disabled={locked||!profile||!source?.available} onClick={p.createExperiment}>准备同源演示数据</button></>:<><p className="small muted">先完成校准，再上传该用户的独立 EEG 回放文件，配对 EOG 后即可演示完整闭环。</p><Upload label="上传回放 EEG · NPZ" disabled={locked||!profile} onFile={f=>p.upload(f,false)}/></>}
        <label>兼容的实验数据<select value={p.experiment} disabled={locked||!profile} onChange={e=>p.selectExperiment(e.target.value)}><option value="">请选择实验</option>{readyExperiments.map(row=><option key={row.id} value={row.id}>{row.id.slice(0,8)} · {row.source.samples}条 · {row.source.channels}通道{row.source.eog_path?" · 含EOG":" · EEG"}</option>)}</select></label>
        {experiment&&<p className="small muted">{experiment.source.samples} 条 EEG · {experiment.source.eog_path?"EOG 已配对":"缺少 EOG：允许观察 EEG 推理，设备保持 STOP"}</p>}
        {subject&&!subject.is_demo&&<><label>EOG 预处理状态<select value={String(p.eogPrefiltered)} disabled={locked} onChange={e=>p.setEogPrefiltered(e.target.value==="true")}><option value="false">原始μV · 模型执行1–15Hz滤波</option><option value="true">已完成1–15Hz带通滤波</option></select></label><Upload label="上传同源 EOG 配对 · NPZ" disabled={locked||!experiment} onFile={p.uploadEog}/><details className="format-help"><summary>EOG 配对要求</summary><p>仅含数值 X，压缩≤16MiB、解压≤64MiB，250Hz/μV，全部有限且窗口非恒定。(N,501) 与 EEG trial 一一对应；(2N,250) 按时间顺序，每个 EEG trial 对应两段。同步关系由上传者确认。</p><p>请如实选择是否已滤波，避免重复处理。</p></details></>}
        <label>回放速度<select value={p.speed} disabled={locked} onChange={e=>p.setSpeed(Number(e.target.value))}><option value={1}>1× · 原始采样速率</option><option value={2}>2× · 加速演示</option></select></label>
        <button className="primary" disabled={locked||!profile||!experiment||!compatible(profile,experiment)} onClick={p.makeSession}>创建实时模拟会话</button>
        {!p.guest&&experiment?.source.labels_present&&<button className="text-button" disabled={locked||!profile} onClick={p.evaluate}>评估带标签回放数据</button>}
        <p className="small muted">带标签数据可查看本次回放评分；信号、分类概率与设备响应在会话中同步呈现。</p>
      </section>
    </div>
  </>;
}
