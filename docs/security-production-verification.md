# 安全加固版本公网验收

日期：2026-09-29（北京时间）。入口：https://152.136.191.171:9443/。

## 已发布版本

- 代码提交：`4e68fedae490f49395b5a4a966907419cfa6e9d6`，已推送 GitHub `main`。
- 当前发布目录：`/opt/als-bci/releases/security-4e68fed`；`/opt/als-bci/current` 指向该目录。
- 后端独立环境：`/opt/als-bci/venvs/security-4e68fed`。全部 65 项依赖与锁文件一致，`pip check` 通过；EEG 模型运行依赖仍为 NumPy 2.2.6、SciPy 1.15.3、scikit-learn 1.6.1、MNE 1.9.0；原 EOG 环境仍使用 scikit-learn 1.9.1。
- 旧发布 `/opt/als-bci/releases/hero-34b08d4` 和旧依赖环境保留。旧前端 `_next` 资源复制至新发布目录，兼容切换前已打开的页面。
- 发布包 SHA-256：`ea945d906686261a713226b3679d03bc990b74a5625925842bdf6a20359d018b`；服务器检查发布包和 52 项静态构建文件校验值通过。
- 后续文档提交仅记录验收结果，不改变上述运行代码版本。

## 备份及数据保留

备份目录：`/var/backups/als-bci/20260929T081356Z-security-4e68fed`，root 私有权限。包含数据库备份、artifacts/demo、原环境文件、原 systemd/Nginx 配置和旧发布路径。未改变表结构、账号密码、生产环境内容或演示数据来源；原环境文件 SHA-256 一致。

| 切换前后核对对象 | 切换前 | 切换后、业务验收前 |
| --- | ---: | ---: |
| 用户 | 4 | 4 |
| 校准档案 | 13 | 13 |
| 参与者 | 7 | 7 |
| 实验 | 11 | 11 |

业务验收随后通过现有脚本添加一组明确命名的演示参与者、校准与实验记录，验证真实闭环。测试会话均已关闭，原记录未删除。

## 验收结果

- `als-bci`、Nginx、MySQL 均 active；`nginx -t` 通过。API 8000、MySQL 3306 仍仅监听回环地址；沿用专用 HTTPS 9443，未调整共享 443、证书或防火墙。
- 首页、工作台、运行中心 HTTP 200；11 项首屏资源 HTTP 200。三个页面的 CSP 内联脚本哈希全部匹配，frame-ancestors、nosniff、DENY 等响应头生效。
- 四角色登录、Secure Cookie、角色访问限制、生产 MySQL 和真实 EOG 健康检查通过；四套来源可用，智答实际回答及引用通过。
- 40 试次个体化校准、实验准备、真实 EEG/EOG 确认、模拟设备 ACK、离线拒绝、护理角色告警处理、审计、人工急停锁定和重置均通过。
- 两个共享访客客户端独立创建会话；创建第二个会话或退出第一个客户端不会关闭另一个。有效 WebSocket 收到实时快照；跨站连接和写请求返回 403，允许三条流并拒绝第四条。
- 超过 16KiB 的 JSON 返回 413，129 字符密码返回 422 且不回显密码；`.env`、安全头配置文件和生产 API 文档路径禁止访问。
- 公网浏览器验证新版 3D 首页、访客登录、工作台与运行中心正常，未发现 CSP/脚本错误；Three.js 原有 API 弃用提示仍存在。
- 服务器隔离回归：**98 passed，3 warnings，47.69s**。运行时明确提供 `EOG_PYTHON=/opt/als-bci/eog-venv/bin/python`、`DEMO_DATA_DIR=/var/lib/als-bci/demo` 与单线程 BLAS；数据库和写入 artifact 由测试脚本创建在临时目录。首次未指定演示数据/EOG 路径的运行失败，配置路径后全部通过，未触及生产数据库。
- 发布后检查服务错误日志无错误条目。大规模并发压力和分布式限流不属于本次已完成验收。

本地补充证据：`temp/deploy/security-public-acceptance.json`、`output/security-review/public-workspace.png`、`output/security-review/public-operations.png`。服务器私有业务验收和共享账号验证记录保存在上述备份目录，未公开完整 API 输出、账号口令或环境秘密。

## 回滚

停止 `als-bci`，将 current 原子恢复至备份 `previous-release` 记录的旧目录，恢复备份 `als-bci.service` 与 `nginx.conf`，执行 `systemctl daemon-reload`、`nginx -t`、重启后端并重载 Nginx。旧 unit 使用保留的旧依赖环境。恢复后检查公网健康和登录；本次无数据库迁移，不自动覆盖业务数据库和用户文件。
