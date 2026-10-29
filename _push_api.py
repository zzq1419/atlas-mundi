# -*- coding: utf-8 -*-
"""在 git 走不了代理时，用 GitHub 数据 API 把本地改动合成一个 commit 推上去。

为什么不走 Contents API 逐个文件：13 个文件就是 13 个 commit，Pages 会
每个 commit 触发一次构建，白排队。这里走 blob → tree(base_tree) → commit
→ patch ref，一次提交只产生一个 commit、一次构建。

用法：python _push_api.py "提交说明"
读 `git show --name-only HEAD` 的文件清单（即最近一次本地提交改了什么）。
"""
import base64
import json
import os
import re
import subprocess
import sys
import urllib.request

OWNER, REPO, BRANCH = "zzq1419", "atlas-mundi", "main"
API = "https://api.github.com"
ROOT = os.path.dirname(os.path.abspath(__file__))


def token():
    p = os.path.expanduser("~/.git-credentials")
    for line in open(p, encoding="utf-8"):
        m = re.match(r"https://(zzq1419):([^@]+)@github", line.strip())
        if m:
            return m.group(2)
    raise SystemExit("找不到可用的 GitHub token")


TOKEN = token()


def call(method, path, payload=None, ok=(200, 201)):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise SystemExit("%s %s → %s\n%s" % (method, path, e.code, detail))


def changed_files():
    out = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    return [x.strip() for x in out.splitlines() if x.strip()]


def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else "chore: 同步"
    files = changed_files()
    if not files:
        print("最近一次提交没有改动文件")
        return 1
    print("待推送 %d 个文件" % len(files))

    ref = call("GET", "/repos/%s/%s/git/ref/heads/%s" % (OWNER, REPO, BRANCH))
    head_sha = ref["object"]["sha"]
    head = call("GET", "/repos/%s/%s/git/commits/%s" % (OWNER, REPO, head_sha))
    base_tree = head["tree"]["sha"]
    print("远程 HEAD %s" % head_sha[:8])

    entries = []
    for i, f in enumerate(files, 1):
        path = os.path.join(ROOT, f.replace("/", os.sep))
        if not os.path.exists(path):
            print("  [跳过] %s（本地不存在，可能是删除）" % f)
            entries.append({"path": f, "mode": "100644", "type": "blob", "sha": None})
            continue
        raw = open(path, "rb").read()
        blob = call("POST", "/repos/%s/%s/git/blobs" % (OWNER, REPO), {
            "content": base64.b64encode(raw).decode(),
            "encoding": "base64",
        })
        entries.append({"path": f, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print("  [%d/%d] %-24s %6.0f KB" % (i, len(files), f, len(raw) / 1024))

    tree = call("POST", "/repos/%s/%s/git/trees" % (OWNER, REPO), {
        "base_tree": base_tree,
        "tree": entries,
    })
    commit = call("POST", "/repos/%s/%s/git/commits" % (OWNER, REPO), {
        "message": msg,
        "tree": tree["sha"],
        "parents": [head_sha],
    })
    call("PATCH", "/repos/%s/%s/git/refs/heads/%s" % (OWNER, REPO, BRANCH),
         {"sha": commit["sha"]})
    print("\n已推送 %s → %s" % (head_sha[:8], commit["sha"][:8]))
    print("注意：本地与远程历史已分叉，网络恢复后执行")
    print("  git fetch origin main && git reset --soft FETCH_HEAD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
