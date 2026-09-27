# 平台架构

Next.js静态前端 → 同源Nginx /api → FastAPI单worker → MySQL与文件artifact。
用户会话令牌为数据库保存SHA256的随机token，不需要JWT secret。密码Argon2id。roles/user_roles实现四角色限制；subjects为研究参与者，owner_id是登录账号。

校准：安全NPZ → mean(X X^T) → 正则 → R^-1/2 → 账号隔离artifact → MySQL Profile元数据。
回放：固定Profile → 后端250Hz时钟分块释放真实EEG →501点完整窗口→EA→四频带滤波→CSP→LDA→四类概率→安全决策。
EOGProvider使用真实SVM模型实现，版本隔离子进程加载并校验权重；DeviceAdapter目前只有Simulator实现，后续可接MQTT/HTTP/WebSocket/Serial。预测不会绕过统一安全控制层直达设备。

实际表：users, roles, user_roles, login_sessions, subjects, calibration_profiles, experiments, inference_sessions, inference_records, devices, device_commands, alerts, audit_logs, system_configuration。通过Alembic建表；大型模型和EA不进入数据库。
回放内存态不跨进程共享；重启关闭旧会话、全部STOP；重新选择持久Profile创建会话即可重载。实时会话通过带Cookie认证的WebSocket推送样本窗口、预测、EOG事件和设备状态；模型同步推理在线程池执行，并由信号量限制并发数。

旧批量REST接口仍保留软件回归用途，生产仅研究员/管理员访问，不具有设备控制权。旧RAG界面已停用；第三方密钥不参与主流程。
