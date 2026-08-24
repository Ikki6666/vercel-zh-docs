# Vercel 文档中文翻译站 — 完整项目规划

> 基于 2026-08-24 调研结论：vercel.com/docs 不开源，但官方暴露了完整的机器可读内容层
> （任意页面 `.md` 后缀返回原始 Markdown、`/docs/sitemap.md` 层级索引、`llms-full.txt` 全量包）。
> 项目代号（暂定）：`vercel-docs-zh`

## 1. 项目定位

- **非官方**社区中文翻译站，忠实跟踪 vercel.com/docs（/docs 主体，1257 页）。
- 目标用户：使用 Vercel 平台的中文开发者。
- 成功标准：核心章节覆盖率 100%、全站覆盖率 ≥95%、翻译滞后官方 ≤7 天、译文可读性过关。

## 2. 总体架构

```
vercel.com（官方源，只读）
  ├─ /docs/sitemap.md          ──┐
  ├─ /docs/<path>.md             ├─→ 同步管道（sync.py）
  └─ /docs/taxonomy.json       ──┘
        │
   upstream/en/docs/...        # 英文镜像（脚本管理，git 可追溯）
   manifest.json               # {path: {hash, lastmod, synced_at}}
        │
   翻译流水线（translate.py，LLM + 术语表约束）
        │
   translations/zh/docs/...    # 中文译文（人工可改，git 可追溯）
        │
   Starlight 构建（build_nav.py 自动生成侧边栏）
        │
   静态站点 → 部署到 Vercel
```

核心原则：

1. 英文镜像与中文译文分离存放（同 LangChain zh-overlay 模式），译文永远可人工修改。
2. 一切产物可重建：upstream 可重拉，站点内容从 translations 生成。
3. 翻译状态由 hash 对比推导，不靠人工记忆。

## 3. 仓库结构

```
vercel-docs-zh/
├── upstream/
│   ├── en/docs/…               # 官方 .md 镜像（只读区，脚本写入）
│   ├── sitemap.md              # 最近一次拉取的 sitemap
│   └── manifest.json           # hash / lastmod 登记表
├── translations/zh/docs/…      # 中文译文（与 upstream 同相对路径）
├── glossary/
│   ├── terms.json              # 术语表（taxonomy.json 派生 + 人工维护）
│   └── style-guide.md          # 翻译风格指南
├── site/                       # Astro Starlight 站点
│   ├── astro.config.mjs
│   ├── src/content/docs/       # 由脚本从 translations/zh 同步生成
│   └── src/components/         # 状态横幅、原文链接等
├── scripts/
│   ├── sync.py                 # sitemap → diff → 下载变更页
│   ├── status.py               # untranslated / translated / needs_update / removed
│   ├── translate.py            # LLM 批量翻译（注入术语表与风格指南）
│   ├── build_nav.py            # sitemap 层级 → sidebar 配置
│   └── stamp.py                # 登记已翻译版本的 hash
├── .github/workflows/
│   ├── sync.yml                # 每周一同步，自动开 PR（含变更清单）
│   ├── translate.yml           # 手动触发批量翻译
│   └── deploy.yml              # push main → 构建 + 部署
└── Makefile                    # sync / status / translate / build 等入口
```

## 4. 核心流程

### 4.1 同步管道（make sync）

1. 拉 `/docs/sitemap.md`，解析缩进层级与每页的 path / type / lastmod / summary。
2. 与 manifest 对比，得出：新增、删除、lastmod 变化三类。
3. lastmod 变化页下载 `<path>.md` 算 sha256；hash 未变只更新 lastmod（官方 frontmatter 的 `last_updated` 不可靠，以 sitemap Lastmod + 内容 hash 为准）。
4. 更新 upstream 与 manifest，输出报告。
5. 删除页：upstream 移除；译文保留并标记 `removed_upstream`，不进构建。

频率：GitHub Actions 每周一自动 + 随时手动。

### 4.2 翻译状态机（make status）

| 状态 | 判定 | 动作 |
|---|---|---|
| untranslated | 无译文 | 进入待翻队列 |
| translated | 译文 hash == upstream hash | 无 |
| needs_update | hash 不一致 | 拉真实 diff，增量重翻（不盲目全重翻） |
| removed_upstream | upstream 已删 | 退出构建，保留归档 |

### 4.3 翻译流水线（make translate）

