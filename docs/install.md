# Aether 安装与分享

## npm 分享安装

推荐把 Aether 作为 npm 包分发。npm 包只是分发层，包内仍保留 Codex marketplace 结构。

发布后，用户可以运行：

```bash
npx aether-codex-plugin install
```

这个命令会显式执行安装动作：

- 将包内置 marketplace 复制到持久目录 `~/.aether/codex-marketplace/aether-codex-plugin`
- 注册包内置 Codex marketplace
- 初始化 `~/.aether/data`
- 写入 `~/.config/aether/config.json`
- 安装 `aether` CLI 到 `~/.local/bin/aether`

不会使用 npm `postinstall` 自动写用户目录。

如果只想查看 marketplace 根目录：

```bash
npx aether-codex-plugin marketplace-path
```

这个命令也会刷新持久 marketplace 目录，避免 Codex 指向 `npx` 临时目录。

## Codex Marketplace 手动安装

Aether 仓库本身是一个 Codex marketplace 根目录，入口文件是：

```text
.agents/plugins/marketplace.json
```

分享给其他用户时，优先分享完整仓库或发布包，而不是只分享 `plugins/aether` 目录。接收方拿到完整目录后运行：

```bash
codex plugin marketplace add <aether-marketplace-root>
```

其中 `<aether-marketplace-root>` 是包含 `.agents/plugins/marketplace.json` 的目录。安装后在 Codex 插件界面选择 Aether，并开启新的线程让技能重新加载。

如果 marketplace 已添加，更新本地目录后运行：

```bash
codex plugin marketplace upgrade aether
```

## npm 发布包

从仓库根目录运行：

```bash
plugins/aether/scripts/package-plugin.sh
```

输出：

```text
dist/aether-codex-plugin-<version>.tgz
```

发布到 npm 前先检查包内容：

```bash
npm pack --dry-run
```

发布：

```bash
npm publish
```

如果以后改成 scoped package，例如 `@your-scope/aether-codex-plugin`，首次公开发布需要使用 `npm publish --access public`。

## 本地开发 Cache 安装

从仓库根目录运行：

```bash
plugins/aether/scripts/install-local.sh
```

这个脚本会：

- 将 `plugins/aether` 同步到 `~/.codex/plugins/cache/aether/aether/<version>`
- 生成用户配置 `~/.aether/codex-plugin/config.json`
- 建立配置软链 `~/.config/aether/config.json`
- 安装命令软链 `~/.local/bin/aether`
- 初始化 `~/.aether/data`

这个方式会直接写入本机 Codex cache，适合当前机器快速联调；它不是推荐的插件分享入口。安装后重启 Codex，让插件技能重新加载。

## 命令行使用

安装后直接使用：

```bash
aether doctor
aether visual-asset list --summary
aether prompt compose --source-prompt "a lonely rainy neon city"
```

开发仓库根目录也保留 `src -> plugins/aether/src` 软链，因此本地调试仍可使用：

```bash
PYTHONPATH=src python -m aether_core.cli doctor
```

## 数据位置

用户配置：

```text
~/.config/aether/config.json -> ~/.aether/codex-plugin/config.json
```

用户数据：

```text
~/.aether/data/aether.sqlite
~/.aether/data/assets
~/.aether/data/cache
~/.aether/data/runs
```

插件 cache：

```text
~/.codex/plugins/cache/aether/aether/<version>
```
