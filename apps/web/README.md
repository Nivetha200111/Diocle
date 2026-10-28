# Diocle frontend preview

A Next.js workspace for Diocle. **Live runs** shows real repair runs served by `services/api`. Every other view is still a mock with synthetic data and no backend.

## Live runs (real data)

Start the API (see `services/api/README.md`), then open **Live runs**. The page reads `NEXT_PUBLIC_DIOCLE_API_URL` (default `http://localhost:8000`) and shows each saved run: before/after pass rates, the agent's tool trace, the failing cases, the Java diff, and token cost.

## Theme

`app/retro.css` (loaded after `globals.css` in `app/layout.tsx`) gives the app a Windows 9x / IBM 3270 look. Remove that import to return to the original theme.

## Run locally

Requires Node.js 20.9 or newer.

```sh
cd apps/web
npm install
npm run dev
```

Open [localhost:3000](http://localhost:3000).

```sh
npm run typecheck
npm run build
npm start
```

## Explore the mock

- **Overview:** migration summaries, synthetic metrics, recent activity, a dependency graph, and verification overview.
- **Migrations:** search, filter by state, open migration details, and inspect synthetic source programs.
- **New migration:** select or drag COBOL/copybook files, or load a synthetic sample, to create a local mock run with animated progress. Only file names are read; file contents are never uploaded, parsed, or converted.
- **Dependency graph:** inspect programs/copybooks, follow CALL/COPY edges, and zoom the graph.
- **Risk findings:** filter priority, expand source context, mark findings reviewed, and reopen them.
- **Conversions:** compare handwritten COBOL/Java, copybook/SQL, and test examples; download illustrative output files.
- **Verification:** filter sample matching/mismatching output cases and export a sample report.
- **Reports:** download migration summaries as JSON with explicit mock labels.
- **Settings:** edit the local workspace name and reset the demo.
- **Search:** use the header search or `Cmd/Ctrl + K` to find pages and migrations.

All state lives in memory and resets on refresh. New migrations simulate pipeline progress; completing the animation does not mean any real analysis, conversion, compilation, or testing took place. Downloaded reports explicitly include `mock: true` and a disclaimer.

The model name in the UI describes the planned Muse Spark / Meta Model API integration. There are no LLM calls, credentials, API endpoints, or backend implementation in this mock. The existing contracts are unchanged.

## Structure

- `app/`: App Router entry point, global styling, and metadata.
- `components/workspace.tsx`: workspace views and local interactions.
- `components/dependency-graph.tsx`: interactive SVG dependency graph.
- `components/ui.tsx`: shared accessible dialogs, status badges, and pipeline controls.
- `lib/demo.ts`: synthetic fixtures and clearly labeled sample downloads.

DM Sans is bundled locally through `@fontsource-variable/dm-sans`. No external image or font services are needed to render the interface.
