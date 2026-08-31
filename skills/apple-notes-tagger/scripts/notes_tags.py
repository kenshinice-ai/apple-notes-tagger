#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apple 备忘录真标签工具。

备忘录的 #标签 是内联对象，只有编辑器的输入解析会创建它。核心手法：
  · 激活已有的死文本标签：光标移到标签末尾 -> 敲空格 -> 退格
  · 新增标签：粘贴标签文本 -> 敲空格（粘贴绕开输入法，中文才不会被吃掉）
两者都不重打已有文字，所以中文标签能保住。

子命令：
  scan      只读盘点所有笔记（真标签数 / 死标签行）
  tags      列出一条笔记上真标签的名字
  activate  把死文本标签行就地激活成真标签
  add       在笔记末尾追加真标签
  remove    删掉指定的真标签
"""
import argparse, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "engine.applescript")
OBJ = "￼"                       # 真标签/附件在正文里的占位符
DATE_LINE = re.compile(r"^\s*📅\s*\d{4}-\d{2}-\d{2}\s*$")

class Hang(Exception): pass
class Fail(Exception): pass
class Skip(Exception): pass          # 明确判定「不该动这条」，与失败区分开

# AX 会给右到左的标签名包上双向隔离符，匹配前必须剥掉
BIDI = dict.fromkeys(map(ord, "\u200e\u200f\u061c\u2066\u2067\u2068\u2069"
                              "\u202a\u202b\u202c\u202d\u202e"), None)
# 希伯来语/阿拉伯语等强 RTL 区段
RTL_RE = re.compile("[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]"
                    "|[\U00010800-\U00010fff]|[\U0001e800-\U0001eeff]")

def has_rtl(text):
    return bool(RTL_RE.search(text))

# ---------------------------------------------------------------- 底层调用

def osa(*args, timeout=45):
    try:
        p = subprocess.run(["osascript", ENGINE] + [str(a) for a in args],
                           capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["pkill", "-9", "osascript"], capture_output=True)
        raise Hang("osascript 超时（备忘录卡住了）: %s" % (args[:1],))
    if p.returncode != 0:
        raise Fail("osascript 出错: " + p.stderr.decode("utf-8", "replace")[:200])
    out = p.stdout.decode("utf-8", "replace")
    head, _, val = out.partition("\n")
    f = head.split("\t")
    if f[0] != "OK":
        raise Fail(head.replace("\t", " "))
    if val.endswith("\n"): val = val[:-1]
    return int(f[1]), int(f[2]), val

def u16(s):  return len(s.encode("utf-16-le")) // 2
def idx_of_u16(s, off):
    n = 0
    for i, ch in enumerate(s):
        if n == off: return i
        n += 2 if ord(ch) > 0xFFFF else 1
    if n == off: return len(s)
    raise Fail("UTF-16 偏移 %d 落在代理对中间" % off)

def open_note(nid):
    """打开笔记、焦点进正文、光标到文末。返回 (光标偏移, 全文)。"""
    caret, sel, v = osa("open", nid)
    if caret != u16(v) or sel != 0:
        raise Fail("Cmd+↓ 之后光标不在文末（%d/%d，全文 %d）" % (caret, sel, u16(v)))
    return caret, v

# ---------------------------------------------------------------- 标签行识别

def tagline_candidate(value, vocab=None, scan_back=1):
    """找出「标签行」。默认只看最后一个非空行（若它是 📅 日期行则看它上面一行），
    避免把正文里的话题标签行（#某某[话题]# 之类）误当成标签行。
    返回 (行号, 行文本, 行首字符下标) 或 None。"""
    lines = value.split("\n")
    starts, pos = [], 0
    for l in lines:
        starts.append(pos); pos += len(l) + 1
    idx = [i for i, l in enumerate(lines) if l.strip()]
    if not idx: return None
    cands = []
    last = idx[-1]
    cands.append(last)
    if DATE_LINE.match(lines[last].strip()) and len(idx) > 1:
        cands.append(idx[-2])
    for extra in range(1, scan_back):
        k = len(idx) - 1 - extra
        if k >= 0: cands.append(idx[k])
    for i in cands:
        toks = [t for t in lines[i].split(" ") if t]
        if not toks: continue
        if vocab is not None:
            ok = all(t in vocab or t == OBJ for t in toks) and any(t in vocab for t in toks)
        else:
            ok = all(t.startswith("#") or t == OBJ for t in toks) and any(t.startswith("#") for t in toks)
        if ok: return i, lines[i], starts[i]
    return None

def tokens_of(line, line_start):
    out, i = [], 0
    while i < len(line):
        if line[i] == " ": i += 1; continue
        j = i
        while j < len(line) and line[j] != " ": j += 1
        out.append((line[i:j], line_start + i, line_start + j)); i = j
    return out

# ---------------------------------------------------------------- 激活

def plan_activate(v0, caret, vocab, scan_back):
    """预先算出整条笔记的动作序列（右往左）和预期最终正文。"""
    steps, v, cur = [], v0, idx_of_u16(v0, caret)
    while True:
        f = tagline_candidate(v, vocab, scan_back)
        if not f: break
        _, line, lstart = f
        pick = (lambda t: t in vocab) if vocab is not None else (lambda t: t.startswith("#"))
        toks = [t for t in tokens_of(line, lstart) if pick(t[0])]
        if not toks: break
        tok, a, b = toks[-1]
        presses = cur - b
        if presses < 0: raise Fail("光标已在目标左侧")
        steps.append((presses, u16(v[:b])))
        v = v[:a] + OBJ + v[b:]
        cur = a + 1
    return steps, v

def activate(nid, vocab=None, scan_back=1):
    caret, v0 = open_note(nid)
    f = tagline_candidate(v0, vocab, scan_back)
    if f and has_rtl(f[1]):
        # 方向键在双向文本里按「视觉」顺序移动，不按逻辑顺序，光标算术会错位。
        # 校验能拦住并撤销，但不如根本不动它。add / remove 不受影响。
        raise Skip("标签行含右到左文字（阿拉伯/希伯来等），方向键定位不可靠，跳过")
    steps, expected = plan_activate(v0, caret, vocab, scan_back)
    if not steps: return 0
    flat = []
    for p, e in steps: flat += [p, e]
    try:
        caret, sel, v = osa("tagseq", *flat, timeout=30 + 3 * len(steps))
    except Fail as e:
        if "caret" in str(e) or "选区" in str(e):
            _, _, vu = osa("undo", 2 * len(steps) + 2)
            raise Fail("%s（已撤销，完全还原=%s）" % (e, vu == v0))
        raise
    if v != expected:
        _, _, vu = osa("undo", 2 * len(steps) + 2)
        raise Fail("结果与预期不符（已撤销，完全还原=%s）" % (vu == v0))
    return len(steps)

# ---------------------------------------------------------------- 新增 / 删除

def add_tags(nid, tags, mode="auto"):
    """在笔记末尾追加真标签。整个过程是原子的：一旦开始改动，
    任何一步出问题都会撤销并确认还原，绝不留下半成品（否则重跑会重复添加）。"""
    caret, v0 = open_note(nid)
    f = tagline_candidate(v0)
    lines = v0.split("\n")
    idx = [i for i, l in enumerate(lines) if l.strip()]
    on_tagline = bool(idx) and f is not None and idx[-1] == f[0]
    if mode == "auto":
        mode = "append" if on_tagline else "newline"

    touched = False
    def rollback(n):
        try:
            _, _, vu = osa("undo", n)
            return vu == v0
        except (Fail, Hang):
            return False

    try:
        if mode == "newline":
            _, _, v = osa("ret")
            touched = True
            if v != v0 + "\n":
                raise Fail("换行后正文异常")
            base = v
        elif v0 and not v0.endswith((" ", "\n")):
            _, _, v = osa("space")
            touched = True
            if v != v0 + " ":
                raise Fail("补分隔空格后正文异常")
            base = v
        else:
            base = v0

        expected = base + " ".join([OBJ] * len(tags)) + " "
        _, _, v = osa("addseq", *tags, timeout=30 + 5 * len(tags))
        touched = True
        if v != expected:
            raise Fail("追加标签后正文不符")
        _, _, v = osa("back", 1)          # 去掉末尾那个触发解析用的空格
        if v != expected[:-1]:
            raise Fail("删末尾空格后正文不符")
        return len(tags)
    except (Fail, Hang) as e:
        if not touched:
            raise
        ok = rollback(3 * len(tags) + 6)
        raise Fail("%s（已撤销，完全还原=%s）" % (e, ok))

def clean_name(desc):
    """AXDescription 形如 "<本地化的词> <标签名>"（英文是 "Tag foo"）。
    标签名不含空格，所以按第一个空格切开就够，不依赖任何语言的固定前缀。"""
    d = desc.translate(BIDI).strip()
    if " " in d:
        d = d.split(" ", 1)[1]
    return d.strip()

def inline_elements(nid=None):
    """按文档顺序返回正文里的内联元素，与正文中的 ￼ 一一对应。
    每项 (kind, name)，kind 为 "tag" 或 "attachment"。"""
    if nid is not None: open_note(nid)
    _, _, out = osa("elements")
    els = []
    for line in out.split("\n"):
        if not line.strip(): continue
        f = line.split("\t")
        role = f[0] if f else ""
        sub = f[1] if len(f) > 1 else ""
        desc = f[2] if len(f) > 2 else ""
        if role == "AXGroup" or sub == "AXHostingView":
            continue                              # 编辑器自己的宿主视图，不是正文元素
        if sub == "AXTextAttachment" or role == "AXLink":
            els.append(("attachment", desc.translate(BIDI).strip()))
        else:
            els.append(("tag", clean_name(desc)))
    return els

def list_tags(nid):
    return [name for kind, name in inline_elements(nid) if kind == "tag"]

def remove_tags(nid, targets):
    """删掉指定名字的真标签。内联元素与正文里的 ￼ 按文档顺序一一对应，
    所以带附件的笔记也能正确处理——附件会被识别出来并跳过。"""
    wanted = [t.lstrip("#").translate(BIDI).strip() for t in targets]
    removed = 0
    for want in wanted:
        caret, v0 = open_note(nid)
        els = inline_elements()
        positions = [i for i, ch in enumerate(v0) if ch == OBJ]
        if len(els) != len(positions):
            raise Fail("内联元素 %d 个但占位符 %d 个，对不上，不动这条"
                       % (len(els), len(positions)))
        k = next((i for i, (kind, name) in enumerate(els)
                  if kind == "tag" and name == want), None)
        if k is None:
            continue
        a, b = positions[k], positions[k] + 1
        if b < len(v0) and v0[b] == " ":      b += 1     # 连同后面的分隔空格
        elif a > 0 and v0[a - 1] == " ":      a -= 1     # 或前面的
        if has_rtl(v0[:b]):
            raise Skip("这条笔记里有右到左文字，方向键按视觉顺序移动，不安全，跳过")
        presses = len(v0) - b
        if presses:
            caret, sel, v = osa("left", presses)
            if v != v0: raise Fail("移动光标时正文变了")
        want_caret = u16(v0[:b])
        if caret != want_caret:
            raise Fail("光标位置不符 got=%d want=%d（一个字都没删）" % (caret, want_caret))
        expected = v0[:a] + v0[b:]
        _, _, v = osa("back", b - a)
        if v != expected:
            _, _, vu = osa("undo", (b - a) + 2)
            raise Fail("删除后正文不符（已撤销，完全还原=%s）" % (vu == v0))
        removed += 1
    return removed

# ---------------------------------------------------------------- 自动分类的两端

SECRET_HINTS = [
    r"sk-[A-Za-z0-9_\-]{16,}", r"\bAKIA[0-9A-Z]{16}\b", r"ghp_[A-Za-z0-9]{20,}",
    r"\bBSB\b", r"\bTFN\b", r"\bCVV\b", r"\bIBAN\b", r"\bSWIFT\b",
    r"\bpassw(or)?d\b", r"\bpasscode\b", r"\bpin\b\s*[:：=]",
    r"\b密码\b", r"\b账号\b\s*[:：]", r"\b(?:\d[ -]?){13,19}\b",
]
SECRET_RE = re.compile("|".join(SECRET_HINTS), re.IGNORECASE)

def looks_sensitive(text):
    return bool(SECRET_RE.search(text))

def export_for_tagging(recs, out_path, max_chars=600, skip_sensitive=True,
                       exclude_folders=(), only_untagged=True):
    """把待分类的笔记导出成 JSONL，交给模型读。默认跳过看起来含凭据的笔记。"""
    n_skip_sensitive = n_skip_tagged = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in recs:
            if r["folder"] in exclude_folders or r["folder"] == "Recently Deleted": continue
            real = r["txt"].count(OBJ) - r["natt"]
            if only_untagged and real > 0:
                n_skip_tagged += 1; continue
            if skip_sensitive and looks_sensitive(r["txt"]):
                n_skip_sensitive += 1; continue
            body = r["txt"].strip()
            if len(body) > max_chars: body = body[:max_chars] + " …"
            fh.write(json.dumps({"id": r["id"], "folder": r["folder"],
                                 "title": r["name"][:80], "text": body},
                                ensure_ascii=False) + "\n")
    return n_skip_sensitive, n_skip_tagged

def load_map(path):
    """标签分配表。每行： <note id><TAB>#标签1 #标签2 ...   （# 开头的行是注释）"""
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("//"): continue
        parts = line.split("\t")
        if len(parts) < 2: continue
        nid = parts[0].strip()
        tags = [t if t.startswith("#") else "#" + t for t in parts[1].split() if t.strip()]
        if nid and tags: out.append((nid, tags))
    return out

