# 前端

Next.js 16.3.1 / React19 / TypeScript / Tailwind4，原项目内改造，静态export部署。
`npm ci` → `npm run lint` → `npx tsc --noEmit` → `npm run build`，输出out/。
生产同源`/api/v1`；本地可用根目录scripts/preview.py代理。npm run dev热更新时可设置NEXT_PUBLIC_API_BASE_URL=http://localhost:8000（仅公开API地址，不允许密钥）。
首页/、控制工作台/lab/、运行中心/operations/。EOG使用真实SVM模型并标记REAL MODEL，设备标记SIMULATED。当前工作台真实EEG回放按后端采样时钟，不调用旧useExampleAnimation。
