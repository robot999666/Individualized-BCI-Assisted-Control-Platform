"""演示：四分类的两种使用方式（校准 / 冷启动）。

用法：python demo.py

演示内容：
  1. 校准模式：加载 S3 数据，划分训练/测试，fit 训练，报告测试准确率。
  2. 冷启动模式：加载预训练模型，对 S3 数据分类，报告准确率。
  3. 两种模式都同时演示 22 通道和 3 通道。
"""
import os
import numpy as np

from model import FBCSPModel, ColdStartModel, CLASS_NAMES, C3CZ_C4
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
MODEL_DIR = os.path.join(HERE, "models")


def load_data(name):
    d = np.load(os.path.join(DATA_DIR, name))
    return d["X"], d["y"]


def report(pred, y, tag):
    acc = accuracy_score(y, pred)
    print(f"  {tag}: 准确率 {acc*100:.2f}%（{len(y)} 个样本）")


def main():
    print("=" * 60)
    print("四分类模型演示（左转/右转/直行/停止）")
    print("=" * 60)

    for ch_name, key in [("22通道", "22ch"), ("3通道", "3ch")]:
        print(f"\n=== {ch_name} ===")
        X, y = load_data(f"S3_{key}.npz")

        # ---- 方式1：校准模式 ----
        print("  [方式1 校准模式] 用 S3 数据 80% 训练、20% 测试：")
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=42)
        m = FBCSPModel().fit(X_tr, y_tr)
        report(m.predict(X_te), y_te, "FBCSP 校准")

        # ---- 方式2：冷启动模式 ----
        print("  [方式2 冷启动模式] 加载预训练模型，直接分类全部 S3 数据：")
        cs = ColdStartModel.load(os.path.join(MODEL_DIR, f"coldstart_{key}.pkl"))
        report(cs.predict(X), y, "EA+FBCSP 冷启动")

        # 打印几个示例预测
        print("  示例预测（前5个样本）:")
        for i in range(5):
            print(f"    样本{i}: 真实={CLASS_NAMES[y[i]]} "
                  f"校准预测={CLASS_NAMES[m.predict(X[i:i+1])[0]]} "
                  f"冷启动预测={CLASS_NAMES[cs.predict(X[i:i+1])[0]]}")

    print("\n" + "=" * 60)
    print("演示完成。")
    print("实际使用：")
    print("  校准模式：m = FBCSPModel().fit(你的校准数据X, 标签y); m.predict(新数据)")
    print("  冷启动模式：m = ColdStartModel.load('models/coldstart_22ch.pkl'); m.predict(新数据)")
    print("注：本 demo 的冷启动准确率偏高，因为 S3 参与了冷启动模型的训练；")
    print("    此结果不代表全新用户表现；历史准确率缺少可复核独立实验记录。")
    print("=" * 60)


if __name__ == "__main__":
    main()
