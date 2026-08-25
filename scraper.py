# coding:utf-8
"""
Scraper that:
- Moves existing YYYY-MM-DD.md files in the repo root into YYYY/ subfolders (archive migration).
- Creates today's YYYY-MM-DD.md inside the year folder, appends scraped trending repos.
- Commits and pushes changes if there are any.

Notes:
- The workflow must checkout with persist-credentials: true and the workflow must have
  permissions: contents: write (see .github/workflows/schedule.yml).
- The script uses the runner's git configuration to push. On GitHub Actions the default
  credentials (GITHUB_TOKEN) will be used if persist-credentials is enabled.
"""

import datetime
import codecs
import requests
import os
import time
import re
import shutil
import subprocess
from pyquery import PyQuery as pq

DATE_FILENAME_RE = re.compile(r'^(\d{4})-\d{2}-\d{2}\.md$')


def move_existing_date_files():
    """
    Move files in repo root matching YYYY-MM-DD.md into folder YYYY/YYYY-MM-DD.md.
    Skip files already inside a YYYY/ folder.
    """
    moved = []
    for name in os.listdir('.'):
        if os.path.isdir(name):
            continue
        m = DATE_FILENAME_RE.match(name)
        if m:
            year = m.group(1)
            dest_dir = os.path.join('.', year)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)
            dest_path = os.path.join(dest_dir, name)
            # If destination already exists, skip (avoid overwriting)
            if os.path.exists(dest_path):
                print(f"Skip moving {name} -> {dest_path} (already exists)")
                continue
            shutil.move(name, dest_path)
            moved.append((name, dest_path))
            print(f"Moved {name} -> {dest_path}")
    if not moved:
        print("No root date files to move.")
    return moved


def git_has_changes():
    try:
        out = subprocess.check_output(['git', 'status', '--porcelain'], stderr=subprocess.DEVNULL)
        return bool(out.strip())
    except Exception as e:
        print("git status failed:", e)
        return False


def git_add_commit_push(message):
    # Configure git user if not set
    try:
        # Only set name/email for this repo run to avoid global changes
        subprocess.run(['git', 'config', 'user.name', 'github-trending'], check=True)
        subprocess.run(['git', 'config', 'user.email', 'trending@github.com'], check=True)
    except Exception as e:
        print("git config failed:", e)

    try:
        subprocess.run(['git', 'add', '-A'], check=True)
        # If nothing to commit, git commit will fail; guard with status check
        if not git_has_changes():
            print("No changes to commit.")
            return False

        subprocess.run(['git', 'commit', '-m', message], check=True)
        # push using default remote & branch configured by checkout action (persist-credentials true)
        subprocess.run(['git', 'push'], check=True)
        print("Pushed changes.")
        return True
    except subprocess.CalledProcessError as e:
        print("Git command failed:", e)
        return False


def create_markdown(date, filename):
    # ensure parent dir exists
    parent = os.path.dirname(filename)
    if parent and not os.path.exists(parent):
        os.makedirs(parent)
    # write header with utf-8 encoding
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("## " + date + "\n")


def scrape(language, filename):
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (compatible; GitHub-Trending-Scraper/1.0)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8'
    }

    # encode language for URL (some languages like 'c++' contain '+')
    from urllib.parse import quote
    lang_for_url = quote(language) if language else ''
    url = f'https://github.com/trending/{lang_for_url}?since=daily'
    print("Fetching", url)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    d = pq(r.content)
    items = d('div.Box article.Box-row')

    # append items to file with utf-8
    with codecs.open(filename, "a", "utf-8") as f:
        f.write('\n#### {language}\n'.format(language=language or 'all'))
        for item in items:
            i = pq(item)
            title = i(".lh-condensed a").text()
            owner = i(".lh-condensed span.text-normal").text()
            description = i("p.col-9").text()
            url_path = i(".lh-condensed a").attr("href")
            if url_path:
                url_full = "https://github.com" + url_path
            else:
                url_full = ""
            # write line
            f.write(u"* [{title}]({url_full}): {description}\n".format(title=title, url_full=url_full, description=description))


def job():
    # First, migrate existing root date files into year folders
    move_existing_date_files()

    now = datetime.datetime.now()
    strdate = now.strftime('%Y-%m-%d')
    year = now.strftime('%Y')
    dirpath = year
    if not os.path.exists(dirpath):
        os.makedirs(dirpath)
    filename = os.path.join(dirpath, f'{strdate}.md')

    # create markdown header
    create_markdown(strdate, filename)

    # scrape languages (list can be adjusted)
    languages = [
        '', 'python', 'swift', 'go', 'c', 'c++', 'zig', 'c#', 'rust', 'dart',
        'svelte', 'javascript', 'typescript', 'objective-c', 'objective-c++',
        'crystal', 'v', 'd', 'java'
    ]

    for lang in languages:
        try:
            scrape(lang, filename)
            # polite delay between requests
            time.sleep(1)
        except Exception as e:
            print(f"Error scraping {lang}: {e}")

    # Commit & push if there are changes
    commit_message = now.strftime('%Y-%m-%d')
    if git_has_changes():
        git_add_commit_push(commit_message)
    else:
        print("No repository changes to commit after scraping.")


if __name__ == '__main__':
    job()