# ---------------------------------------------------------------- 只读盘点

SURVEY = r'''
set outFile to "%s"
set fh to open for access (POSIX file outFile) with write permission
set eof fh to 0
tell application "Notes"
	repeat with a in accounts
		repeat with f in folders of a
			set fn to name of f
			set an to name of a
			repeat with n in notes of f
				try
					write ("<<<REC>>>" & an & tab & fn & tab & (id of n) & tab & (name of n) & tab & (creation date of n as text) & tab & (count of attachments of n) & "<<<TXT>>>" & (plaintext of n) & linefeed) to fh as «class utf8»
				end try
			end repeat
		end repeat
	end repeat
end tell
close access fh
'''

def scan(out_path):
    script = SURVEY % out_path
    p = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=900)
    if p.returncode != 0:
        raise Fail(p.stderr.decode("utf-8", "replace")[:300])
    recs = []
    for r in open(out_path, encoding="utf-8").read().split("<<<REC>>>"):
        if not r.strip(): continue
        head, _, txt = r.partition("<<<TXT>>>")
        f = head.split("\t")
        if len(f) < 6: continue
        recs.append(dict(account=f[0], folder=f[1], id=f[2], name=f[3],
                         cdate=f[4], natt=int(f[5]), txt=txt.rstrip("\n")))
    return recs

