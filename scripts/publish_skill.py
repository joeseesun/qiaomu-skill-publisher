#!/usr/bin/env python3
"""
Skill Publisher — 检查并发布 Claude Code Skill 到 GitHub

用法:
  python3 publish_skill.py <skill_dir> [--github-user USER] [--public/--private] [--dry-run]

流程:
  1. 验证 SKILL.md (YAML frontmatter)
  2. 检查/创建 LICENSE
  3. 生成 README.md
  4. 初始化 git (如需)
  5. 创建 GitHub repo + push
  6. 验证 npx skills 可发现
"""

import os
import sys
import re
import subprocess
import argparse
import json
import datetime
import shutil
import tempfile


def run(cmd, capture=True, check=True, cwd=None):
    """Run a shell command and return stdout."""
    if isinstance(cmd, list):
        r = subprocess.run(cmd, capture_output=capture, text=True, cwd=cwd)
    else:
        r = subprocess.run(cmd, shell=True, capture_output=capture, text=True, cwd=cwd)
    if check and r.returncode != 0:
        return None
    return r.stdout.strip() if capture else ""


def check_prerequisites():
    """Check gh CLI is available and authenticated."""
    if not run("which gh"):
        print("[错误] 未找到 gh CLI。安装方式: brew install gh", file=sys.stderr)
        return False
    auth = run("gh auth status 2>&1", check=False)
    if auth is None or "not logged" in (auth or ""):
        print("[错误] gh 未登录。运行: gh auth login", file=sys.stderr)
        return False
    return True


def parse_yaml_frontmatter(skill_md_path):
    """Extract name and description from SKILL.md YAML frontmatter.

    Returns (name, desc, yaml_error). yaml_error is None if parsing succeeded.
    Uses pyyaml for strict validation (same parser family as npx skills CLI).
    Falls back to regex if pyyaml is unavailable.
    """
    with open(skill_md_path, "r") as f:
        content = f.read()
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return None, None, "找不到 YAML frontmatter（需要 --- ... --- 包裹）"
    yaml_block = m.group(1)

    try:
        import yaml
        try:
            data = yaml.safe_load(yaml_block)
        except yaml.YAMLError as e:
            err_line = str(e).split("\n")[0]
            return None, None, (
                f"YAML 语法错误: {err_line}\n"
                "   常见原因: description 含未转义的引号或特殊字符\n"
                "   修复方法: 改用 | 块标量格式:\n"
                "     description: |\n"
                "       描述文字，可随意包含 \"引号\"、'单引号'、冒号: 等"
            )
        if not isinstance(data, dict):
            return None, None, "frontmatter 解析结果不是 dict"
        name = data.get("name")
        desc = data.get("description")
        if isinstance(desc, str):
            desc = " ".join(desc.split())  # normalize whitespace
        return name, desc, None

    except ImportError:
        pass  # pyyaml not installed, fall back to regex

    # Regex fallback (less strict, may miss YAML errors)
    name_m = re.search(r"^name:\s*(.+)$", yaml_block, re.MULTILINE)
    name = name_m.group(1).strip().strip("'\"") if name_m else None
    desc = None
    desc_m = re.search(r"^description:\s*[|>]\s*\n((?:[ \t]+.+\n?)+)", yaml_block, re.MULTILINE)
    if desc_m:
        lines = desc_m.group(1).split("\n")
        desc = " ".join(line.strip() for line in lines if line.strip())
    else:
        desc_m = re.search(r"^description:\s*(.+)$", yaml_block, re.MULTILINE)
        if desc_m:
            desc = desc_m.group(1).strip().strip("'\"")
    return name, desc, None


def get_github_user():
    """Get current GitHub username."""
    return run("gh api user --jq '.login'")


def get_origin_repo(skill_dir):
    """Return (owner, repo) parsed from git origin, if present."""
    remote = run("git remote get-url origin 2>/dev/null", cwd=skill_dir, check=False)
    if not remote:
        return None, None

    patterns = [
        r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
        r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, remote)
        if match:
            return match.group("owner"), match.group("repo")
    return None, None


