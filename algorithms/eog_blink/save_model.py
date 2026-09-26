from pathlib import Path
"""
save_model.py - 用全部数据训练最终模型并保存，供部署使用。
"""
import numpy as np
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import joblib
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from eog_detect import SFREQ
from train import extract_features


# 加载数据
data = np.load(str(Path(__file__).resolve().parent / 'eog_dataset.npz'))
X, y = data['X'], data['y']
print(f"训练数据: {len(X)} 样本")

# 提取特征
X_feat = np.array([extract_features(w) for w in X])
print(f"特征维度: {X_feat.shape[1]}")

# 训练最终模型（全部数据）
clf = Pipeline([
    ('scaler', StandardScaler()),
    ('svm', SVC(C=10.0, kernel='rbf', gamma='scale', probability=True))
])
clf.fit(X_feat, y)

# 保存
model_path = str(Path(__file__).resolve().parent / 'blink_detector.pkl')
joblib.dump(clf, model_path)
print(f"模型已保存: {model_path}")
print(f"模型大小: {os.path.getsize(model_path)/1024:.1f} KB")
