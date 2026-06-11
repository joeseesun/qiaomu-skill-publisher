---
name: skill-publisher
description: |
  一键发布 agent skill 到 GitHub，自动验证 SKILL.md、生成或检查更吸引人的 README、区分 skill name 与 GitHub repo name、创建或更新仓库、推送并通过 npx skills 真实安装验证。当用户说"发布这个skill"、"publish skill"、"把skill发到GitHub"、"分享这个skill"、"/publish-skill"时触发。支持发布当前目录或指定路径的 skill。
---

# Skill Publisher

一键将 agent skill 发布到 GitHub，自动完成验证、README 质量检查、补全、推送和真实安装验证。

## 前置条件

- `gh` CLI 已安装且已登录（`gh auth status`）
- Skill 目录包含有效的 `SKILL.md`（含 YAML frontmatter `name` + `description`）
- 优先使用 `/Users/joe/.agents/skills/<name>` 作为正式源目录；`.codex` / `.claude` 可作为兼容入口。

## 发布流程

当用户要求发布 skill 时，运行发布脚本：

```bash
python3 ~/.agents/skills/qiaomu-skill-publisher/scripts/publish_skill.py <skill_dir>
```

### 确定 skill 目录

- 如果用户说"发布这个 skill"且当前在某个 skill 目录 → 用当前目录
- 如果用户指定了 skill 名称 → 优先在 `~/.agents/skills/` 下查找
- 如果不确定 → 问用户要发布哪个 skill

### 脚本自动完成的步骤

1. **验证** SKILL.md 的 YAML frontmatter（name + description）
2. **检查** gh CLI 就绪状态
3. **创建** LICENSE（MIT，如果缺少）
4. **生成或检查** README.md：生成时不再写 TODO 模板；已存在时拦截明显占位符
5. **识别仓库名**：优先使用当前 `origin` 仓库名，避免把 `skill-publisher` 误发到错误 repo
6. **初始化** git（如果需要）
7. **创建或更新** GitHub 公开仓库并推送
8. **验证** `npx skills add --list` 可发现，并在临时目录真实安装

### 参数选项

| 参数 | 说明 |
|------|------|
| `--private` | 创建私有仓库（默认公开） |
| `--dry-run` | 仅检查，不实际发布 |
| `--skip-verify` | 跳过 npx skills 验证 |
| `--github-user USER` | 指定 GitHub 用户名（默认自动获取） |
| `--repo-name NAME` | 指定 GitHub 仓库名；默认优先使用当前 `origin` 仓库名，否则使用 skill name |
| `--no-symlink` | 跳过同步 `~/.agents/skills/` 实体目录 |

### 自动同步 ~/.agents/skills/ 实体目录

发布成功后，脚本可自动把 skill 同步到 `~/.agents/skills/<name>` 作为实体目录。

这个目录是通用 Agent Skills 标准目录，以下工具会自动读取：
OpenCode、Codex CLI、Cursor、Gemini CLI、GitHub Copilot、Amp、Cline、Warp 等。

一次发布，多工具共享，无需重复配置。

如果当前发布源已经是 `~/.agents/skills/<name>`，脚本会跳过同步，避免误删自己的源目录。若 skill name 与 repo name 不一致，或者你不想产生本地副本，发布时加 `--no-symlink`。

### ⚠️ SKILL.md YAML 安全规则（发布前必查）

`npx skills` 使用严格 YAML 解析器，以下写法会导致安装失败（报 "No valid skills found"）：

| ❌ 错误写法 | ✅ 正确写法 |
|-----------|-----------|
| `description: 含有 "引号" 的文字` | 改用 `\|` 块标量（见下方） |
| `description: 含单引号'的文字` | 改用 `\|` 块标量 |
| `description: 含冒号: 的文字` | 改用 `\|` 块标量 |

**最安全的 description 写法**：
```yaml
description: |
  描述放这里，可以随意包含 "双引号"、'单引号'、冒号: 等特殊字符
  触发词: 用户说...时触发
```

脚本已内置 YAML 严格校验（pyyaml），会在发布前捕获这类错误并给出修复提示。

### 更新已发布的 skill

对已有 GitHub 仓库的 skill 再次运行同一命令，脚本会检测到仓库已存在，自动 commit + push 更新。

## 使用示例