def validate_skill(skill_dir):
    """Validate skill directory structure."""
    errors = []
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(skill_md):
        errors.append("缺少 SKILL.md")
        return errors, None, None

    name, desc, yaml_error = parse_yaml_frontmatter(skill_md)
    if yaml_error:
        errors.append(yaml_error)
        return errors, None, None
    if not name:
        errors.append("SKILL.md 缺少 YAML frontmatter 中的 name 字段")
    if not desc:
        errors.append("SKILL.md 缺少 YAML frontmatter 中的 description 字段")
    if desc and len(desc) < 20:
        errors.append(f"description 太短 ({len(desc)} 字符)，建议至少 50 字符")

    return errors, name, desc


def ensure_license(skill_dir, github_user):
    """Create MIT LICENSE if missing."""
    license_path = os.path.join(skill_dir, "LICENSE")
    if os.path.exists(license_path):
        return False
    year = datetime.datetime.now().year
    # Try to get full name from git config
    full_name = run("git config user.name") or github_user
    content = f"""MIT License

Copyright (c) {year} {full_name}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
    with open(license_path, "w") as f:
        f.write(content)
    return True


def extract_user_facing_sections(body):
    """
    Extract user-facing sections from SKILL.md body.
    Skips AI-only sections like output formatting rules, internal rules, etc.

    AI-only sections to skip (case-insensitive patterns):
    - "Output Formatting Rules"
    - Lines starting with "Rule:" or "**Rule:"
    - Sections about internal AI behavior

    User-facing sections to keep:
    - Quick Examples / 快速示例 / 示例
    - Commands / 命令
    - Usage / 使用方法
    - Features / 功能
    - 支持的平台 / Supported sites
    """
    AI_SECTION_PATTERNS = [
        r"output formatting rules",
        r"requirements",  # usually "Chrome open with..." which IS user-facing, keep it
    ]
    # Actually let's keep requirements — it's important for users.
    # Only skip pure AI-instruction sections:
    SKIP_SECTION_TITLES = {
        "output formatting rules",
        "output formatting",
        "formatting rules",
    }

    lines = body.split("\n")
    result_lines = []
    skip_section = False
    current_h2 = ""

    for line in lines:
        # Detect h2/h3 headings
        h2_match = re.match(r"^##\s+(.+)$", line)
        if h2_match:
            current_h2 = h2_match.group(1).strip().lower()
            skip_section = current_h2 in SKIP_SECTION_TITLES
            if skip_section:
                continue

        # Skip lines starting with "Rule:" (AI-facing rules)
        if re.match(r"^\*?\*?Rule:", line):
            continue

        if skip_section:
            continue

        result_lines.append(line)

    return "\n".join(result_lines).strip()


def generate_readme(skill_dir, name, repo_name, desc, github_user):
    """Generate README.md from SKILL.md content."""
    readme_path = os.path.join(skill_dir, "README.md")
    if os.path.exists(readme_path):
        return False

    # Build tagline from description (first sentence)
    if "。" in desc:
        tagline = desc.split("。")[0] + "。"
    elif ". " in desc:
        tagline = desc.split(". ")[0] + "."
    else:
        tagline = desc[:120]

    readme = f"""# {repo_name}

<p align="center">
  <a href="https://github.com/{github_user}/{repo_name}/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/{github_user}/{repo_name}?style=for-the-badge&logo=github" /></a>
  <a href="https://github.com/{github_user}/{repo_name}/network/members"><img alt="Forks" src="https://img.shields.io/github/forks/{github_user}/{repo_name}?style=for-the-badge&logo=github" /></a>
  <a href="https://github.com/{github_user}/{repo_name}/issues"><img alt="Issues" src="https://img.shields.io/github/issues/{github_user}/{repo_name}?style=for-the-badge&logo=github" /></a>
  <a href="https://github.com/{github_user}/{repo_name}/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/{github_user}/{repo_name}?style=for-the-badge&logo=git" /></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue.svg?style=for-the-badge" /></a>
</p>

> {tagline}
> Install this agent skill with one command, then trigger it with natural language in Codex, Claude Code, or another skills-compatible agent.

```bash
npx skills add {github_user}/{repo_name}
```

