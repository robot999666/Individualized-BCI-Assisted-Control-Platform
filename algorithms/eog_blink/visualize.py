from pathlib import Path
"""可视化：眨眼vs不眨眼信号对比 + 特征分析。"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

data = np.load(str(Path(__file__).resolve().parent / 'eog_dataset.npz'))
X, y, subj_ids = data['X'], data['y'], data['subj_ids']
sfreq = int(data['sfreq'])

# 分离眨眼和非眨眼样本
blink_idx = np.where(y == 1)[0]
nonblink_idx = np.where(y == 0)[0]

# 随机选几个样本画
np.random.seed(42)
blink_sample = np.random.choice(blink_idx, 5, replace=False)
nonblink_sample = np.random.choice(nonblink_idx, 5, replace=False)

t = np.arange(X.shape[1]) / sfreq - 0.5  # -0.5s to +0.5s

fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

# 眨眼样本
for i, idx in enumerate(blink_sample):
    axes[0].plot(t, X[idx], alpha=0.7, label=f'blink #{i+1} (subj {subj_ids[idx]})')
axes[0].set_title('EOG:ch02 - Blink windows (1s, centered at peak)')
axes[0].set_ylabel('Amplitude (uV)')
axes[0].legend(fontsize=8)
axes[0].axhline(y=0, color='k', linewidth=0.5)
axes[0].axvline(x=0, color='r', linestyle='--', alpha=0.5, label='peak')

# 非眨眼样本
for i, idx in enumerate(nonblink_sample):
    axes[1].plot(t, X[idx], alpha=0.7, label=f'non-blink #{i+1} (subj {subj_ids[idx]})')
axes[1].set_title('EOG:ch02 - Non-blink windows (random flat segments)')
axes[1].set_ylabel('Amplitude (uV)')
axes[1].set_xlabel('Time relative to window center (s)')
axes[1].legend(fontsize=8)
axes[1].axhline(y=0, color='k', linewidth=0.5)

plt.tight_layout()
plt.savefig(str(Path(__file__).resolve().parent / 'blink_vs_nonblink.png'), dpi=150)
print("已保存: blink_vs_nonblink.png")

# 画所有眨眼样本的平均波形±标准差
fig, ax = plt.subplots(1, 1, figsize=(10, 5))
blink_mean = X[blink_idx].mean(axis=0)
blink_std = X[blink_idx].std(axis=0)
nonblink_mean = X[nonblink_idx].mean(axis=0)
nonblink_std = X[nonblink_idx].std(axis=0)

ax.plot(t, blink_mean, 'b-', linewidth=2, label='Blink (mean)')
ax.fill_between(t, blink_mean - blink_std, blink_mean + blink_std, alpha=0.3, color='b')
ax.plot(t, nonblink_mean, 'r-', linewidth=2, label='Non-blink (mean)')
ax.fill_between(t, nonblink_mean - nonblink_std, nonblink_mean + nonblink_std, alpha=0.3, color='r')
ax.axvline(x=0, color='k', linestyle='--', alpha=0.5)
ax.set_xlabel('Time (s)')
ax.set_ylabel('Amplitude (uV)')
ax.set_title('Average EOG waveform: Blink vs Non-blink (all subjects)')
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(str(Path(__file__).resolve().parent / 'average_waveform.png'), dpi=150)
print("已保存: average_waveform.png")

# 统计
print(f"\n眨眼样本平均峰值: {X[blink_idx].max(axis=1).mean():.1f} uV")
print(f"非眨眼样本最大幅度: {np.abs(X[nonblink_idx]).max(axis=1).mean():.1f} uV")
print(f"眨眼样本RMS: {np.sqrt((X[blink_idx]**2).mean(axis=1)).mean():.1f} uV")
print(f"非眨眼样本RMS: {np.sqrt((X[nonblink_idx]**2).mean(axis=1)).mean():.1f} uV")