- 系统规则：frontmatter 只译 title/description；代码块、命令、路径、包名、环境变量、内部链接（保持相对路径）一律不动；Markdown 结构与原文对齐。
- 每批注入术语表（强制译名）+ 风格指南（中文技术文档惯例：用"你"、主动语态、半角标点配空格等）。
- 模型分层：全量初翻用高性价比模型（GLM / DeepSeek 级）；核心章节用强模型复校一遍。
- 工程要求：断点续跑、单页失败重试不阻塞批次、token 用量统计。
- 术语表来源：`/docs/taxonomy.json`（官方产品命名）+ 第一批翻译后人工整理高频术语。

### 4.4 构建与站点

- `build_nav.py`：sitemap 缩进层级自动转 Starlight sidebar；中文标题取自译文 frontmatter。
- 每页顶部组件：非官方声明 +「基于官方 <Lastmod> 版本翻译」+ 查看英文原文链接 + 落后天数徽章。
- 不翻译区（如 REST API 参考）：直接渲染英文原文并打"未翻译"徽章，保证导航完整。
- 搜索：Starlight 内置 Pagefind（中文可用）。
- SEO：self-canonical（不指回官方，否则中文页不被收录），页面显著标注来源与原文链接。

### 4.5 部署

静态产物部署到 Vercel（免费额度足够）。域名避免以 "vercel" 开头（商标风险），如 `vcdocs-cn.xxx` / `vercel-zh.xxx` 均有风险，建议中性命名并在站内声明非官方。

## 5. 分期计划

### M0 — 骨架验证（第 1 周）

- 仓库初始化；sync.py / status.py / manifest 跑通。
- Starlight 站点 + build_nav 自动生成全量导航（英文壳）。
- 部署预览域名。
- 验收：sync 幂等、status 准确、1257 页导航自动生成。

### M1 — 核心章节（第 2–3 周）

- 范围（约 250 页）：Getting Started、Fundamentals、Frameworks、Functions、Deployments、Domains、CLI、环境变量、Projects & Accounts、Observability。
- 术语表 v1 + 风格指南定稿；翻译流水线全链路跑通。
- 人工抽检每批 10%。
- 验收：站点公开可访问，核心路径全中文。

### M2 — 全量 docs（第 4–8 周）

- 剩余约 950 页分批翻译（每批约 100 页：跑 → 抽检 → 修 → 合并）。
- REST API 参考策略落地：英文保留 + 中文导航壳。
- 验收：覆盖率 ≥95%（低价值/废弃页可豁免并登记）。

### M3 — 持续运营（长期）

- 每周自动同步 → 自动开 PR（变更清单 + needs_update 标记）→ 小 diff 自动重翻。
- 社区贡献指南（PR 流程 + 翻译规范 + issue 模板）。
- 二期调研：KB 669 页（无 .md 端点，需 HTML 抓取转换方案）。
- 可选：站内中文 AI 问答。

## 6. 质量保证

- 一致性检查脚本：术语表禁译词扫描；译文与原文的结构 diff（标题层级数、代码块数、链接数不一致即报警）。
- 抽检制度：每批 10% 人工审，核心章节加倍。
- 反馈闭环：每页「报告翻译问题」按钮 → GitHub issue 模板（带页面路径与版本 hash）。

## 7. 成本估算

| 项 | 估算 |
|---|---|
| LLM 初翻（全量约 200 万 token） | GLM/DeepSeek 级：约 ¥100–200；Claude Sonnet 级：$30–60 |
| 每周增量重翻 | 很小（通常几十页以内） |
| 托管 | 静态站，免费 |
| 域名 | 约 ¥60/年 |
| 人力 | M1–M2 审校每周约 5–10 小时 |

## 8. 风险与应对

| 风险 | 应对 |
|---|---|
| 官方端点改版失效 | 管道只依赖 3 个稳定端点；sync 失败即告警；HTML 抓取转换作 fallback |
| 官方更新量大跟不上 | 分层跟进：核心章节 100%，长尾页显示落后天数，透明化管理预期 |
| 商标/版权 | 非官方声明 + 原文链接 + 不用官方 logo + 中性域名 |
| 术语不一致 | 术语表强制注入 + 一致性扫描 |
| LLM 译文质量 | 风格指南 + 抽检 + 社区反馈修复 |

## 9. 下一步

1. 确认项目名与域名方向。
2. 初始化仓库，执行 M0（我可以直接搭出全部骨架并跑通同步）。
