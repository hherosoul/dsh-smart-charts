# dsh-smart-charts

DeepSeek Harness 的 Smart Charts skill 插件：把数据文件（CSV / Excel / JSON）转换为交互式 ECharts HTML，支持 21 种图表类型、多文件合并、LLM 数据转换代码（沙箱执行）。

这是同一个源码的两个分发渠道：

- **GitHub 直装**（纯 TS 源码，需 allowBuilds）
- **npm 发布**（预编译 `lib/`，免 allowBuilds）

## 安装

### 渠道 A：GitHub 直装

```bash
dsh plugin --profile web add github:你/dsh-smart-charts
```

首次安装会因为 pnpm≥10 拒绝运行 git 依赖的 `prepare` 构建脚本而失败。按 pnpm 打印的提示，把**精确包名**写进 profile 的 `pnpm-workspace.yaml`（默认为 `~/.dsh/profiles/web/pnpm-workspace.yaml`）：

```yaml
allowBuilds:
  dsh-smart-charts: true
```

然后重新安装：

```bash
dsh plugin --profile web add github:你/dsh-smart-charts
```

> 放行 `allowBuilds` 等于授权该包在安装阶段执行代码，请只对你信任的源码放行，并建议固定 commit：`github:你/dsh-smart-charts#<sha>`。

### 渠道 B：npm 发布

```bash
pnpm install && pnpm build
pnpm publish
```

用户安装预编译产物，无需任何构建权限：

```bash
dsh plugin --profile web add dsh-smart-charts
```

## 验证

```bash
dsh --profile web --dump-config
```

看到 `# == dsh-smart-charts` 一层即加载成功。

## 使用

装好后，在会话里对 agent 说「分析这个 CSV 并生成柱状图」即可触发。skill 首次运行前，agent 会按 `SKILL.md` 的指引安装 Python 依赖：

```bash
pip install -r requirements.txt --require-hashes
```

## 目录结构

```
dsh/
├── package.json         # dsh.bundle.patch 声明
├── cordis.patch.yml     # insert 插件行
├── tsconfig.json
├── src/index.ts         # 唯一入口：mount dsh-skill-filesystem
└── skills/smart-charts/ # skill 本体（SKILL.md + scripts + references + assets）
```

## License

MIT
