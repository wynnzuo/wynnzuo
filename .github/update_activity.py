#!/usr/bin/env python3
"""把 owner 在全部公开仓库的最近活动写进 README 的 activity 标记区。

使用 GitHub 公开 Events API（github token 只用于提高限流额度），
无需额外 secret。每小时由 GitHub Actions 调用一次。
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

USER = os.environ.get("GITHUB_REPOSITORY_OWNER", "wynnzuo")
README = os.environ.get("README_PATH", "README.md")
MAX_LINES = int(os.environ.get("MAX_LINES", "6"))
TOKEN = os.environ.get("GITHUB_TOKEN", "")

START = "<!--START_SECTION:activity-->"
END = "<!--END_SECTION:activity-->"

# 有意义的动态类型；WatchEvent(star)、ForkEvent 等噪音过滤掉
PUSH = "PushEvent"
CREATE = "CreateEvent"
ISSUES = "IssuesEvent"
PR = "PullRequestEvent"
RELEASE = "ReleaseEvent"


def fetch_events():
    url = f"https://api.github.com/users/{USER}/events/public?per_page=100"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "gh-readme-activity"}
    if TOKEN:
        headers["Authorization"] = f"token {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except Exception as exc:  # 网络 / 限流等：记录后跳过本次，等下次调度
        print(f"warning: 获取 {USER} 的公开事件失败，本次不更新: {exc}")
        return []


def fmt_date(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return dt.astimezone().strftime("%Y-%m-%d")


def render(events):
    lines = []
    seen = set()
    for ev in events:
        if len(lines) >= MAX_LINES:
            break
        etype = ev.get("type")
        repo = (ev.get("repo") or {}).get("name", "")
        if not repo or repo == f"{USER}/{USER}":  # 跳过 profile 仓库自身的提交
            continue
        link = f"[{repo}](https://github.com/{repo})"
        day = fmt_date(ev.get("created_at", ""))
        payload = ev.get("payload") or {}

        if etype == PUSH:
            key = (repo, day)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {day} 提交到 {link}")

        elif etype == CREATE:
            ref = payload.get("ref", "")
            if payload.get("ref_type") == "repository":
                lines.append(f"- {day} 创建了仓库 {link}")
            elif ref:
                label = "创建了分支" if payload.get("ref_type") == "branch" else "打了标签"
                lines.append(f"- {day} 在 {link} {label} `{ref}`")

        elif etype == ISSUES:
            action = payload.get("action")
            number = (payload.get("issue") or {}).get("number")
            if action and number:
                lines.append(f"- {day} 在 {link} {action} issue #{number}")

        elif etype == PR:
            action = payload.get("action")
            number = (payload.get("pull_request") or {}).get("number")
            if action and number:
                lines.append(f"- {day} 在 {link} {action} PR #{number}")

        elif etype == RELEASE:
            tag = (payload.get("release") or {}).get("tag_name", "")
            if tag:
                lines.append(f"- {day} 发布了 {link} `{tag}`")
    return lines


def main():
    if not os.path.exists(README):
        print(f"error: 找不到 {README}")
        sys.exit(1)
    with open(README, encoding="utf-8") as f:
        content = f.read()
    if START not in content or END not in content:
        print(f"error: {README} 缺少 activity 标记区")
        sys.exit(1)

    lines = render(fetch_events())
    body = "\n".join(lines) + "\n" if lines else ""
    updated = content[: content.index(START) + len(START)] + "\n" + body + content[content.index(END):]
    if updated != content:
        with open(README, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"已更新 {len(lines)} 条动态")
    else:
        print("无变更")


if __name__ == "__main__":
    main()
