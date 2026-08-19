# 示例数据与使用说明

本目录提供示例数据，帮助你快速体验 `smart-charts` skill。

## 示例数据

`sales_data.csv` — 2026 年第一季度销售数据，共 18 行、5 列：

| 列名 | 说明 |
|---|---|
| `month` | 月份（2026-01 ~ 2026-03） |
| `region` | 地区（华东 / 华南） |
| `product` | 产品（手机 / 电脑 / 配件） |
| `sales` | 销售额（元） |
| `profit` | 利润（元） |

## 如何使用

### 1. 把数据放到 workspace 目录

DSH 的 agent 只能访问 workspace（工作区）目录内的文件。请把 `sales_data.csv` 复制到你的 workspace 目录（即启动 `dsh` 时所在的目录，或在 UI「选择工作区」里添加的目录）。

### 2. 触发 skill

任选其一：

- **斜杠命令**：输入 `/smart-charts`
- **自然语言**：直接说「分析 sales_data.csv 生成图表」

### 3. 示例提示词

```text
用 smart-charts 分析 sales_data.csv：
1. 按产品统计总销售额，生成柱状图
2. 按月份展示销售额趋势，生成折线图
3. 各地区销售额占比，生成饼图
```

### 4. 查看结果

生成的交互式 HTML 会输出到 workspace 的 `output` 目录，用浏览器打开即可查看、缩放、悬停查看数据、另存为图片。

## 支持的图表类型

柱状图、折线图、饼图、散点图、面积图、雷达图、漏斗图、热力图、桑基图、词云等 21 种类型，详见 skill 内的 `references/REFERENCE.md`。
