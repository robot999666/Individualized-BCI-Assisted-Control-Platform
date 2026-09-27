# 个体化脑机辅助控制软件平台

面向 ALS 中晚期、重度脑卒中后遗症等重度运动障碍人群的辅助交互研究与比赛软件。
**不是医疗器械，不提供诊断、治疗或真实 ALS 临床有效性宣称。**

## 实现与边界

用户 → 独立校准集 → Calibration Profile → 真实 EEG 流式回放 → EA + FBCSP + LDA → Safety Controller → EOG 确认 → Device Gateway → 模拟器 → 告警、监控与审计。

- **REAL**：两套原有真实模型（3ch / 22ch）、SHA256校验、EA校准、窗口推理、MySQL元数据、Argon2密码、服务端Session、四角色RBAC、安全逻辑、API/进程指标与审计。
- **REAL MODEL**：已接入交付的 EOG SVM 眨眼模型，以真实 EOG 窗口检测、自动双眨眼确认；没有手动 Mock 确认接口。EEG 与 EOG 分别运行在 sklearn 1.6.1 / 1.9.1 环境，加载时校验 SHA256。
- **SIMULATED**：轮椅、护理床、紧急呼叫、智能家居；ACK、延迟、丢包、离线、超时、失败及BUSY。设备延迟和执行状态不是实体设备测量。
- **未实现**：真实EEG/EOG采集、硬件适配、ALS临床评估。公网入口使用独立 HTTPS 端口和加密会话，限公开科研演示，真实敏感数据仍需独立安全评估。

首页 `/`，工作台 `/lab/`，运行中心 `/operations/`。生理数据尽可能本地/端侧处理是设计目标；本部署上传数据在服务器执行计算。代码不把原始EEG发送第三方模型。

## 冷启动的真实含义

旧实现每次使用整个请求批次重新计算EA。本版本先执行 integration 的全局 4–36Hz 带通，再使用校准集计算 `mean(X @ X.T)`，加 `1e-6 * trace(R)/channels` 正则，保存其逆平方根矩阵为NPZ。无标签校准保持原预训练 CSP/LDA；上传含真实 y、每类至少10条的校准集时，调用交付算法重新训练 CSP/LDA，并保存真实个人分类器。两种产物在 Profile 中分别标记。修正了交付代码校准与预测的全局滤波不一致问题。

Profile保存user_id（研究参与者）、owner_id（账号）、model_version/checksum、channel_layout、calibration_sample_count、artifact_path/checksum、来源trial指纹、created_at、status。无独立验证时validation_metric为null。
后续推理读取同一Profile，逐窗口结果不随evaluation批次组成变化。模型版本或artifact checksum变化拒绝执行。撤销Profile停止关联会话。相同trial同时出现在校准与evaluation时拒绝创建会话。

原模型4个频带：4–12 /8–16 /12–24 /20–36 Hz，Butterworth + `filtfilt` + CSP + LDA。3通道为C3/Cz/C4（原22ch索引7/9/11），每频带3个特征；22ch每频带6个特征。输入250Hz、μV、501点。窗口内filtfilt非逐采样因果，窗口收齐才推理。

## 数据与指标口径

见 [改造前审计](docs/prechange-audit.md)、[数据协议](docs/data-protocol.md)。BCI Competition IV 2a有9名受试者，各T/E两会话，6 run×48 trial=288，22 EEG+3 EOG；EOG不参与分类。

Demo：A01T前40个干净trial仅用于EA校准，A01E前24个干净trial用于回放。逐trial保留原始索引、cue/sample位置、GDF与NPZ SHA256。E没有类别标签时不计算accuracy。预训练交付包声称使用全部9人，缺少完整session/trial训练清单，因此**T/E分离不等于独立模型验证**，也不能声称未见受试者表现。

原始GDF、说明PDF和转换后demo均不进入Git；在本机转换后，仅将最小demo通过SSH部署。来源许可没有在仓库中完整提供，不作再许可或公开数据集再分发。

