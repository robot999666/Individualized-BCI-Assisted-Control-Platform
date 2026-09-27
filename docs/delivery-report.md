# 交付与部署验收报告

验收日期：2026-09-27，Asia/Shanghai。工作区：`D:\recent\web`。

## 访问与账号

- Web：<https://152.136.191.171:9443/>
- 工作台：<https://152.136.191.171:9443/lab/>
- 运行中心：<https://152.136.191.171:9443/operations/>
- API：<https://152.136.191.171:9443/api/v1>
- TLS 使用 Let's Encrypt 公网 IP 证书，Secure Cookie 已启用。专用 HTTPS 端口为9443，Nginx不监听443；80只用于ACME验证及跳转。
- 服务器本机HTTPS和证书链验证正常。外网9443连接当前超时，需在腾讯云安全组对该实例增加入站TCP 9443规则后公网访问才会生效；腾讯云控制台当前未登录，未修改安全组。公开科研Demo，不接收真实患者敏感数据。
- 四角色：demo_admin、demo_researcher、demo_caregiver、demo_guest。
- 密码仅在本机忽略文件 `runtime/production-accounts.json` 与服务器root专用600权限文件中；此报告不包含密码。该文件已通过SSH私下交付至本机。

## 实现结果

用户/研究参与者 → 独立校准 → 保存Calibration Profile → 250Hz真实EEG回放 → 全局4–36Hz预处理/EA/FBCSP/LDA → 安全检查 → 真实EOG SVM双眨眼确认 → Device Gateway → 四类设备模拟器 → 告警、监控与审计。

无标签校准保存EA逆平方根矩阵，保持预训练CSP/LDA；有真实标签且每类至少10条的上传校准调用交付算法，训练并保存用户CSP/LDA。Profile保存来源、通道、pipeline version、权重/产物checksum，重新加载时逐项核对。未独立验证时validation_metric为null。

EOG已经使用交付的真实模型，没有Mock确认按钮或Mock确认API。由独立sklearn1.9.1工作进程计算概率和耗时；EEG维持sklearn1.6.1。连续两次不同峰确认，重复窗口不会重复计为眨眼；持续偏移急停规则仅适用未带通的原始输入，规则不是闭眼诊断。

## 数据与目录

代码按 `algorithms`、`backend`、`frontend`、`scripts`、`deploy`、`docs` 分层。

| 内容 | 路径 |
|---|---|
| MySQL数据库 | als_bci，专用als_bci@127.0.0.1账号 |
| 校准/个人模型/实验产物 | /var/lib/als-bci/artifacts，按owner隔离 |
| 最小demo | /var/lib/als-bci/demo |
| EEG原权重 | /opt/als-bci/current/algorithms/bci_4class/models |
| EEG/EOG集成代码与EOG权重 | /opt/als-bci/current/algorithms/system_integration |
| 私有生产配置 | /etc/als-bci.env，root600 |
| 本机原始EOG缓存 | algorithms/eog_blink/eog_dataset.npz，仅本机、Git忽略 |
| 临时脚本/截图/日志/备份 | temp，Git忽略，不上传整个目录 |

校准A01T前40个干净trial；回放A01E前24个干净trial；cue+0.5至2.5秒、501点、μV、C3/Cz/C4。2a完整原始GDF、说明PDF及完整EOG缓存均未提交或上传。单独部署的最小demo压缩包约319KiB，带来源manifest/checksum。

EOG演示从用户提供的2b缓存选48个真实250点片段，两个真实眨眼样本安排在6–8秒，构成明确披露的离线配对场景。**不是同一受试者同步采集，不是原始连续EOG记录。** 自动伪标签参与最终模型训练，未报告独立准确率。2a原模型训练清单不全，T/E物理分离只证明本次校准与回放不混用，不等于独立泛化验证。

## 服务器与服务

Ubuntu24.04，Python3.12.3，MySQL8.0.46，Nginx1.24.0。服务部署在 `/opt/als-bci/current`，指向 `/opt/als-bci/releases/` 中已验证版本。

EEG环境 `/opt/als-bci/venv`：NumPy2.2.6 / SciPy1.15.3 / sklearn1.6.1 / MNE1.9.0。
EOG环境 `/opt/als-bci/eog-venv`：NumPy2.2.6 / SciPy1.15.3 / sklearn1.9.1 / MNE1.9.0 / joblib1.6.0。
前端在Windows使用Node和Next16.3.1构建静态out，生产无需Node进程。

| 服务 | 监听地址/端口 | 验收状态 |
|---|---|---|
| als-bci.service | 127.0.0.1:8000 | active、enabled、崩溃自动重启 |
| nginx.service | 0.0.0.0:80、0.0.0.0:9443 / [::]:80、[::]:9443 | active、enabled；未监听443 |
| mysql.service | 127.0.0.1:3306 / 33060 | active、enabled |
| ssh.service | :22 | 可用 |

