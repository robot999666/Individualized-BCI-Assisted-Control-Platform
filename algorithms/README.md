# 算法目录

- `bci_4class/`：原 EEG FBCSP/LDA 权重与 S3 软件回归。
- `system_integration/`：EEG 全局滤波、个体校准、EOG SVM 和参考状态机。产品使用后端统一安全控制层。
- `eog_blink/`：用户提供的 EOG 训练/特征/数据构建来源。`eog_dataset.npz` 仅本机，Git忽略。

EEG使用sklearn1.6.1；EOG模型由sklearn1.9.1序列化，部署在独立子进程。训练数据不是独立评测集。完整运行、真实与模拟边界见根README。