真实S3软件回归（2026-09-26 Windows Python3.12.7）：3ch 288条=63.5417%，22ch 288条=82.9861%，重复预测逐值一致；批量模型计算约55.9ms/371.7ms，非实时硬件性能、非独立泛化指标。S3参与过训练。71.3%、53.6%缺少可复核实验记录；60.4%未查到出处，均不用于正式页面宣传。

## 本地启动（Windows，Python3.12 / Node22+ / MySQL8）

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
# 本地MySQL绑定127.0.0.1，创建als_bci数据库及专用账号
# 按.env.example建立未提交的.env，填写DATABASE_URL；凭据至少12字符
cd backend
.venv/Scripts/python -m alembic upgrade head
# 将四个BCI_<ROLE>_PASSWORD作为环境变量设置（不要写入命令历史）
.venv/Scripts/python -m app.platform.seed
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

GDF转换使用单独环境，避免MNE1.9/NumPy2读取GDF时的uint8溢出；推理仍保持NumPy2.2.6/SciPy1.15.3/sklearn1.6.1/MNE1.9.0：

```powershell
python -m venv runtime/gdf-env
runtime/gdf-env/Scripts/python -m pip install -r scripts/requirements-gdf.txt
runtime/gdf-env/Scripts/python scripts/prepare_demo.py
python -m venv runtime/eog-env
runtime/eog-env/Scripts/python -m pip install -r backend/requirements-eog.txt
backend/.venv/Scripts/python scripts/prepare_eog_demo.py
cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm run build
cd ..
backend/.venv/Scripts/python scripts/preview.py
# http://localhost:3000，静态生产构建，同源/api代理到8000
```

开发热更新可在frontend运行npm run dev；跨端口开发显式配置 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`，生产留空走同源 `/api`。`scripts/preview.py`仅本地使用。

## 可重复Demo

1. 在登录旁查看演示访客账号密码，登录后创建/选择演示用户。
2. 开始个体化校准，确认40条、3ch、EA reference与模型checksum。
3. 创建Demo实验，选择Profile和Evaluation Set，1×创建会话。
4. 开始回放，250Hz释放样本，观察真实波形/概率/各阶段耗时。
5. 第3个窗口通常出现连续2窗右转且置信度>55%，随后第7/8秒真实EOG片段经模型识别为两次眨眼，自动确认并产生RIGHT和SIMULATED ACK。窗口切换可立即恢复STOP；持久命令记录保留ACK证据。
6. 暂停/继续/重置；把轮椅设OFFLINE，下一窗口STOP/REJECTED，告警和审计出现记录。
7. 测试DELAY、DROP、TIMEOUT、FAILURE。紧急求助最高优先并锁定STOP，重置后才能重新播放。
8. 运行中心查看记录；caregiver可查看和处理脱敏Demo告警，不能上传、校准或修改配置。

四个角色为管理员、研究人员、照护人员和演示访客。页面只公开低权限演示访客账号；其余账号通过私密交付文件提供。管理员可以创建账号、改权限/停用账号、查看模型校验值、配置新会话安全阈值（0.5–0.99）和稳定窗数（2–5）。研究人员仅访问自己的参与者、校准档案、实验及日志；可上传带真实标签的实验做预测评分。访客只允许内置公开Demo。照护人员可查看并处理获授权的脱敏Demo告警。

## 安全与运维

- 密码Argon2id；随机不透明Session令牌只以SHA256保存到数据库；HTTPS 下使用 Secure、HttpOnly、SameSite=Strict Cookie，8小时有效，停用/权限变更撤销会话。
- 写请求校验Origin；生产要求X-BCI-Request头；登录/API速率限制；生产关闭/docs、/redoc、/openapi.json。生产环境 `SECURE_COOKIE=true`。
- 上传限制20MiB，NPZ解压64MiB；类型、shape、有限值、标签、路径检查，禁止用户pickle；artifact以随机ID按账号目录隔离。
- 安全默认停止：低置信度、预测不稳定、无确认、设备离线/忙碌/故障、过期或异常；单次确认绑定窗口且不能重放；运动许可3秒到期停止；客户端6秒无活动自动暂停，重启不自动恢复运动。
- 单worker拥有回放时钟和模拟器；当前不支持横向多worker共享实时会话。关闭会话释放内存；持久记录保留。日志仅元数据，不记录EEG/密码/令牌。
- API和推理计时用perf_counter；回放用monotonic；模拟设备延迟由计划事件实现，标记SIMULATED，未用sleep伪造推理耗时。计算延迟不含采样等待、网络传输或数据库最终commit。

```powershell
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python scripts/benchmark_bci.py
```

生产使用本地已验证静态构建 + Nginx + systemd + MySQL；不依赖SSH终端，不需要生产Node进程。公网 HTTPS 入口为 `https://152.136.191.171:9443`，Lighthouse 实例防火墙已放行 TCP 9443。HTTP 80 仅承载 IP 证书验证和 HTTPS 跳转，443 留给服务器其他项目。Let's Encrypt 短期 IP 证书由每6小时检查的定时器自动续期。见 [部署与故障排查](docs/operations.md)。`deploy/install.sh`只安装已上传的已验证release，`.env`位于/etc、模型在代码目录、数据在/var/lib，避免代码更新覆盖用户产物。

