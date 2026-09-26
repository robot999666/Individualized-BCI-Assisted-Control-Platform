# 改造前审计（2026-09-26）

本地最初缺少源码、模型与 .git。经 GitHub API 核对仓库 README 与残留脚本后，从 robot999666/als-bci-web 的 723c98b 恢复缺失文件；已有文件逐字节比对（忽略 CRLF）一致，未覆盖已有内容。恢复副本在 D:/recent/als-bci-recovery。

## 原架构
Next.js 16.3.1 / React 19 / TypeScript / Tailwind v4 / ECharts。FastAPI 通过 uvicorn app.main:app 启动；npm run build 生产构建。现有 compose 仅提供后端，未包含数据库，暂不作为本次生产方式。
REST analyze/demo → Bci4ClassService → RuntimeModel → EA → 四频带 Butterworth filtfilt → MNE CSP → sklearn LDA。3ch=[C3,Cz,C4]，22ch 为标准布局；每频带分别3/6个CSP特征，4频带共12/24维。启动校验固定 SHA256 并执行4条真实数据自测，失败不回退 Mock。

## 冷启动
原实现以请求全部 trial 的 mean(X @ X.T) 加 trace-scaled 1e-6 正则，计算逆平方根；无用户状态、无专属模型。独立 FBCSPModel.fit 可重新训练但不在现有 Web 路径中。本次产品化保存校准集逆平方根矩阵与模型 checksum，固定预训练 CSP/LDA；不是重新训练模型。filtfilt 使用当前完整窗口，在窗口收齐后推理，不能宣称逐采样点因果滤波。

## 数据审计
已读 sample_data/desc_2a介绍.pdf 全6页。9名受试者，各有不同日期T/E两会话；每会话6 run ×48 trial=288，每类72。250Hz；22 EEG +3 EOG，EOG不得参与运动想象分类。trial开始768，2秒后提示769/770/771/772（左手/右手/双脚/舌头）；783为未知类别；1023为拒绝trial；32766为run开始；276/277/1072为EOG相关段。run之间缺失值不得直接作为有效EEG。A04T EOG段特殊。原始18个GDF完整存在。

S3 README明确参与冷启动训练；交付包称模型使用全部9人，但没有可复核训练脚本、session/trial清单。不能把任何受试者标为未见用户，也不能确认E会话未参与训练。T/E物理分离能保证本次EA校准/回放不泄漏，但不能建立独立模型测试结论。Demo选择A01T前40个干净trial校准、A01E前12个干净trial回放，记录原始trial/event/sample索引、SHA256；E标签缺失时不算accuracy。501点窗口采用cue后0.5至2.5秒，原权重没有epoch出处，作为明确记录的演示协议，不声称复现训练协议。

## 指标
63.54% /82.99%为S3软件回归口径，需实际重新运行。71.3%/53.6%只见文档说明，无fold/seed/预测记录；60.4%未找到。均不进入正式首页。演示CSV由DemoProvider生成，不能当成真实EEG。

## 部署预检
SSH可达；本机私钥ACL过宽，收紧为当前用户后认证成功，未复制或输出私钥。Ubuntu 24.04内核6.8，3.6GiB内存、1.9GiB swap、40GB磁盘剩余33GB；仅SSH和DNS监听，Python3存在，尚无Node/Nginx/MySQL/Docker。计划本地验证后采用Nginx静态前端 + systemd FastAPI + localhost MySQL。
