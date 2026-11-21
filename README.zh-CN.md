# Codex 桌面端恢复 `/` 调用技能补丁

本补丁用于在 macOS 版 Codex 桌面端（`ChatGPT.app`，已实测版本 `26.1117.31558`）中恢复通过 `/` 斜杠菜单搜索并调用全部已启用技能，同时保留原有内置斜杠命令与 `$` 技能选择器。

## 效果说明

应用补丁并重启应用后，输入框具备以下能力。

- 在 Codex 工作区输入框键入 `/` 时，斜杠菜单会在内置命令下方展示 `Skills` 分组，列出当前工作区全部已启用技能。
- 键入 `/技能名`（支持显示名与原始名称）即可实时过滤，按回车或点击候选项会自动把 `/xxx` 替换为对应的 `$技能名` 技能标签。
- 通用对话输入框与云端浏览器技能列表同步支持 `/` 触发与行内替换。
- 脚本采用副本构建与目录原子替换方式，运行前会自动克隆备份原始官方签名应用，随时可以一键还原。

## 环境要求

- macOS（Apple Silicon），已安装 Codex 桌面端（默认路径 `/Applications/ChatGPT.app`，脚本也会自动检查 `/Applications/Codex.app`）。
- 系统自带 `python3` 与 `codesign`（如尚未安装命令行工具，可先运行 `xcode-select --install`）。
- 本机安装 `node` 时会自动对修改后的前端脚本执行 `node --check` 语法校验。

## 快速开始

打开终端，进入本目录后执行以下命令。

### 1. 检查当前应用状态

```bash
python3 codex-slash-skills-patch.py status
```

### 2. 预演校验（只读检查，无文件改动）

```bash
python3 codex-slash-skills-patch.py apply --dry-run
```

### 3. 备份并应用补丁

```bash
python3 codex-slash-skills-patch.py apply
```

执行完成后，**完全退出 Codex 桌面端（`⌘Q`）再重新打开**即可生效。

### 4. 一键恢复官方原版

```bash
python3 codex-slash-skills-patch.py restore
```

还原完成后同样需要退出（`⌘Q`）并重新打开应用。

## 常用参数

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `--app` | `/Applications/ChatGPT.app` | 指定目标桌面端 `.app` 路径 |
| `--backup-dir` | `~/.codex-slash-patch/backups` | 指定原版应用备份目录 |
| `--sign` | `auto` | 指定重签证书身份，支持 `auto`、`-`（临时签名）或指定证书名与 SHA-1 指纹 |
| `--dry-run` | 关闭 | 仅用于 `apply`，匹配目标代码块并做语法检查 |
| `--backup` | 自动匹配同版本备份 | 仅用于 `restore`，显式指定要恢复的备份 `.app` 路径 |

### 签名策略说明

- `--sign auto` 会优先查找本机钥匙串中已有的 `Apple Development` 或 `Developer ID Application` 证书，未找到时自动回退到本地临时签名（`-`）。
- 如果希望强制使用本地临时签名，可运行以下命令。

```bash
python3 codex-slash-skills-patch.py apply --sign -
```

## 补丁修改内容

脚本会在临时副本中完成以下四步操作，校验通过后再原子替换目标应用。

1. **Codex 工作区输入框（动态定位包含 `composer.planSkillSlashCommand.title` 的异步模块）**
   新增 `id_slash_skills` 组件，读取当前工作区全部已启用技能并注册至斜杠命令表（`triggers: ["/"]`、`group: "Skills"`），同时配置弹窗点击与行内 `/xxx` 替换回调。
2. **通用对话与浏览器技能模块**
   为已有技能注册逻辑补充 `/` 触发符、原始名称搜索别名与 `onSelectFromInlineSlash` 行内替换回调。
3. **归档完整性更新**
   将修改后的 3 个脚本追加写入 `Contents/Resources/app.asar`，更新对应文件与归档头的 SHA-256 校验值，同步写入 `Contents/Info.plist`，并关闭 `Codex Framework` 内嵌的 ASAR 强校验开关位。
4. **本地重签与校验**
   为 8 个辅助进程、`Codex Framework.framework` 及主程序 `.app` 统一重签，并通过 `codesign --verify --verbose=2` 校验后原子替换。

## 注意事项

- **首次重启钥匙串弹窗**
  由于应用签名身份变更，重启后 macOS 可能会弹出访问 `Codex Safe Storage` 钥匙串的确认框。点击「始终允许」即可继续沿用原有登录态。使用本机开发者证书签名时该授权会持续保留。
- **受限系统权限移除**
  本地重签会移除仅限官方团队签发的推送通知、通用链接及官方应用组权限，核心对话、本地工作区、技能与插件功能均正常可用。
- **版本更新后处理**
  当 Codex 通过官方自动更新升级到新版本后，新安装包会覆盖本补丁。升级后可先运行 `python3 codex-slash-skills-patch.py apply --dry-run` 检查新版本前端代码结构是否兼容，如结构已变更则需更新匹配片段。
- **安全备份机制**
  首次对某版本执行 `apply` 时，脚本会在 `~/.codex-slash-patch/backups/ChatGPT-<版本号>-orig.app` 创建 APFS 写时复制克隆备份（几乎不占额外磁盘空间），重复运行 `apply` 也会保留该原始备份。
