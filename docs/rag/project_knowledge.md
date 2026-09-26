# 项目知识

当前平台的准确说明见根README、docs/architecture.md、docs/data-protocol.md。
EEG使用真实EA+FBCSP+LDA；个体化产物是校准集EA逆平方根矩阵，不是重新训练的专属分类器。
EOG是真实SVM眨眼模型，Demo为明确披露的2a/2b离线配对真实片段；轮椅、护理床、紧急呼叫和智能家居是Simulator，没有真实硬件接入或ALS临床验证。
T/E分离只保证此次EA校准和回放不混用；原模型训练会话清单未知。71.3%、53.6%、60.4%缺少足够可复核实验依据，不得宣传。S3准确率只用于软件回归。
