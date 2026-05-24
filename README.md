# Repo to Architecture Mapper

A small web tool that takes a public GitHub URL and gives you back an
interactive dependency graph, a list of all dependency manifests with their
contents, and inferred setup docs. No accounts, no AI, no waiting.

I made this because I kept opening unfamiliar repos and wanting a fast way
to get my bearings without scrolling through fifty files. It's a quick
sketch, not a deep static analyzer.

## Try it

If you've already deployed your own copy, that's it — just open your Vercel
URL, paste a GitHub repo URL, and click Analyze.

## Deploy your own copy

The whole thing is one static page plus a single Python serverless
function. It deploys to Vercel in about a minute.

1. Fork or clone this repo to your own GitHub account.
2. Go to <https://vercel.com/new>, import the repo, and accept the defaults.
   Vercel will detect the static files and the Python function automatically.
3. Visit the deployment URL.

There are no environment variables to set and no API keys required. The
default Vercel hobby plan is enough.

If you want to bump GitHub's rate limit (60 requests per hour without a
token, 5,000 with one), the UI has an optional GitHub token field on the
left — paste a personal access token from
<https://github.com/settings/tokens>. No scopes are required for public
repos.

## Run it locally

You need Python 3.9+ and the Vercel CLI (`npm i -g vercel`).

```bash
pip install -r requirements.txt
vercel dev
```

That serves the static page and the Python function on the same port. Open
the URL it prints (usually <http://localhost:3000>).

## How to use it

1. Paste a GitHub URL into the sidebar.
2. Optionally paste a GitHub token.
3. Pick how many source files to fetch (default 60) and how coarse the
   graph should be (depth slider).
4. Click Analyze.

You'll get five tabs:

- **Summary** — language breakdown, top-level layout, manifest count, and
  the most-imported internal modules per language.
- **Dependency graph** — one interactive graph per language detected.
  Hover a node for its in/out import counts; drag to rearrange.
- **Setup docs** — install / build / run commands inferred from the
  manifests, plus any "Setup" or "Getting Started" sections pulled from
  the repo's own README. Downloadable as `SETUP.md`.
- **Manifests** — every dependency manifest with its full dep list and
  (for `package.json`) scripts.
- **Raw context** — the full structured-facts blob, useful if you want to
  pipe it somewhere else.

## How it works

- The frontend posts your inputs to `/api/analyze`.
- The serverless function uses the GitHub REST API to fetch the file tree,
  the dependency manifests, the README, and a capped sample of source
  files (default 60).
- It parses manifests for Python, JavaScript / TypeScript, Java / Kotlin,
  Go, Rust, and Ruby.
- It parses internal imports for Python (via the `ast` module),
  JavaScript / TypeScript (regex on `import` and `require`), and
  Java / Kotlin (`package` and `import` lines), then builds a directed
  module graph and returns it as JSON.
- The frontend renders the graph with `vis-network` and the setup docs
  with `marked`.

The function only forwards your inputs to GitHub. No analytics, no
storage, no third-party calls beyond GitHub itself.

## What it doesn't do

- Internal-import parsing only covers Python, JS / TS, Java, and Kotlin.
  Go, Rust, and Ruby get manifest parsing but no module graph.
- JS / TS path resolution is relative-only — `tsconfig` path aliases and
  webpack / vite resolvers are ignored.
- Java edges are package-level, not class-level.
- Source-file fetching is capped (default 60). For large monorepos, raise
  the cap or analyze a smaller sub-path if you can.
- Very large repos may hit GitHub's tree-truncation limit. The app will
  tell you when that happens; results are best-effort in that case.

If you need real static analysis, reach for a language-specific tool
(`pylint`, `madge`, `jdeps`, and so on).

## Layout

```
.
├── index.html       Frontend page
├── app.js           Frontend logic (vanilla JS)
├── styles.css       Styling
├── api/
│   └── analyze.py   Vercel Python serverless function
├── analyzer/        Reusable parsing modules
│   ├── github.py
│   ├── manifests.py
│   ├── imports.py
│   ├── graph.py
│   ├── setup_docs.py
│   └── context.py
├── vercel.json
├── requirements.txt
└── LICENSE
```

## License

MIT. See [LICENSE](LICENSE).