UFW active，incoming默认deny；保留原有22/80/443规则，并仅为本项目新增9443。安全组需同步放行TCP 9443；没有停止或覆盖服务器上的其他服务。FastAPI、MySQL仍只绑定127.0.0.1。Certbot 5.8.0公网IP短期证书到期前自动续期，systemd定时器每6小时检查并部署后重载Nginx；`certbot renew --dry-run --run-deploy-hooks` 已模拟成功。Snap自带重复定时器已关闭，避免与项目定时器并行续期。

## 验证结果

本地：46项后端测试通过，覆盖MySQL、四角色权限/隔离、EA一致性、integration预处理一致性、有标签个人模型保存重载、真实EOG双峰确认与去重、漏数据拒绝、产物篡改、低置信度/不稳定/超时/急停、网关ACK/延迟/丢包/离线/失败、告警与审计，以及Reset后安全配置保留、公开/管理员健康接口权限和推送流。仅Starlette测试工具有一条弃用警告。
前端：eslint通过、tsc --noEmit通过、Next生产构建通过。浏览器完成用户创建、校准、加载Profile、真实回放，持久记录显示RIGHT / CONFIRM / ACK。

S3软件回归再次确认：3ch63.5417%、22ch82.9861%，288条，重复概率逐值一致；最近本机批量计算约76.9ms/449.3ms。S3参与训练，此数据不是独立泛化或临床指标。71.3%、53.6%、60.4%、99.95%均未用于正式性能宣传。

生产HTTPS闭环验收通过（服务器本机回环访问）：四角色登录和RBAC、Secure Cookie、MySQL/模型/文件健康、40条校准、真实EEG预测、真实EOG自动确认、SIMULATED ACK、DEVICE_OFFLINE拒绝、照护角色告警确认、审计记录、急停锁定及拒绝重放。告警确认写入处理人、处理时间和处理结果，本次端到端响应时间为0.098秒。公开存活接口返回最小状态，管理员详情接口可读取内部健康信息。会话数据通过WebSocket推送，推理在线程中运行并由Semaphore限制并发。外网验收待安全组开放9443后复测。
前三EEG窗实际端到端计算为6.918 / 4.949 / 4.654ms；预处理2.194 / 2.292 / 2.143ms；模型推理0.246 / 0.261 / 0.255ms。计时使用perf_counter，不含采样等待、网络和最终DB提交，不作硬件性能承诺。

服务器已实际重启，boot_id从84c27140-7f03-4579-96ca-dcb7e226bcc6变为baf22ef5-1439-437b-a6cc-a834dc43bf5a；三服务自动恢复、health=ok、保存Profile重载通过；旧运动会话不自动恢复。
外网HTTP及协议探测：80可用，3306/8000/33060应用不可访问。当前本机网络代理会使裸TCP connect产生误报，因此同时核对协议响应、服务器ss监听和UFW规则。
`.env`与backend/.env返回403；私钥路径、docs、openapi.json、temp、runtime返回404；未登录users返回401。密钥仅留在用户指定本机位置。

## Git与发布

仓库：https://github.com/robot999666/als-bci-web，分支main。
项目说明和部署口径已同步至GitHub `main`；生产代码发布版本为`3695446a127bca8d967cd54d6b9ac04504c61e9b`，记录于 `/opt/als-bci/current/RELEASE_COMMIT`。公网安全组规则尚未添加，外网验收因此待完成。
发布包基于Git已提交文件和本地静态构建，排除temp/runtime/.env/.pem/完整EOG缓存/原始GDF。用户产物与代码目录分离。

## 运维与排障

```bash
sudo systemctl start als-bci nginx mysql
sudo systemctl stop als-bci
sudo systemctl restart als-bci
sudo systemctl status als-bci nginx mysql --no-pager
sudo journalctl -u als-bci -n 100 --no-pager
sudo tail -n 100 /var/log/nginx/access.log  # 前端请求日志
sudo tail -n 100 /var/log/nginx/error.log
sudo systemctl status mysql --no-pager
sudo tail -n 100 /var/log/mysql/error.log
curl -fsS http://127.0.0.1/api/v1/health
sudo ss -lntp
sudo ufw status
```

公网网站打不开先查腾讯云安全组 TCP 9443，再查Nginx监听、UFW和静态资源；502查后端启动及loopback8000；FastAPI起不来查env、WorkingDirectory、迁移、Python与EOG环境；模型失败查checksum/依赖和EOG_PYTHON；MySQL失败查本地服务、账号和DATABASE_URL；校准失败查NPZ维度/250Hz/μV/非有限值/样本量/写权限；断流查WebSocket、Secure Cookie、Origin和会话状态；设备离线在模拟器切换ACK并查告警，急停需显式重置；磁盘满查df与产物保留策略；内存高查会话数量、文件大小与进程RSS。完整说明见operations.md。

## 项目边界

真实：EEG/EOG模型计算、无标签EA校准、有标签个人分类器训练、FastAPI、MySQL、权限、安全逻辑、计算耗时、监控与审计。
模拟：实体轮椅、护理床、紧急呼叫、智能家居及网关网络场景/ACK。
未来：EEG/EOG真实采集、同步多模态评测、硬件适配、真实照护授权关系与独立临床评估。软件不提供医疗诊断、治疗或ALS临床有效性结论。