# ---------------------------------------------------------------- CLI

def load_ids(path):
    return [l.strip() for l in open(path, encoding="utf-8") if l.strip()]

def load_vocab(path):
    if not path: return None
    return set(open(path, encoding="utf-8").read().split())

def run_batch(ids, fn, log_path, label):
    log = open(log_path, "a", encoding="utf-8", buffering=1) if log_path else None
    ok = fail = skipped = consec = 0
    t0 = time.time()
    for k, nid in enumerate(ids, 1):
        try:
            n = fn(nid); ok += 1; consec = 0
            line = "OK\t%s\t%d" % (nid, n)
        except Skip as e:
            skipped += 1; consec = 0          # 主动跳过不算失败，不触发熔断
            line = "SKIP\t%s\t%s" % (nid, e)
        except (Fail, Hang) as e:
            fail += 1; consec += 1
            line = "FAIL\t%s\t%s" % (nid, e)
        if log: log.write(line + "\n")
        if not line.startswith("OK"): print(line, flush=True)
        if consec >= 5:
            print("连续 5 条失败，停止。"); break
        if k % 20 == 0:
            el = time.time() - t0
            print("%s %d/%d  ok=%d skip=%d fail=%d  已用 %.1f 分钟，剩约 %.0f 分钟"
                  % (label, k, len(ids), ok, skipped, fail, el/60, el/k*(len(ids)-k)/60),
                  flush=True)
    print("%s 完成：ok=%d skip=%d fail=%d" % (label, ok, skipped, fail))
    return ok, fail

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="只读盘点所有笔记")
    s.add_argument("--out", default="notes-scan.txt")
    s.add_argument("--dead-ids", help="把「还有死文本标签行」的笔记 id 写到这个文件")
    s.add_argument("--vocab", help="标签词表文件（每行一个 #词），限定只认这些词")

    s = sub.add_parser("tags", help="列出一条笔记上真标签的名字")
    s.add_argument("--id", required=True)

    s = sub.add_parser("activate", help="把死文本标签行激活成真标签")
    s.add_argument("--ids", required=True, help="每行一个 note id")
    s.add_argument("--vocab")
    s.add_argument("--scan-back", type=int, default=1)
    s.add_argument("--log", default="activate.log")

    s = sub.add_parser("add", help="在笔记末尾追加真标签")
    s.add_argument("--ids", required=True)
    s.add_argument("--tags", required=True, help="逗号分隔，例如 '#房贷,#ref'")
    s.add_argument("--mode", choices=["auto", "newline", "append"], default="auto")
    s.add_argument("--log", default="add.log")

    s = sub.add_parser("export", help="导出待分类的笔记（JSONL），交给模型判断该打什么标签")
    s.add_argument("--out", default="to-tag.jsonl")
    s.add_argument("--scan-out", default="notes-scan.txt")
    s.add_argument("--max-chars", type=int, default=600)
    s.add_argument("--include-sensitive", action="store_true",
                   help="连疑似含密码/银行卡/密钥的笔记也导出（默认跳过）")
    s.add_argument("--include-tagged", action="store_true", help="连已有真标签的笔记也导出")
    s.add_argument("--exclude-folder", action="append", default=[])

    s = sub.add_parser("apply", help="按分配表给笔记打标签（每行： note-id<TAB>#a #b）")
    s.add_argument("--map", required=True)
    s.add_argument("--mode", choices=["auto", "newline", "append"], default="auto")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--log", default="apply.log")

    s = sub.add_parser("remove", help="删掉指定的真标签")
    s.add_argument("--ids", required=True)
    s.add_argument("--tags", required=True, help="逗号分隔，例如 '#附件,#file'")
    s.add_argument("--log", default="remove.log")

    a = ap.parse_args()

    if a.cmd == "scan":
        vocab = load_vocab(a.vocab)
        recs = scan(os.path.abspath(a.out))
        dead = []
        for n in recs:
            n["real"] = n["txt"].count(OBJ) - n["natt"]
            f = tagline_candidate(n["txt"], vocab)
            n["dead"] = bool(f and any(t.startswith("#") for t in f[1].split()))
            if n["dead"]: dead.append(n)
        print("笔记 %d 条（含 %d 个账户）" % (len(recs), len(set(r["account"] for r in recs))))
        print("估算真标签总数: %d" % sum(max(0, r["real"]) for r in recs))
        print("标签行仍是死文本的笔记: %d" % len(dead))
        for n in dead[:30]:
            print("   %-10s %-30s %s" % (n["folder"], n["name"][:30].replace("\n", " "),
                                          tagline_candidate(n["txt"], vocab)[1][:50]))
        if a.dead_ids:
            open(a.dead_ids, "w", encoding="utf-8").write("\n".join(n["id"] for n in dead) + "\n")
            print("已写出 %s" % a.dead_ids)

    elif a.cmd == "tags":
        for t in list_tags(a.id): print(t)

    elif a.cmd == "activate":
        vocab = load_vocab(a.vocab)
        run_batch(load_ids(a.ids), lambda n: activate(n, vocab, a.scan_back), a.log, "激活")

    elif a.cmd == "export":
        recs = scan(os.path.abspath(a.scan_out))
        ns, nt = export_for_tagging(recs, a.out, a.max_chars,
                                    skip_sensitive=not a.include_sensitive,
                                    exclude_folders=set(a.exclude_folder),
                                    only_untagged=not a.include_tagged)
        n = sum(1 for _ in open(a.out, encoding="utf-8"))
        print("已导出 %d 条到 %s" % (n, a.out))
        print("跳过：已有真标签 %d 条，疑似含凭据 %d 条%s"
              % (nt, ns, "（用 --include-sensitive 可包含）" if ns else ""))
        print("下一步：读这个文件，写一份 分配表（每行 note-id<TAB>#标签1 #标签2），再跑 apply")

    elif a.cmd == "apply":
        pairs = load_map(a.map)
        print("分配表 %d 条" % len(pairs))
        if a.dry_run:
            for nid, tags in pairs[:20]: print("  %s -> %s" % (nid[-8:], " ".join(tags)))
            print("(--dry-run，未改动任何笔记)"); return
        log = open(a.log, "a", encoding="utf-8", buffering=1)
        ok = fail = consec = 0
        for k, (nid, tags) in enumerate(pairs, 1):
            try:
                n = add_tags(nid, tags, a.mode); ok += 1; consec = 0
                log.write("OK\t%s\t%s\n" % (nid, " ".join(tags)))
            except Skip as e:
                consec = 0
                log.write("SKIP\t%s\t%s\n" % (nid, e)); print("SKIP", nid[-8:], e)
            except (Fail, Hang) as e:
                fail += 1; consec += 1
                log.write("FAIL\t%s\t%s\n" % (nid, e)); print("FAIL", nid[-8:], e)
                if consec >= 5: print("连续 5 条失败，停止。"); break
            if k % 20 == 0: print("%d/%d ok=%d fail=%d" % (k, len(pairs), ok, fail), flush=True)
        print("打标签完成：ok=%d fail=%d" % (ok, fail))

    elif a.cmd == "remove":
        tags = [t.strip() for t in a.tags.split(",") if t.strip()]
        run_batch(load_ids(a.ids), lambda n: remove_tags(n, tags), a.log, "删除")

    elif a.cmd == "add":
        tags = [t.strip() for t in a.tags.split(",") if t.strip()]
        tags = [t if t.startswith("#") else "#" + t for t in tags]
        run_batch(load_ids(a.ids), lambda n: add_tags(n, tags, a.mode), a.log, "追加")

if __name__ == "__main__":
    main()
