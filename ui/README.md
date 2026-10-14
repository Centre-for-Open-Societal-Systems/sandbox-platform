# OAN Sandbox Frontend

Web client for the **Open Agri Net (OAN)** developer sandbox. Built with
Next.js 16 (App Router, Turbopack), React 19.3, TypeScript and Tailwind CSS 4.

It serves three audiences from one codebase:

| Area | Route prefix | Audience |
| --- | --- | --- |
| Public site | `/` | Anyone — marketing pages, API catalogue, FAQs, terms |
| Participant portal | `/participant` | Registered organisations and developers |
| Admin console | `/admin` | Network operators |

## Structure

```
src/
  app/
    (public)/        marketing pages, catalogue, FAQs, terms
    admin/
      login/         sign-in, outside the console shell
      (console)/     authenticated console with sidebar layout
    participant/
      login/         sign-in and registration, outside the portal shell
      register/
      (portal)/      authenticated portal with header navigation
  components/
    ui/              primitives and shared admin building blocks (see below)
    layout/          site header/footer, admin sidebar
    portal/          api-explorer-nav (left API menu of the try-it console)
  lib/
    api-client.ts    fetch wrapper, envelope unwrapping, ApiError
    session.ts       admin and participant session storage
    services/        one module per API area
    config.ts        environment-derived runtime config
    permissions.ts   console permission ids, mirroring the backend
  hooks/             use-list-query (grid state), use-hydrated (read browser storage safely)
  types/api.ts       API response types
```

### Data fetching

- **Public pages** fetch on the server with `revalidate`, so they render
  without JavaScript and stay fast. Each falls back to sensible defaults if the
  API is unreachable — a marketing page that vanishes when the backend is down
  is worse than one showing static copy.
- **Portal and console** fetch on the client through TanStack Query, keyed by
  the grid's query object so paging, sorting and filtering refetch naturally.

### Sessions

Two independent sessions, never mixed:

- **Admin** — `sessionStorage`, so closing the tab ends the session.
- **Participant** — `localStorage`, so developers stay signed in between visits.

Both send `x-access-token` and `x-auth-key`. A 401 clears the stored session so
the user is redirected to sign-in rather than left in a broken state.

### Permissions

`lib/permissions.ts` mirrors the backend's permission ids. The sidebar hides
what the signed-in admin cannot open, but the backend enforces access
independently — the client-side check is convenience, not security.

## Getting started

The API must be running first (see `../backend`).

```bash
npm install
copy .env.example .env.local     # point NEXT_PUBLIC_API_BASE_URL at your API
npm run dev
```

Then open <http://localhost:3005> (run with `npm run dev -- -p 3005`; the API allows that origin by default).

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | API base including the `/oan` prefix |
| `NEXT_PUBLIC_DEFAULT_COUNTRY` | ISO-3166 alpha-2 code this deployment serves |
| `NEXT_PUBLIC_SITE_NAME` | Name shown in the header and page titles |

These are inlined at build time, so a container image is bound to the API URL
it was built with. Rebuild when it changes.

## Commands

| Task | Command |
| --- | --- |
| Development server | `npm run dev` |
| Production build | `npm run build` |
| Serve the build | `npm run start` |
| Lint | `npm run lint` |
| Type check | `npm run typecheck` |

## Admin console design

The console follows the admin template of `etp-registry-portal-frontend`
(light only, Roboto). Every admin page is built from the same shared pieces,
so screens look and behave the same. **Do not add text-only row buttons.**

| Component | File | Use |
| --- | --- | --- |
| `PageHeader` (+ `SearchBox`, `FilterBar`, `FilterField`) | `components/ui/page-header.tsx` | breadcrumb, title, search and primary action; mint filter strip |
| `DataTable` | `components/ui/data-table.tsx` | mint header, striped rows, automatic "Sr. No." column, sortable headers |
| `Pagination` | `components/ui/pagination.tsx` | "Showing x–y of z", « ‹ 1 … n › », rows per page, page jump |
| `RowActions`, `IconAction` | `components/ui/row-actions.tsx` | 32 px green icon buttons in the fixed order view · edit · extras · delete · status |
| `StatusToggle` | `components/ui/status-toggle.tsx` | active/inactive or publish switch |
| `useConfirm` / `ConfirmDialog` | `components/ui/confirm-dialog.tsx` | confirmation before delete / deactivate |
| `Badge`, `StatusCodeBadge`, `MethodBadge`… | `components/ui/badge.tsx`, `status-badge.tsx` | square status chips in the template tones |

Layout (`app/admin/(console)/layout.tsx`): 256 px sidebar that collapses to a
74 px icon rail (remembered in `localStorage`), mobile drawer below 768 px,
"Welcome, name" top bar with user menu. Layering: header 55, dialogs 60,
drawer/flyouts 1100+, toasts 2000.

Design tokens live in `app/globals.css` (`--color-brand-*`, `ink`, `subtle`,
`hairline`, `surface-soft`, `sidebar-bg`, `table-head`, `nav-active`, `action`).

## Participant portal design

Standard API developer portal:
- **Header:** logo + SANDBOX tag, Dashboard / API Catalogue / API History, an
  environment pill, and an avatar dropdown with My Profile, Change Password
  (`/participant/profile#change-password`) and Logout. A footer sits under every page.
- **Dashboard:** welcome banner, stat tiles, getting-started checklist,
  environment access cards (request / re-apply), usage chart.
- **API Catalogue:** products and categories on the left; end-points with "Try it" on the right.
- **Console** (`/participant/catalog/{endpointId}`):
  - an `ApiExplorerNav` API menu on the left;
  - a request bar (method, path, environment, Send);
  - Body / Headers / Params tabs;
  - a response panel showing status, time and size;
  - code samples in 7 languages and response samples per status code.
  - The console is keyed by end-point, so switching APIs starts fresh from that end-point's sample.
- **API History:** filters, and a call-details dialog with Overview / Request / Response
  plus "Open in console".

## Versions and upgrade notes

Next.js 16.3.7 (Turbopack), React 19.3, TypeScript 6.0.3, ESLint 9, Tailwind 4.3.
- **TypeScript stays on 6.0:** `typescript-eslint` supports TypeScript up to 6.0.
- **ESLint stays on 9:** Next's lint plugins do not support ESLint 10 yet.
- **Lint command:** `next lint` no longer exists; `npm run lint` runs `eslint`
  with the flat config in `eslint.config.mjs`.
- **State in effects:** the React hooks rules forbid setting state inside
  effects. Derive the value during render, set it in the event handler, or read
  browser storage through `useHydrated`.
- **AGENTS.md / CLAUDE.md:** `next dev` rewrites these on every start. Setting
  `agentRules: false` in `next.config.ts` stops it.
## Theming

Colours are CSS custom properties in `app/globals.css`, defined once on
`:root` and redefined under `prefers-color-scheme: dark`. To rebrand, change
the `--color-brand-*` scale — components reference the tokens, never raw
colour values.

## Adding a console screen

1. Add the permission id to `lib/permissions.ts` (matching the backend).
2. Add the route to `NAV_SECTIONS` in `components/layout/admin-sidebar.tsx`.
3. Create the page under `app/admin/(console)/`.
4. Add the API calls to the matching module in `lib/services/`.

Reuse `useListQuery`, `PageHeader`, `DataTable` and `RowActions` for any grid — they already
handle paging, sorting, debounced search, row actions and the empty and loading states.
