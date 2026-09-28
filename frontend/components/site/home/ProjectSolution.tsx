import SectionHeading from "@/components/site/SectionHeading";

const STEPS = [
  {
    title: "组织标准脑电窗口",
    text: "以 250 Hz 采样率截取 2 秒、501 点脑电窗口，兼容 3 通道与 22 通道数据布局。",
  },
  {
    title: "提取频带空间特征",
    text: "以四个重叠频带保留运动皮层 μ（mu）与 β（beta）节律，再通过 CSP 提炼判别特征。",
  },
  {
    title: "输出四类辅助指令",
    text: "由正则化 LDA 输出四类概率，并在网页端呈现波形、置信度和逐试次结果。",
  },
];

const INTENT_MAPPING = [
  { command: "左转", imagery: "左手运动想象", color: "border-cyan-400/30" },
  { command: "右转", imagery: "右手运动想象", color: "border-indigo-400/30" },
  { command: "直行", imagery: "双脚运动想象", color: "border-emerald-400/30" },
  { command: "停止", imagery: "舌头运动想象", color: "border-amber-400/30" },
];

export default function ProjectSolution() {
  return (
    <section
      id="solution"
      className="scroll-mt-24 border-y border-slate-800/70 bg-slate-950/45 py-24"
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <SectionHeading
          eyebrow="项目方案"
          title="从运动想象脑电到离散辅助指令"
          description="个体化脑机辅助控制平台 将科研数据、算法模型和网页交互整合为一条可操作、可观察、可复现的实验链路。"
        />
        <div className="grid gap-5 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <article key={step.title} className="card-surface relative rounded-2xl p-7">
              <span className="text-[13px] font-semibold tracking-[0.16em] text-cyan-400">
                步骤 {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="mt-5 text-lg font-semibold text-white">{step.title}</h3>
              <p className="mt-3 text-[15px] leading-7 text-slate-400">{step.text}</p>
            </article>
          ))}
        </div>
        <div className="mt-8 rounded-3xl border border-slate-800 bg-slate-900/45 p-6 sm:p-8">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-[13px] font-semibold tracking-[0.14em] text-cyan-300">
                指令映射
              </p>
              <h3 className="mt-2 text-xl font-semibold text-white">
                四类运动想象对应四个离散控制方向
              </h3>
            </div>
            <p className="text-[13px] text-slate-500">类别编号 0–3</p>
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {INTENT_MAPPING.map((item, index) => (
              <div
                key={item.command}
                className={`rounded-2xl border bg-slate-950/45 p-5 ${item.color}`}
              >
                <p className="text-[12px] text-slate-500">类别 {index}</p>
                <p className="mt-2 text-xl font-bold text-white">{item.command}</p>
                <p className="mt-2 text-[15px] text-slate-400">{item.imagery}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
