# apple-notes-tagger — handoff

This file holds what waits on Lee; PWE Desk reads its `## 等 Lee` section every morning.

## 等 Lee

- **[决定] 同一个操作的三个名字：activate / repair / converted** — 命令名 `activate`（SKILL.md:68、README.md:85），说明里又叫 repair（SKILL.md:67 注释、README.md:84、README.md:119、两个 plugin manifest 的描述）和 converted（SKILL.md:79）· 推荐：命令名保持 `activate`（对外 CLI，改名会破坏用户脚本），文档动词统一用 activate，repair 只留在 README.md:119 的括注和 manifest 描述里 · 不定则三个名字并存 · 自 2026-10-07
- **[决定] `remove` 的 RTL 检查方向要不要修** — skills/apple-notes-tagger/scripts/notes_tags.py:257 查的是标签之前的文字 `v0[:b]`，但随后光标从文末向左走过的是标签之后的 `v0[b:]`（:258-261）；docs/ARCHITECTURE.md:126 说 remove 只走过已确认没有 RTL 的文字 · 推荐：先用一条标签后面有阿拉伯文的测试笔记验证，确认后改成查 `v0[b:]` · 不定则标签后有 RTL 文字时，方向键按下后才被 :264 的光标检查拦下（一个字没删，但计为 Fail），标签前有 RTL 的笔记被白白跳过 · 读代码推断，未真机验证 · 自 2026-10-07
- **[决定] 元素计数对不上算 Skip 还是 Fail** — docs/ARCHITECTURE.md:111-112 说是 Skip，代码 notes_tags.py:248-249 `raise Fail`，会计入「连续五次失败就停」· 推荐：改代码为 Skip，和文档、README 的 "refuses" 一致 · 不定则一批计数不符的笔记会让整轮提前停下 · 自 2026-10-07
