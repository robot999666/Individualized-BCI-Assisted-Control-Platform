# Legacy container entry points
原compose仅部署无数据库后端，不能启动新平台。当前受支持路径为README说明的本地MySQL + 原生Python，以及deploy/的Nginx + systemd生产部署。后续若新增容器部署，需要完整MySQL、迁移、artifact卷、秘密注入与健康验证，不能复用旧compose。
