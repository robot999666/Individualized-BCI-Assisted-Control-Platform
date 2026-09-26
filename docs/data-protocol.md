# 数据协议与可复现性

原始来源：用户本地提供的 BCI Competition IV 2a GDF 与 desc_2a介绍.pdf。已核对PDF全6页。
9 subjects A01–A09，每人T(训练标签)/E(评测隐藏标签)不同日期两会话；6 runs×48 trials。250Hz，前22通道EEG、后3通道EOG。原始类别1..4映射软件0..3。

事件：768 trial开始；769/770/771/772 左手/右手/双脚/舌头提示；783未知提示；1023专家标记伪迹；32766新run；276/277眼开/闭；1072眼动。trial开始2秒后出现cue，想象持续到trial第6秒。run边界缺失值排除，A04T的EOG段特殊。

`scripts/prepare_demo.py`只提取A01T/A01E；按原始顺序排除有1023或非有限值的trial，选T前40和E前24，取cue+125至cue+626（右开）共501点，C3/Cz/C4索引7/9/11，V转μV。此epoch选择是公开记录的演示协议；原权重无epoch配置证据，不能声称精确复现原训练预处理。

输出calibration.npz / evaluation.npz / manifest.json。后者包含GDF/NPZ SHA256、subject、会话文件名、每个trial原始编号、cue位置、window起止、事件码、采样率、通道及协议。校准仅用T；回放仅用E；E不参与EA估计。

模型包README说全部9人训练，缺少session/trial完整训练记录，因此不把A01E称为独立模型测试；无E标签不计算accuracy。用户上传带标签文件可计算描述性评分，明确pretraining overlap unknown。Profile validation_metric保持null，除非未来确有可复核独立验证。

转换单独使用NumPy1.26.4/SciPy1.15.3/MNE1.9.0，模型推理使用NumPy2.2.6/SciPy1.15.3/sklearn1.6.1/MNE1.9.0。原始数据和转换结果均不提交Git，部署仅私下传输必要demo。未见完整再分发许可，不提供原始数据公网下载入口。

最新integration README明确cue+0.5~2.5秒；平台新增全局4–36Hz预处理并将pipeline_version写入Profile。旧EA Profile拒绝直接复用，必须重新校准。EOG真实片段配对及训练重叠说明见根README；manifest保存完整来源行号。