**中文** | [English](#english)

## 为什么值得用

很多 skill 发布失败，不是功能不够好。

而是 README 太像内部说明、安装路径不清、YAML frontmatter 有坑，或者发布后没有验证能不能被 `npx skills add` 发现。

这个 skill 会把可复用工作流包装成一个公开可安装的 agent skill，并把发布结果验证到可复制安装命令为止。

## 你会得到

- 一个带 `SKILL.md`、README、LICENSE 的 GitHub 仓库
- 严格 YAML frontmatter 校验
- README 发布页，不是内部指令转储
- `npx skills add` 可发现性和真实安装验证
- 本地 `~/.agents/skills` 兼容同步
- 清楚的仓库 URL、安装命令和验证结果

## 安装

```bash
npx skills add {github_user}/{repo_name}
```

安装后确认：

```bash
test -f ~/.agents/skills/{name}/SKILL.md
```

## 你可以这样说

- "把这个 skill 发布到 GitHub。"
- "先检查一下这个 skill 能不能发布。"
- "重写 README，让它更像公开产品页，然后发布。"
- "更新已发布的 skill，并验证 npx skills add 可安装。"

## 前置要求

- [ ] 已安装 GitHub CLI：`brew install gh`
- [ ] 已登录 GitHub CLI：`gh auth status`
- [ ] 已安装 Python 3.9+
- [ ] skill 目录包含有效的 `SKILL.md`
- [ ] 公开发布前已检查 README 中没有密钥、私有路径或内部账号信息

## Skill 摘要

{desc}

## 发布质量检查

发布前至少确认：

- README 第一屏说清楚用户痛点和安装命令
- README 有真实使用示例，不只是参数说明
- README 没有 `TODO`、`特性 1`、`[问题 1]` 这类占位符
- 如果 repo 已经有 `origin`，发布目标使用现有仓库名，而不是误用 skill name
- 发布后通过 `npx skills add {github_user}/{repo_name} --list`
- 最好再做一次临时目录真实安装

## Troubleshooting

| 问题 | 原因 | 解决方法 |
|---|---|---|
| `gh` 不可用 | GitHub CLI 没装或没登录 | 运行 `brew install gh && gh auth login` |
| `npx skills add` 找不到 skill | `SKILL.md` frontmatter 无效或 repo/path 错误 | 先运行发布脚本 dry-run，修复 YAML |
| 发布到了错误仓库 | skill name 和 repo name 混用 | 使用现有 `origin`，或传 `--repo-name` |
| README 看起来像内部文档 | 直接复制了 `SKILL.md` | 重写成痛点、样例、安装、风险和排障结构 |
| 本地 `.agents` 被重复复制 | 从非规范目录发布但自动同步开启 | 使用 `--no-symlink` 或先确认目标目录 |

## License

MIT

Copyright (c) 向阳乔木  
X: https://x.com/vista8  
GitHub: https://github.com/joeseesun/

<a name="english"></a>
## English

{repo_name} packages and publishes an agent skill to GitHub, then verifies that it can be discovered and installed through `npx skills add`.

Install:

```bash
npx skills add {github_user}/{repo_name}
```

It focuses on:

- strict `SKILL.md` YAML validation
- GitHub repository creation or update
- product-page README guidance
- repo-name and skill-name separation
- `npx skills add` discovery and install verification
- safe local agent-skill sync

Copyright (c) 向阳乔木  
X: https://x.com/vista8  
GitHub: https://github.com/joeseesun/
"""
    with open(readme_path, "w") as f:
        f.write(readme)
    return True


def check_readme_quality(skill_dir):
    """Block obvious placeholder READMEs before publishing."""
    readme_path = os.path.join(skill_dir, "README.md")
    if not os.path.exists(readme_path):
        return []

    with open(readme_path, "r") as f:
        content = f.read()

    placeholder_patterns = [
        r"<!--\s*TODO",
        r"特性\s*1[：:]描述",
        r"场景\s*1[：:]\[场景名称\]",
        r"你说[：:]\"\[用户的自然语言输入\]\"",
        r"AI 做[：:]\[AI 的具体操作步骤\]",
        r"Q:\s*\[问题\s*\d+\]",
        r"\*\*A:\*\*\s*\[解决方案\]",
        r"your-org/your-repo",
        r"docs/assets/product-screenshot\.png",
        r"（在此补充",
    ]
    errors = []
    for pattern in placeholder_patterns:
        if re.search(pattern, content, flags=re.IGNORECASE):
            errors.append(f"README.md 仍包含占位内容: {pattern}")
    return errors


def init_git(skill_dir):
    """Initialize git repo if needed."""
    git_dir = os.path.join(skill_dir, ".git")
    if os.path.isdir(git_dir):
        return False
    run(f"git init", cwd=skill_dir)
    return True


def create_and_push(skill_dir, repo_name, desc, github_user, public=True):
    """Create GitHub repo and push."""
    visibility = "--public" if public else "--private"

    # Check if repo already exists
    existing = run(f"gh repo view {github_user}/{repo_name} --json url --jq '.url' 2>/dev/null", check=False)
    if existing and "github.com" in existing:
        print(f"[信息] 仓库已存在: {existing}")
        # Just push updates
        run("git add -A", cwd=skill_dir)
        status = run("git status --porcelain", cwd=skill_dir)
        if status:
            run('git commit -m "Update skill"', cwd=skill_dir)
        # Check if remote exists
        remote = run("git remote get-url origin 2>/dev/null", cwd=skill_dir, check=False)
        if not remote:
            run(f"git remote add origin https://github.com/{github_user}/{repo_name}.git", cwd=skill_dir)
        run("git push -u origin main 2>&1", cwd=skill_dir, check=False)
        run("git push -u origin HEAD:main 2>&1", cwd=skill_dir, check=False)
        return existing

    # Short description for GitHub (max 350 chars)
    gh_desc = desc[:150] if len(desc) > 150 else desc

    # Commit all files
    run("git add -A", cwd=skill_dir)
    run(f'git commit -m "Initial release: {repo_name}"', cwd=skill_dir)

    # Create repo and push
    result = run(
        ["gh", "repo", "create", f"{github_user}/{repo_name}", visibility,
         "--description", gh_desc, "--source", ".", "--push"],
        cwd=skill_dir, check=False
    )
    if result and "github.com" in result:
        url = result.strip().split("\n")[0]
        return url
    print(f"[错误] 创建仓库失败: {result}", file=sys.stderr)
    return None


def verify_skill(github_user, repo_name, skill_name):
    """Verify skill is installable via npx skills.

    Runs both --list discovery and a real install into a temporary directory.
    """
    source = f"{github_user}/{repo_name}"
    result = run(f"npx skills add {source} --list 2>&1", check=False)
    if not result:
        return False, "npx skills 命令执行失败或超时"
    # Must see both "Found N skill" and the skill name — confirms YAML was parsed OK
    if "No valid skills found" in result:
        return False, "YAML 解析失败（npx skills 找不到有效 skill）— 检查 SKILL.md frontmatter"
    if not ("Found" in result and skill_name in result):
        return False, f"skill 名称 '{skill_name}' 未出现在 --list 输出中"

    tmpdir = tempfile.mkdtemp(prefix="skill-publisher-verify-")
    try:
        install = run(
            f"npx skills add {source} --skill {skill_name} 2>&1",
            cwd=tmpdir,
            check=False,
        )
        installed_skill = os.path.join(tmpdir, ".agents", "skills", skill_name, "SKILL.md")
        if not install or not os.path.exists(installed_skill):
            return False, "真实安装失败：临时目录中没有生成 .agents/skills/<name>/SKILL.md"
        return True, None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def sync_agent_skill(skill_dir, name):
    """Copy/update a skill into ~/.agents/skills/<name> as real files.

    This keeps the local agent skill tree as the canonical on-disk mirror instead of
    a symlink, so future edits can live there as实体 files.
    """
    agents_dir = os.path.expanduser("~/.agents/skills")
    os.makedirs(agents_dir, exist_ok=True)
    target_path = os.path.join(agents_dir, name)
    target = os.path.abspath(skill_dir)
    backup_path = None

    if os.path.abspath(target_path) == target:
        return "skipped", f"{target_path} 已经是当前发布源目录，跳过同步以避免自删"

    if os.path.islink(target_path):
        backup_path = os.readlink(target_path)
        os.unlink(target_path)
    elif os.path.isdir(target_path):
        shutil.rmtree(target_path)
    elif os.path.exists(target_path):
        os.remove(target_path)

    shutil.copytree(
        target,
        target_path,
        ignore=shutil.ignore_patterns(".git", ".DS_Store"),
        dirs_exist_ok=False,
    )

    if backup_path:
        return "updated", f"{target_path} 已从 symlink 迁移为实体目录，来源: {target}"
    return "created", f"{target_path} ← {target}"


def main():
    parser = argparse.ArgumentParser(description="发布 Claude Code Skill 到 GitHub")
    parser.add_argument("skill_dir", help="Skill 目录路径")
    parser.add_argument("--github-user", help="GitHub 用户名 (默认自动获取)")
    parser.add_argument("--repo-name", help="GitHub 仓库名 (默认优先使用当前 origin 仓库名，否则使用 skill name)")
    parser.add_argument("--private", action="store_true", help="创建私有仓库 (默认公开)")
    parser.add_argument("--dry-run", action="store_true", help="仅检查，不实际发布")
    parser.add_argument("--skip-verify", action="store_true", help="跳过 npx skills 验证")
    parser.add_argument("--no-symlink", action="store_true", help="跳过同步 ~/.agents/skills/ 实体目录")
    args = parser.parse_args()

    skill_dir = os.path.abspath(args.skill_dir)
    if not os.path.isdir(skill_dir):
        print(f"[错误] 目录不存在: {skill_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 检查 Skill: {skill_dir}\n")

    # Step 1: Validate
    errors, name, desc = validate_skill(skill_dir)
    if errors:
        print("❌ 验证失败:")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)
    print(f"✅ SKILL.md 验证通过 (name: {name})")

    # Step 2: Prerequisites
    if not check_prerequisites():
        sys.exit(1)
    print("✅ gh CLI 已就绪")

    origin_owner, origin_repo = get_origin_repo(skill_dir)
    github_user = args.github_user or origin_owner or get_github_user()
    if not github_user:
        print("[错误] 无法获取 GitHub 用户名", file=sys.stderr)
        sys.exit(1)
    print(f"✅ GitHub 用户: {github_user}")

    repo_name = args.repo_name or origin_repo or name
    print(f"✅ GitHub 仓库名: {repo_name}")
    if repo_name != name:
        print(f"ℹ️  Skill name 与仓库名不同: skill={name}, repo={repo_name}")

    # Step 3: Ensure LICENSE
    if ensure_license(skill_dir, github_user):
        print("📄 已创建 LICENSE (MIT)")
    else:
        print("✅ LICENSE 已存在")

    # Step 4: Generate README
    if generate_readme(skill_dir, name, repo_name, desc, github_user):
        print("📄 已生成 README.md")
    else:
        print("✅ README.md 已存在")

    readme_errors = check_readme_quality(skill_dir)
    if readme_errors:
        print("❌ README 质量检查失败:")
        for e in readme_errors:
            print(f"   - {e}")
        sys.exit(1)
    print("✅ README 质量检查通过")

    if args.dry_run:
        print(f"\n🏁 Dry run 完成。实际发布命令:")
        print(f"   python3 {__file__} {skill_dir} --github-user {github_user} --repo-name {repo_name}")
        return

    # Step 5: Git init
    if init_git(skill_dir):
        print("📦 已初始化 git 仓库")
    else:
        print("✅ git 仓库已存在")

    # Step 6: Create repo and push
    public = not args.private
    print(f"\n🚀 发布到 GitHub ({'公开' if public else '私有'})...")
    url = create_and_push(skill_dir, repo_name, desc, github_user, public=public)
    if not url:
        print("❌ 发布失败", file=sys.stderr)
        sys.exit(1)
    print(f"✅ GitHub: {url}")

    # Step 7: Verify
    if not args.skip_verify:
        print("\n🔎 验证 npx skills 可安装...")
        ok, verify_err = verify_skill(github_user, repo_name, name)
        if ok:
            print("✅ 验证通过（可发现，并已在临时目录真实安装）")
        else:
            print(f"❌ 验证失败: {verify_err}", file=sys.stderr)
            print("   请检查 SKILL.md frontmatter，修复后重新运行脚本更新", file=sys.stderr)

    # Step 8: Sync ~/.agents/skills/实体目录
    if not args.no_symlink:
        status, msg = sync_agent_skill(skill_dir, name)
        if status == "created":
            print(f"\n📁 已同步 Agent skill: {msg}")
        elif status == "updated":
            print(f"\n📁 已更新 Agent skill: {msg}")
        else:
            print(f"\nℹ️  Agent skill: {msg}")

    # Summary
    print(f"\n{'='*60}")
    print(f"🎉 发布成功！")
    print(f"   仓库: {url}")
    print(f"   安装: npx skills add {github_user}/{repo_name}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
