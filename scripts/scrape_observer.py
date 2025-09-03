# Repo structure

```
/
  index.html
  scripts/
    scrape_observer.py
  .github/
    workflows/
      fetch-results.yml
  data/            # created automatically by the workflow
```

---

## index.html

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Jamaica Election 2025 — Live Results</title>
  <style>
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
    header { padding: 12px 16px; border-bottom: 1px solid #ccc; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    h1 { margin: 0; font-size: 1.1rem; }
    .links a { margin-right: 12px; }
    .grid { display: grid; gap: 12px; padding: 12px; grid-template-columns: 1fr; }
    @media (min-width: 980px) { .grid { grid-template-columns: 1fr 1fr; } }
    .card { border: 1px solid #ccc; border-radius: 14px; overflow: hidden; background: rgba(0,0,0,0.02); }
    .title { padding: 10px 12px; font-weight: 600; border-bottom: 1px solid #ddd; }
    .frame { width: 100%; height: 78vh; border: 0; }
    .note { padding: 10px 12px; font-size: 0.9rem; border-top: 1px solid #ddd; }
    a { color: inherit; }
  </style>
</head>
<body>
  <header>
    <h1>Jamaica General Election — Live Tracking</h1>
    <nav class="links">
      <a href="https://www.ecj.com.jm/live-election-results/" target="_blank" rel="noopener">Open ECJ</a>
      <a href="https://election.jamaicaobserver.com/2025/" target="_blank" rel="noopener">Open Observer</a>
    </nav>
  </header>
  <main class="grid">
    <section class="card">
      <div class="title">Official: Electoral Commission of Jamaica</div>
      <iframe class="frame" src="https://www.ecj.com.jm/live-election-results/"></iframe>
      <div class="note">If the embed is blocked by the site, use the “Open ECJ” link above.</div>
    </section>

    <section class="card">
      <div class="title">Media: Jamaica Observer — Results</div>
      <iframe class="frame" src="https://election.jamaicaobserver.com/2025/"></iframe>
      <div class="note">If the embed is blocked by the site, use the “Open Observer” link above.</div>
    </section>
  </main>
  <noscript>
    JavaScript is disabled. Use the links in the header to open the live results.
  </noscript>
</body>
</html>
```

---

## .github/workflows/fetch-results.yml

```yaml
name: Fetch election results
on:
  schedule:
    - cron: "*/5 * * * *"   # every 5 minutes
  workflow_dispatch:
permissions:
  contents: write
jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install requests beautifulsoup4 lxml
      - name: Scrape media page for tabular data
        run: python scripts/scrape_observer.py
      - name: Commit data artifacts
        run: |
          git config user.name "github-actions"
          git config user.email "actions@users.noreply.github.com"
          git add -A
          git commit -m "auto: update results" || exit 0
          git push
```

---

## scripts/scrape\_observer.py

```python
#!/usr/bin/env python3
"""
Scrapes a public media results page and writes JSON + CSV.
Safe Python 3 syntax. Avoids fancy constructs that can trigger copy/paste issues.
"""
import csv
import json
import time
import pathlib
import sys

try:
    import requests
    from bs4 import BeautifulSoup
except Exception as e:
    # Keep the workflow green but record the error
    sys.stderr.write(f"Missing deps: {e}
")
    sys.exit(1)

URL = "https://election.jamaicaobserver.com/2025/"
OUTDIR = pathlib.Path("data")
OUTDIR.mkdir(parents=True, exist_ok=True)

FIELDS = [
    "constituency",
    "parish",
    "candidate",
    "party",
    "votes",
    "percent",
    "status",
    "boxes",
]

def fetch_html(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text

def parse_rows(html: str):
    """Heuristic parse. If structure changes, returns []."""
    soup = BeautifulSoup(html, "lxml")
    rows = []

    # Look for any text node that signals a detailed table section
    anchors = [
        "Detailed Results by Constituency",
        "Constituency Results",
    ]
    anchor = None
    for label in anchors:
        anchor = soup.find(string=lambda s: isinstance(s, str) and label in s)
        if anchor:
            break

    if not anchor:
        return rows

    stop_markers = ("Follow Us", "Connect With Us", "Mobile Apps", "©")
    status_tokens = ("Not Started", "Counting", "Declared")

    for node in anchor.find_all_next(text=True):
        s = (node or "").strip()
        if not s:
            continue
        if any(m in s for m in stop_markers):
            break
        if any(tok in s for tok in status_tokens):
            parts = [p for p in s.split("  ") if p]
            if len(parts) >= 8:
                rows.append({
                    "constituency": parts[0],
                    "parish": parts[1],
                    "candidate": parts[2],
                    "party": parts[3],
                    "votes": parts[4],
                    "percent": parts[5].replace("%", ""),
                    "status": parts[6],
                    "boxes": parts[7],
                })

    return rows

def write_artifacts(rows):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {"source": URL, "fetched_at": ts, "rows": rows}

    (OUTDIR / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with (OUTDIR / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})

    print(f"Saved {len(rows)} rows at {ts}")


def main():
    try:
        html = fetch_html(URL)
        rows = parse_rows(html)
    except Exception as e:
        # Emit empty artifacts with error info in JSON
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (OUTDIR / "results.json").write_text(
            json.dumps({"source": URL, "fetched_at": ts, "rows": [], "error": str(e)}, indent=2),
            encoding="utf-8",
        )
        with (OUTDIR / "results.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
        print(f"Error: {e}")
        return 0

    write_artifacts(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
