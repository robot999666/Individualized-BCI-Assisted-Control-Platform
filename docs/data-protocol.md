# 数据协议与可复现性

原始来源：用户本地提供的 BCI Competition IV 2a GDF 与 desc_2a介绍.pdf。已核对PDF全6页。
9 subjects A01–A09，每人T(训练标签)/E(评测隐藏标签)不同日期两会话；6 runs×48 trials。250Hz，前22通道EEG、后3通道EOG。原始类别1..4映射软件0..3。

事件：768 trial开始；769/770/771/772 左手/右手/双脚/舌头提示；783未知提示；1023专家标记伪迹；32766新run；276/277眼开/闭；1072眼动。trial开始2秒后出现cue，想象持续到trial第6秒。run边界缺失值排除，A04T的EOG段特殊。

`scripts/prepare_demo.py`只提取A01T/A01E；按原始顺序排除有1023或非有限值的trial，选T前40和E前24，取cue+125至cue+626（右开）共501点，C3/Cz/C4索引7/9/11，V转μV。此epoch选择是公开记录的演示协议；原权重无epoch配置证据，不能声称精确复现原训练预处理。

输出calibration.npz / evaluation.npz / manifest.json。后者包含GDF/NPZ SHA256、subject、会话文件名、每个trial原始编号、cue位置、window起止、事件码、采样率、通道及协议。校准仅用T；回放仅用E；E不参与EA估计。

模型包README说全部9人训练，缺少session/trial完整训练记录，因此不把A01E称为独立模型测试；无E标签不计算accuracy。用户上传带标签文件可计算描述性评分，明确pretraining overlap unknown。Profile validation_metric保持null，除非未来确有可复核独立验证。

转换单独使用NumPy1.26.4/SciPy1.15.3/MNE1.9.0，模型推理使用NumPy2.2.6/SciPy1.15.3/sklearn1.6.1/MNE1.9.0。原始数据和转换结果均不提交Git，部署仅私下传输必要demo。未见完整再分发许可，不提供原始数据公网下载入口。

最新integration README明确cue+0.5~2.5秒；平台新增全局4–36Hz预处理并将pipeline_version写入Profile。旧EA Profile拒绝直接复用，必须重新校准。EOG真实片段配对及训练重叠说明见根README；manifest保存完整来源行号。

## 工作台来源与上传协议

`GET /api/v1/data-sources` 提供服务器管理的四套来源：A01 / A02 的 3ch / 22ch。A01 3ch 为原演示数据，另外三套通过 `runtime/gdf-env/Scripts/python scripts/prepare_sources.py` 准备到 demo_processed 子目录。每套校准为同一受试者 T 会话40条，回放为 E 会话24条，文件与来源均有 SHA256 校验；缺失来源显示“未准备”。此脚本需要原 Demo 和 EOG pairing 已准备。

A01 两种通道布局使用同一组 EEG trial，沿用明确声明的 2b EOG 片段离线配对场景，适合展示双眨眼闭环。A02 两种布局使用 A02E 同一 GDF 的通道23，按照每个 EEG trial 的 sample_start / sample_stop 提取同步 EOG 原始μV数据，保留原始 sample_start 给重叠窗口去重。电极方向、眨眼标签未经独立验证，不保证产生移动确认；不能把未确认的 STOP 视为模型未运行。

校准、实验的 source_id 与通道布局必须匹配，用户必须相同；创建会话和带标签评分均在服务端检查。旧 A01 Profile / Experiment 仍按 subject、channels 推导来源键。更换来源需关闭会话，再选择或生成对应档案；新会话输入全部校验成功后才关闭旧会话。

私有用户 EEG 上传为仅含 X 和可选 y 的 NPZ。X 数值形状 (N,3,501) 或 (N,22,501)，N≥2，250Hz、μV、全部有限；压缩≤20MiB、解压≤64MiB。3ch 顺序 C3/Cz/C4；22ch 顺序 Fz/FC3/FC1/FCz/FC2/FC4/C5/C3/C1/Cz/C2/C4/C6/CP3/CP1/CPz/CP2/CP4/P1/Pz/P2/POz。y 为长度 N 的整数数组，取0左手/1右手/2双脚/3舌头。无 y 保存 EA；有 y 必须每类≥10条，保存实际训练的个人 CSP/LDA 分类器。

上传表单 `source_id` 为采集来源标识，默认 default。服务器保存 `upload:<subject_id>:<source_id>`；同一用户的校准与回放必须使用相同标识，且不能包含重复 trial。这个声明无法证明文件实际来自同一人，采样率、单位、通道顺序和同步关系须由上传者正确准备，平台不宣称自动验证身份或独立泛化准确率。

私有实验的 EOG 上传仅含 X，形状 (N,501) 或 (2N,250)，250Hz、μV、有限数值且每个检测窗口非恒定；压缩≤16MiB、解压≤64MiB。`prefiltered=true` 仅用于已完成1–15Hz带通的信号。已有活动会话使用该实验时禁止替换 EOG；需先关闭会话。无 EOG 时允许查看 EEG 实时推理，禁止产生移动确认。

工作台命令、告警与响应统计按当前 session_id 过滤；运行中心保留有权查看的历史。服务器实时流断开最后一个客户端时暂停回放并停止设备；网络无响应时6秒 watchdog 兜底。暂停冻结游标；重置、急停、撤销、退出或权限变更使旧推理失效。回放结束立即 STOP；人工急停记录 MANUAL_EMERGENCY，需重置才能继续。
