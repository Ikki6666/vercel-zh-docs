# vercel-zh-docs

[Vercel 官方文档](https://vercel.com/docs) 的非官方简体中文翻译项目。

> 本项目与 Vercel, Inc. 无隶属关系。内容版权归 Vercel 所有，以官方英文文档为准。

## 工作原理

```
vercel.com /docs/sitemap.md + /docs/<path>.md     官方机器可读内容端点
        │ scripts/sync.py（每周同步，hash 增量）
upstream/en/ + upstream/manifest.json             英文镜像与 hash 登记
        │ scripts/translate.py（LLM 批量翻译，注入术语表）
translations/zh/                                  中文译文（人工可改）
        │ scripts/publish.py + scripts/build_nav.py
site/（Astro Starlight）→ 静态站点
```

- 翻译状态由 `manifest.json` 中的 `hash`（上游内容）与 `translated_hash`（翻译时所基于的版本）对比自动推导。
- 站点内容目录 `site/src/content/docs/`（除首页）与 `site/src/nav.json` 均为生成物，已 gitignore。

## 快速开始

```bash
make sync          # 同步官方文档（首次会全量下载约 1250 页）
make status        # 查看翻译状态统计
make translate     # 需要 VZ_API_BASE / VZ_API_KEY / VZ_MODEL 环境变量
make dev           # 生成本地内容并启动开发服务器
make build         # 生成本地内容并构建静态站点到 site/dist/
```

翻译一批页面：

```bash
export VZ_API_BASE=https://api.openai.com/v1   # 任意 OpenAI 兼容端点
export VZ_API_KEY=sk-...
export VZ_MODEL=gpt-4o

python3 scripts/translate.py --status untranslated --limit 20   # 先看清单可加 --dry-run
```

翻译成功会自动登记版本 hash；人工修改译文后无需重新登记（hash 记录的是上游版本）。

## 目录结构

| 路径 | 说明 |
|---|---|
| `upstream/en/` | 官方英文 Markdown 镜像（脚本管理，勿手改） |
| `upstream/manifest.json` | 每页 hash / lastmod / 层级 / 翻译版本登记 |
| `translations/zh/` | 中文译文，与 `upstream/en/` 同相对路径 |
| `glossary/terms.json` | 术语表（keep = 保留英文，translate = 强制译法） |
| `glossary/style-guide.md` | 翻译风格指南 |
| `scripts/` | sync / status / stamp / translate / publish / build_nav |
| `site/` | Astro Starlight 站点 |
| `docs-plan.md` | 项目完整规划（分期、成本、风险） |

## 路线图

- **M0（当前）**：同步管道 + 站点骨架 + 全量英文镜像上线。
- **M1**：核心章节约 250 页中文翻译（入门、概念、框架、函数、部署、域名、CLI、环境变量）。
- **M2**：全量翻译（≥95% 覆盖），REST API 参考保留英文。
- **M3**：每周自动同步重翻、社区贡献流程、KB（/kb）二期调研。

## 注意事项

- 官方 frontmatter 的 `last_updated` 不可靠（长期停留 2018），同步以 sitemap 的 `Lastmod` + 内容 sha256 为准。
- 官方未提供 KB（/kb）页面的 `.md` 端点，KB 暂未纳入。
- 域名与站点请保持「非官方」声明，避免商标问题。