```
用户：发布 yt-search-download 这个 skill
执行：python3 ~/.agents/skills/qiaomu-skill-publisher/scripts/publish_skill.py ~/.agents/skills/yt-search-download

用户：把当前 skill 发到 GitHub
执行：python3 ~/.agents/skills/qiaomu-skill-publisher/scripts/publish_skill.py .

用户：先检查一下能不能发布
执行：python3 ~/.agents/skills/qiaomu-skill-publisher/scripts/publish_skill.py <dir> --dry-run

用户：当前 skill name 与仓库名不同，明确发布到 qiaomu-skill-publisher
执行：python3 ~/.agents/skills/qiaomu-skill-publisher/scripts/publish_skill.py <dir> --repo-name qiaomu-skill-publisher
```

## README 质量检查（发布前必做）

**脚本只在 README 不存在时自动生成一个发布页模板**。发布前，必须人工检查/撰写 README，确保它对陌生用户有价值。

最新标准：自动生成的 README 不应包含 `TODO`、`特性 1`、`[问题 1]` 这类占位符；已有 README 如果包含明显占位内容，发布会失败。

### README 必须包含的 7 个要素

1. **价值主张（Hook）**：第一段就让用户明白"这能解决我什么问题"，用具体场景描述，避免抽象描述
2. **首屏证据**：产品截图、输出样例、真实生成物或短 Demo 必须出现在 README 第一屏附近；Web 项目优先放完整产品截图
3. **动态可信信号**：GitHub stars、forks、issues、last commit、license、deploy/install 按钮等徽章要放在顶部；适合公开传播的项目加 Star History
4. **前置条件清单（checkbox 格式）**：用 `- [ ]` 列出所有依赖，让用户逐一确认。每条都要写清楚怎么装，不能只说"需要 xxx"
5. **完整安装步骤**：编号步骤，细到小白能跟着做。每步都提供验证命令（如 `--version`）
6. **自然语言使用示例**：展示 2-3 个用户真实会说的句子，让人一眼看懂怎么触发
7. **致谢原作者**：如果 skill 基于第三方工具/库，必须注明原项目链接和作者
8. **必要的风险/限制说明**：写操作、账号相关、费用相关的风险需明确告知
9. **常见问题/Troubleshooting**：至少列出 3 个常见报错和解决方法，降低用户放弃率

### Web 项目 README 发布标准

参考 `nexu-io/open-design` 这类高转化 README，Web 项目不能只写安装命令，必须像产品发布页一样给用户一个可判断的首屏。

**首屏顺序建议**：

1. 项目名 + 一句话 Hook
2. 主要 CTA：`Deploy with Vercel` / Live Demo / Install，按钮要能直接用真实仓库 URL
3. GitHub 动态徽章：stars、forks、issues、last commit、license、build 状态（如果有）
4. 产品截图：`docs/assets/product-screenshot.png`，alt 写清楚截图内容
5. 3-6 个核心功能点，不写泛泛的"高效/现代/优雅"

**Web 项目必须优先补齐**：

- `docs/assets/product-screenshot.png`：首屏或核心工作流截图
- `docs/assets/` 下的样例输出：如图片生成网站放 3-6 个代表性生成图
- README 中的样例表格：展示输入、输出、关键差异或使用场景
- `scripts/capture-screenshots.*` 或等价命令：能本地启动网站后自动刷新 README 截图
- 部署说明：Vercel/Netlify/Docker 等入口必须使用真实仓库 URL 和最少步骤

**推荐 README 模块**：

```markdown
# Project Name

> 一句话说明用户会得到什么。

[Deploy with Vercel] [Live Demo] [Stars] [Forks] [Last commit] [License]

<img src="docs/assets/product-screenshot.png" alt="..." />

## 为什么值得用
## 样例输出
## 一键部署
## 本地开发
## 自动更新截图
## 数据/生成流程
## Star History
## Troubleshooting
```

**自动截图要求**：

- 有前端 UI 的项目，优先用 Playwright/Puppeteer 生成 README 截图，不手工截屏
- 截图脚本应允许通过环境变量指定 URL，例如 `SCREENSHOT_URL=http://127.0.0.1:3000 npm run capture:screenshots`
- 截图文件放进 `docs/assets/`，README 使用相对路径引用
- 截图脚本是发布资产生成，不等同于功能验收；除非用户要求，否则不要把它包装成完整 E2E 测试

### 语言原则

**默认写中英双语 README，但中文在前。** 中文用户是主要受众，英文是给国际用户的补充。

**双语结构（中文在前）**：
```markdown
# skill-name

> 中文一行价值主张
> One-line English hook

**[中文](#中文) | [English](#english)**

---

<a name="中文"></a>
## 中文
[完整中文内容]

---

<a name="english"></a>
## English
[完整英文内容]
```

