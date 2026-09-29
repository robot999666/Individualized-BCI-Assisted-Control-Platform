# 生产部署与运维

入口：https://152.136.191.171:9443/。Lighthouse 实例防火墙和 UFW 已允许入站 TCP 9443，公网访问已验收。HTTP `:80` 用于 Let's Encrypt IP 证书验证和跳转，应用 TLS 在专用 `:9443` 终止，不占用共享 `:443`。公网 HTTPS Cookie 设置 `SECURE_COOKIE=true`。证书约6天有效，由 systemd 定时器每6小时检查续期并在续期后重载 Nginx。

## 目录与环境

- `/opt/als-bci/current`：已验证代码和静态前端；模型`algorithms/bci_4class/models` 和 `algorithms/system_integration/models`；S3仅回归自测。
- `/opt/als-bci/venvs/security-4e68fed`：当前后端 Python3.12 锁定环境；`/opt/als-bci/venv` 保留供旧版本回滚，systemd 的 ExecStart 指明实际环境。
- `/var/lib/als-bci/artifacts`：校准EA、上传/实验NPZ，按owner隔离。
- `/var/lib/als-bci/demo`：最小T/E转换数据与manifest。
- `/etc/als-bci.env`：root 600，数据库和预置账号秘密；严禁进入Git。
- MySQL数据库`als_bci`，专用用户`als_bci@127.0.0.1`。
- Node仅在本地构建，生产没有Node/前端常驻服务，Nginx直接读取frontend/out。

## 首次部署

服务器只运行已在本地验证的代码；先准备apt的nginx/mysql-server/python3-venv。
上传白名单release包（代码、模型、自测样本、静态构建、deploy；不含.env/私钥/raw GDF/缓存），解压到`/opt/als-bci/current`。
单独将最小demo放`/var/lib/als-bci/demo`，owner为als-bci。执行`sudo bash /opt/als-bci/current/deploy/install.sh`。
多来源工作台还需将本地 `prepare_sources.py` 生成的 `a01-22ch`、`a02-3ch`、`a02-22ch` 子目录连同各自 manifest / calibration / evaluation / EOG 一并私下复制到 Demo 目录，保留相对结构；缺失目录仅禁用对应来源。安装后端依赖必须包含固定版本 websockets，且 Nginx / 本地 preview 必须转发 Upgrade，否则无法建立实时流。原始 GDF 不部署。
脚本生成随机账号密码而不输出，凭据仅`/root/als-bci-accounts.json`，通过SSH私下交付。

## 服务

| 服务 | 监听 | 管理 |
|---|---|---|
| als-bci.service | 127.0.0.1:8000 | 单worker Uvicorn/FastAPI，崩溃3秒后重启 |
| nginx.service | :80、:9443 | :80 处理 ACME 验证和跳转；:9443 提供 TLS 静态前端、API 和 WebSocket 反代 |
| mysql.service | 127.0.0.1:3306（X插件33060也为loopback） | MySQL8，开机启动 |
| ssh.service | :22 | 运维 |

公网入口需要 80（证书 HTTP-01 验证及跳转）与 9443（HTTPS 站点）；保留既有 22、80、443 云端和 UFW 规则，不改写其他项目端口。部署只为 9443 添加 UFW 规则，Lighthouse 实例防火墙也需允许 TCP 9443。FastAPI 8000 与 MySQL 3306/33060 继续只监听回环地址。当前 Lighthouse 实例防火墙规则已配置并验收。

```bash
sudo systemctl start als-bci nginx mysql
sudo systemctl stop als-bci
sudo systemctl restart als-bci
sudo systemctl status als-bci nginx mysql --no-pager
sudo journalctl -u als-bci -n 100 --no-pager
sudo journalctl -u als-bci -f
sudo tail -n 100 /var/log/nginx/access.log  # 前端访问
sudo tail -n 100 /var/log/nginx/error.log   # 前端/反代错误
sudo systemctl status mysql --no-pager
sudo tail -n 100 /var/log/mysql/error.log
curl -fsS http://127.0.0.1:8000/api/v1/health/live
curl -fsS https://152.136.191.171:9443/api/v1/health/live
sudo certbot renew --dry-run --run-deploy-hooks
systemctl status als-bci-certbot-renew.timer --no-pager
sudo ss -lntp
sudo ufw status
```

更新：本地测试/构建 → Git commit/push → 上传白名单release → 维护窗口停止als-bci → 备份MySQL与artifacts → 更新代码 → 读取生产环境后Alembic upgrade head → 重启服务 → 验收。保留旧release可回退；不要覆盖数据目录。当前部署不是高可用集群。