## 核心API

`/api/v1/health/live`（匿名状态）；`/api/v1/health/detail`（仅管理员）；`/auth/login|me|logout`；`/users`；`/subjects`；`/sessions/{id}/stream`（WebSocket 推送）；`/sessions/{id}/control|emergency-stop`；`/operations`；`/alerts/{id}/ack`；`/configuration`。

实时会话经受 Cookie 认证的 WebSocket 由服务端推送脑电块、预测、眼电事件与设备状态；反向代理配置了连接升级和长连接超时。旧批量 analyze/demo 和 RAG 接口仅管理员/研究人员在生产可访问，不控制设备。RAG为可选旧功能，当前不在控制UI启用，未配置第三方密钥也可完整演示。

## 目录与真实 EOG 数据

`algorithms/bci_4class`：原 EEG 算法、权重、S3 回归样本；`algorithms/system_integration`：交付的 EEG/EOG 集成算法和运行权重；`algorithms/eog_blink`：EOG 数据构建、训练、推理来源代码及本机缓存。
`backend` / `frontend`：产品服务；`scripts`：预处理和模型工作进程；`deploy`：部署配置；`docs`：项目说明；`sample_data`：本地原始和最小演示数据；`runtime`：本地私有运行环境；`temp`：临时脚本、日志、截图、原始备份。后两者不进入 Git 或服务器发布包。

用户提供的 eog_dataset.npz 含23529个250点窗口，来源代码以幅度/峰值规则自动标注，最终模型训练使用全部窗口。它不是独立人工标注评测集，不发布99.95%等无法复核的指标。缓存已过1–15Hz带通，回放不会重复过滤，也不启用依赖DC的持续偏移规则。

`prepare_eog_demo.py`从该缓存选48段真实信号，显式把两个眨眼样本排在6–8秒，和2a EEG构成离线配对软件场景。**不是同一受试者同步采集，不是原始连续EOG记录，也不是独立准确率验证。** 行号、受试者编号、伪标签、来源哈希全部写入manifest。无EOG输入时不会产生移动确认；模型异常默认STOP。

私有研究实验可以上传EOG NPZ（只有X）：(N,501)对应EEG各trial，或(2N,250)片段序列；250Hz、μV。上传者须如实声明是否已经带通处理，说明同步关系；平台不凭上传自动宣称同步采集。原始EOG缓存约40MB仅本机保留，不提交或完整上传。