### README 吸引力写法（最重要）

**目标不是"让人看懂"，而是"让人想装"。** 每一段都要回答用户心里那个问题：这和我有什么关系？

**高吸引力 README 的结构**：

1. **第一句话抓痛点**：描述用户现在的痛，不是你的方案。一句话，精准，不废话。
   - ✅ "你问 AI 一个难问题，它给你一个答案，一个角度。"
   - ❌ "这是一个多视角推理工具，基于 arXiv:2605.02396..."

2. **一句话翻转**：立刻给出"用了这个之后"的对比。
   - ✅ "HeavySkill 让 K 个独立 AI 并行思考同一个问题，然后让 Codex 主持讨论，综合出一个比任何单一答案都更扎实的结论。"

3. **具体输出预览**：告诉用户他会得到什么。不要说"生成报告"，要说"生成一个 Medium 杂志风格的 HTML 报告，有每个视角的推理过程，有讨论中发现的盲点，有一个加粗的最终判断"。

4. **首屏截图或样例**：让用户先看到真实结果，再决定是否继续读。Web 项目放产品截图，生成类项目放代表性输出，CLI/Skill 放实际终端输出或生成文档片段。

5. **一行安装**：最低摩擦。不要说"先 clone 再 cd 再 npm install"。
   ```bash
   npx skills add username/skill-name
   ```

6. **自然语言触发示例**：让用户知道怎么用。不是命令，是他会真实说出的话。
   - "讨论一下 React vs Vue"
   - "think harder: 微服务还是单体架构"

7. **前置条件清单（checkbox 格式）**：放在安装之后，不要放开头吓人。用 `- [ ]` 格式让用户逐项确认。

8. **动态项目状态**：公开 GitHub 项目顶部放 stars/forks/issues/last commit/license 徽章；有增长叙事时补 Star History。

9. **Troubleshooting 表格**：至少 3 条，解决用户放弃的最后一公里。

**让人想装的写作要领**：
- 短句。每个 idea 一行，不要堆在同一段。
- 具体胜于抽象。"36k+ GitHub Stars、900 万/月 npm 下载" 比 "流行的开源项目" 有说服力。
- 让用户想象"用了之后"的场景，而不是描述技术实现。
- 风险或限制放最后，不要一开始就说"注意：这个需要..."。

### README 小白友好度检查

发布前逐项核对：

- [ ] 第一句话是痛点，不是功能描述
- [ ] 有"用了之后"的具体场景描述
- [ ] 安装命令一行搞定，放在显眼位置
- [ ] Web 项目有首屏产品截图，生成类项目有代表性输出样例
- [ ] GitHub 项目顶部有动态徽章，公开项目有 Star History 或 repo 活跃度入口
- [ ] Web 项目有自动截图命令，截图在 `docs/assets/`
- [ ] 前置条件用 checkbox 格式，每条说明怎么安装
- [ ] 使用示例是用户真实会说的话，不是技术命令
- [ ] 有 Troubleshooting 表格（问题 → 解决方法）

### README 常见坏味道（避免）

- ❌ 直接把 SKILL.md 的 AI 指令（Output Formatting Rules、Rule:...）放进 README
- ❌ 第一段全是技术描述，没有用户能感受到的价值
- ❌ "基于 arXiv:XXXX..." 开头 — 用户不在乎论文，在乎结果
- ❌ 前置要求放开头，吓跑用户
- ❌ 安装步骤超过 3 步（如果超过了，说明你没想清楚怎么简化）
- ❌ 没有 Troubleshooting，用户遇到问题只能自己摸索
- ❌ Web 项目没有截图，或者截图过期、无法复现
- ❌ Deploy 按钮仍指向 `your-org/your-repo` 这类占位 URL

### 发布工作流

```
1. 读取 SKILL.md，理解 skill 的功能和目标用户
2. 判断语言：默认中文，只在明确国际化需求时写双语
3. 检查 README.md 是否存在，若存在则评估吸引力（不只是完整度）
4. 若 README 不够吸引人，先重写再发布
5. README 确认后，再运行发布脚本
6. 如果当前仓库已有 `origin`，确认脚本使用的是 `origin` 仓库名；否则用 `--repo-name` 明确指定
7. 发布后必须验证 `npx skills add <user>/<repo> --list`，并尽量做临时目录真实安装
```

## 发布完成后

向用户展示：
- GitHub 仓库 URL
- 安装命令：`npx skills add <user>/<skill-name>`
- 验证结果