`scripts/package_release.py`从已提交的HEAD与已验证的frontend/out制作发布包，并单独打包四套最小演示数据。环境配置单独经SSH传输、合并到`/etc/als-bci.env`，不放进代码包。智答配置为`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`，当前模型为deepseek-v4.1-flash；生产所有已登录角色可使用项目智答，匿名仅能看health。

安装依赖时使用umask 022，确保服务账号可读取site-packages；切换前执行`runuser -u als-bci -- /opt/als-bci/venv/bin/python -c 'import websockets.legacy.handshake'`。私有环境和备份仍保持root 600/700。健康检查失败则恢复旧release链接与旧环境并重启，不自动覆盖数据库。完整公网验收使用`verify_deployment.py`和root私有账号文件，包含四角色、来源就绪、RAG真实调用、真实EEG/EOG闭环、模拟ACK、离线保护、告警处理、急停和重置。

2026-09-27已发布工作台、四来源、实时3D与智答版本，功能提交`4e6422d77fe692d36d716f5d9adc138f92acc9b3`。目录`/opt/als-bci/releases/4e6422d`，原版本`/opt/als-bci/releases/3695446`保留；升级前备份`/var/backups/als-bci/20260927T074253Z-4e6422d`。数据库及用户文件已备份，升级前后已有用户/校准/实验记录数量一致。API与公网浏览器验收通过，详见[公网验收记录](production-release-verification.md)。

2026-09-29已发布安全加固版本`4e68fed`，current 指向`/opt/als-bci/releases/security-4e68fed`，备份为`/var/backups/als-bci/20260929T081356Z-security-4e68fed`。后端依赖采用独立环境，旧代码与旧环境保留，生产秘密和用户文件未覆盖。既有站点更新使用`deploy/update-security.sh STAGING_DIRECTORY COMMIT`，不重复运行首次安装脚本。业务、公网安全头、共享访客隔离、实时连接与服务器98项回归通过，详见[安全版本公网验收](security-production-verification.md)。

## 故障排查

| 现象 | 排查与处理 |
|---|---|
| 公网网站打不开 | 先查 Lighthouse 实例防火墙入站 TCP 9443，再查 UFW、Nginx监听和静态out；服务器本机可用 `curl -fsS https://152.136.191.171:9443/api/v1/health/live` 验证 |
| Nginx 502 | 查als-bci与127.0.0.1:8000；journalctl；不要把8000开放公网 |
| FastAPI起不来 | 查env权限/格式、Python依赖、数据库迁移与WorkingDirectory；单worker |
| model load failed | 查两个模型SHA256、文件权限、NumPy2.2.6/SciPy1.15.3/sklearn1.6.1/MNE1.9.0；不能回退Mock |
| MySQL connection failed | systemctl mysql、loopback监听、数据库账号、DATABASE_URL；不要输出密码 |
| Calibration failed | 查NPZ类型/shape/250Hz/μV/有限值/非零能量、磁盘容量与artifacts写权限；demo manifest checksum |
| WebSocket disconnected | 检查 HTTPS Cookie、Origin 白名单、9443 端口与 Nginx Upgrade 头；会话关闭或服务重启后需重新创建 |
| device simulator offline | 工作台选择ACK恢复SIMULATED ONLINE，查STOP/告警；重置紧急锁定再回放 |
| disk full | df -h；按保留策略备份/清理日志、过期artifact，勿直接删除仍被Profile引用的文件 |
| memory high | free -h、systemctl status、查看活动会话；关闭会话、限制上传；单worker，必要时扩容 |
| 401/403 | Session过期重新登录；检查角色和Origin；生产写请求需要X-BCI-Request:1 |
| 重启后会话409 | 设计为fail-closed；选择已有Profile重新创建会话，不自动恢复运动 |

## 监控口径

REAL：API累计请求/错误、最近2000次API平均延迟、CPU/内存、五分钟内活动登录用户、模型/数据库/文件健康、审计、真实计算时延。进程重启后内存计数重新开始，MySQL审计仍保存。
SIMULATED：设备状态、ACK、延迟、丢包/超时/执行失败；运行中心统计可见最近100条命令。无真实硬件网络测量。
本版本使用事件轮询模拟网关延迟；其耗时不混入模型时延。模型时延不含采样等待、网络和最终数据库提交。

EOG使用 `/opt/als-bci/eog-venv`（sklearn1.9.1），由后端启动持久工作进程；启动校验失败不会回退Mock。`EOG_PYTHON`必须指向该环境。
