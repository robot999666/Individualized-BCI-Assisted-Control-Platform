from pathlib import Path
"""
train.py - EOG眨眼二分类训练与评估
策略：按被试留一交叉验证（LOSO），避免数据泄露。
特征方案：手工特征（峰值、RMS、方差等）+ SVM分类器。
"""
import numpy as np
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, confusion_matrix, roc_auc_score)
from sklearn.pipeline import Pipeline
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from eog_detect import build_dataset, SFREQ


def extract_features(window):
    """
    从单个EOG窗口提取手工特征。
    window: (250,) 1秒的EOG信号（uV，已带通滤波）
    返回: 特征向量
    """
    feats = []

    # 1. 峰值特征
    peak = np.max(window)
    trough = np.min(window)
    mean = np.mean(window)
    feats.extend([peak, trough, peak - trough, mean])

    # 2. 能量/方差特征
    feats.append(np.var(window))           # 方差
    feats.append(np.sqrt(np.mean(window**2)))  # RMS
    feats.append(np.sum(np.abs(np.diff(window))))  # 总变差（平滑度）

    # 3. 波形形状特征
    # 峰值位置（眨眼峰值应在窗口中心附近）
    peak_pos = np.argmax(window)
    feats.append(peak_pos / len(window))   # 归一化峰值位置

    # 上升沿斜率（峰值前100ms的斜率）
    center = len(window) // 2
    pre = window[center-25:center]  # 峰值前100ms
    rise_slope = (window[center] - pre[0]) / (len(pre) / SFREQ)
    feats.append(rise_slope)

    # 下降沿斜率（峰值后100ms）
    post = window[center:center+25]
    fall_slope = (post[-1] - window[center]) / (len(post) / SFREQ)
    feats.append(fall_slope)

    # 4. 中心窗口能量占比（眨眼能量集中在中心）
    center_energy = np.sum(window[center-25:center+25]**2)
    total_energy = np.sum(window**2) + 1e-10
    feats.append(center_energy / total_energy)

    # 5. 过零率
    zero_cross = np.sum(np.diff(np.sign(window)) != 0)
    feats.append(zero_cross)

    # 6. 偏度和峰度
    from scipy.stats import skew, kurtosis
    feats.append(skew(window))
    feats.append(kurtosis(window))

    return np.array(feats)


def extract_all_features(X):
    """批量提取特征。"""
    return np.array([extract_features(w) for w in X])


def loso_cross_validation(X, y, subj_ids, C=1.0, kernel='rbf'):
    """
    留一被试交叉验证（Leave-One-Subject-Out）。
    每个fold：用8个被试训练，1个被试测试。
    """
    unique_subjects = np.unique(subj_ids)
    print(f"留一被试交叉验证，共{len(unique_subjects)}个被试: {unique_subjects}")
    print(f"SVM参数: C={C}, kernel={kernel}")
    print("-" * 70)

    all_y_true = []
    all_y_pred = []
    all_y_prob = []
    fold_accs = []

    for test_subj in unique_subjects:
        train_mask = subj_ids != test_subj
        test_mask = subj_ids == test_subj

        X_train, y_train = X[train_mask], y[train_mask]
        X_test, y_test = X[test_mask], y[test_mask]

        # 构建pipeline：标准化 + SVM
        clf = Pipeline([
            ('scaler', StandardScaler()),
            ('svm', SVC(C=C, kernel=kernel, gamma='scale',
                        probability=True, random_state=42))
        ])
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)
        y_prob = clf.predict_proba(X_test)[:, 1]

        acc = accuracy_score(y_test, y_pred)
        fold_accs.append(acc)
        all_y_true.extend(y_test)
        all_y_pred.extend(y_pred)
        all_y_prob.extend(y_prob)

        n_test = len(y_test)
        print(f"  被试{test_subj}: 测试样本{n_test}, Acc={acc:.4f}")

    # 汇总
    all_y_true = np.array(all_y_true)
    all_y_pred = np.array(all_y_pred)
    all_y_prob = np.array(all_y_prob)

    print("-" * 70)
    print(f"平均Accuracy: {np.mean(fold_accs):.4f} ± {np.std(fold_accs):.4f}")
    print(f"全局Accuracy:  {accuracy_score(all_y_true, all_y_pred):.4f}")
    print(f"Precision:     {precision_score(all_y_true, all_y_pred):.4f}")
    print(f"Recall:        {recall_score(all_y_true, all_y_pred):.4f}")
    print(f"F1 Score:      {f1_score(all_y_true, all_y_pred):.4f}")
    print(f"AUC:           {roc_auc_score(all_y_true, all_y_prob):.4f}")
    print(f"混淆矩阵:")
    cm = confusion_matrix(all_y_true, all_y_pred)
    print(f"  TN={cm[0,0]}, FP={cm[0,1]}")
    print(f"  FN={cm[1,0]}, TP={cm[1,1]}")

    return fold_accs, all_y_true, all_y_pred


if __name__ == "__main__":
    # 检查是否已有缓存数据集
    cache_path = str(Path(__file__).resolve().parent / 'eog_dataset.npz')
    if os.path.exists(cache_path):
        print(f"加载缓存数据集: {cache_path}")
        data = np.load(cache_path)
        X, y, subj_ids = data['X'], data['y'], data['subj_ids']
        print(f"  样本数: {len(X)}, 特征维度: {X.shape[1]}")
    else:
        print("未找到缓存，重新构建数据集...")
        X, y, subj_ids = build_dataset()
        np.savez_compressed(cache_path, X=X, y=y, subj_ids=subj_ids, sfreq=SFREQ)
        print(f"已缓存到 {cache_path}")

    # 提取手工特征
    print("\n提取手工特征...")
    X_feat = extract_all_features(X)
    print(f"特征维度: {X_feat.shape[1]}")

    # LOSO交叉验证
    print("\n" + "=" * 70)
    print("开始留一被试交叉验证")
    print("=" * 70)
    loso_cross_validation(X_feat, y, subj_ids, C=10.0, kernel='rbf')
