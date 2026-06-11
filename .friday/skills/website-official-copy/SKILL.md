---
name: website-official-copy
description: 为星期五官网生成或改写正式、专业的产品介绍文案。用户提到官网介绍太口语、不官方、像聊天话术、或要重写 landing 文案时使用。与 impeccable 的 clarify/brand 配合。
---

# 星期五官网官方文案

## 何时使用

- 改写 `website/index.html` 介绍、导航、按钮、区块标题
- 用户说「太不官方」「像口语」「要正式一点」「产品官网文案」
- 发版前统一官网语气

## 语气标准（官方中文产品页）

| 要 | 不要 |
|----|------|
| 陈述能力与边界 | 网络口语、梗、反问、吐槽竞品 |
| 具体功能名（Agent、Ask 模式、WebView2） | 「说人话」「真的去做」「不是教程」 |
| 按钮：动词 + 对象（「查看使用示例」） | 「看怎么说」「了解能力」等含糊 CTA |
| 一节一个主题，标题 ≤12 字为宜 | 「不是炫技清单」「和普通 AI 差在哪」 |
| 数据与隐私写清路径与模式 | 夸张承诺、空泛「智能」「赋能」 |

## 开工前必读（事实来源，禁止编造）

1. `website/PRODUCT.md`（本 skill 维护的产品事实表）
2. `friday/version.py`、`assets/changelog.json`（版本与已发布能力）
3. `README.md` / `long-term-plan.md` 中与对外介绍相关的段落
4. 现有 `website/index.html` 结构（只改文案，不擅自改布局除非用户要求）

## 生成流程

1. **读 PRODUCT.md**，列出本节可写的已验证能力
2. **按区块起草**（Hero → 概览 → 使用示例 → 微信 → 扩展 → 下载 → 系统要求）
3. **自检清单**（全部通过再写入 HTML）：
   - [ ] 无口语按钮/导航（如「看怎么说」「怎么说」）
   - [ ] 每段能对应 PRODUCT.md 中至少一条事实
   - [ ] meta description / og:description 与 Hero 一致、≤160 字
   - [ ] 下载区与 `publish-release.mdc` 约定一致（安装包 ZIP、非便携教程）
4. **可选润色**：对 `website/index.html` 跑 Impeccable `clarify`（`.cursor/skills/impeccable/reference/clarify.md`）做最后一遍清晰度检查
5. **部署**：改完后提醒用户或执行 `website` 目录 `npx vercel deploy --prod --yes` + `vercel alias` 到 `fridayaiagent.vercel.app`

## HTML 映射（保持 id 不变）

| 区块 id | 官方标题建议 |
|---------|----------------|
| `#overview` | 产品能力概览 |
| `#examples` | 典型使用场景 |
| `#wechat` | 微信远程任务 |
| `#features` | 扩展与配置 |
| `#download` | 下载安装 |
| `#requirements` | 系统要求 |

## 禁止

- 编造未实现功能或具体数字（工具数量须与 PRODUCT.md 一致）
- 把官网改成博客/段子体
- 未读 PRODUCT.md 就整页重写
