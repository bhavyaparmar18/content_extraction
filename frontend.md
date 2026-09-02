# SOP Dashboard and Extraction Review Design

This document describes the current SOP dashboard and the review page pattern used by the GP-DAT frontend. It is intended as the implementation reference for an SOP extraction review experience.

## Pages

| Page | Route | Source |
| --- | --- | --- |
| SOP dashboard | `/gpdocs` | [src/pages/Dashboard.tsx](../src/pages/Dashboard.tsx) |
| Migration review pattern | `/migration/review` | [src/pages/MigrationReview.tsx](../src/pages/MigrationReview.tsx) |
| Application routes | N/A | [src/App.tsx](../src/App.tsx) |

The migration review page is the current reference for the SOP extraction review layout: a page header, a left document list, a section list, and a right content/diff panel.

## Design Direction

- Use the existing dark GP-DAT theme by default.
- Use green for primary actions and active navigation.
- Use blue for extracted or added content.
- Use red for deleted content and destructive actions.
- Use sky blue for confidence and informational scores.
- Keep cards compact, bordered, and scannable. The shared `.dashboard-card` class is the base surface.
- Use Lucide icons inside controls.
- Keep the page responsive: the two-column review layout becomes stacked on smaller screens.

## Global Design Tokens

The source of truth is [src/styles/globals.css](../src/styles/globals.css).

### Dark theme

```css
:root,
[data-theme="dark"] {
  --primary: #00E47C;
  --primary-dark: #00C86D;
  --bg-main: #08312A;
  --bg-card: #0A3D34;
  --text-main: #FFFFFF;
  --text-muted: #94A3B8;
  --border: rgba(255, 255, 255, 0.06);
  --sidebar-bg: #062621;
  --nav-active-bg: rgba(0, 228, 124, 0.15);
  --button-bg: var(--primary);
  --button-text: #1f1f1f;
}
```

### Light theme

```css
[data-theme="light"] {
  --primary: #169949;
  --primary-dark: #00C86D;
  --bg-main: #ffffff;
  --bg-card: #f8f8f8;
  --text-main: #0F172A;
  --text-muted: #3A474E;
  --border: #E2E8F0;
  --sidebar-bg: #FFFFFF;
  --nav-active-bg: rgba(0, 228, 124, 0.1);
}
```

### Shared card and button styles

```css
@layer components {
  .dashboard-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    transition: all 200ms ease;
  }

  .btn-primary {
    background: var(--primary);
    color: var(--button-text);
    font-weight: 600;
    border-radius: 0.5rem;
  }

  .btn-primary:hover {
    background: var(--primary-dark);
  }
}
```

The reusable React button is [src/components/ui/Button.tsx](../src/components/ui/Button.tsx). It supports `primary`, `ghost`, and `icon` variants and adds focus and disabled states.

Example:

```tsx
<Button onClick={handleApprove} className="!bg-[var(--primary)] !text-[#08312A]">
  <Check size={16} />
  Approve
</Button>

<Button
  variant="ghost"
  onClick={handleReject}
  className="border border-red-400/30 !text-red-300 hover:!bg-red-400/10"
>
  <X size={16} />
  Reject
</Button>
```

## SOP Dashboard Page

The dashboard is implemented in [src/pages/Dashboard.tsx](../src/pages/Dashboard.tsx). It currently provides:

- SOP loading through `getSops()`.
- Duplicate SOP id filtering.
- Search by title, filename, or document number.
- List and grid views.
- Status KPI cards.
- Pagination with eight documents per page.
- Delete and duplicate-version workflows.
- Expandable SOP content loaded through `getSopDetail()`.
- `DocumentCard` rendering through [src/components/DocumentCard.tsx](../src/components/DocumentCard.tsx).

### Dashboard data flow

```tsx
const [documents, setDocuments] = useState<any[]>([]);
const [search, setSearch] = useState('');
const [viewMode, setViewMode] = useState<ViewMode>('list');
const [expandedContents, setExpandedContents] = useState<Record<string, string>>({});

useEffect(() => {
  fetchDocuments();
}, []);

const handleFetchDetail = async (sopId: string) => {
  if (expandedContents[sopId]) return;

  const data = await getSopDetail(sopId);
  setExpandedContents((previous) => ({
    ...previous,
    [sopId]: data?.md_content ?? '',
  }));
};
```

### Dashboard layout pattern

```tsx
<div className="min-h-screen bg-[var(--bg-main)] text-[var(--text-main)]">
  <div className="mx-auto max-w-[1600px] px-4 py-6 md:px-8">
    <header className="flex items-center justify-between gap-3 pb-3">
      <div>
        <div className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-muted)]">
          GP-DAT
        </div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">
          SOP Repository
        </h1>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          Manage and monitor all SOPs in your repository
        </p>
      </div>
    </header>

    <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      {stats.map(({ label, value, icon: Icon }) => (
        <div key={label} className="dashboard-card px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[13px] text-[var(--text-muted)]">{label}</span>
            <Icon size={18} className="text-[var(--primary)]" />
          </div>
          <div className="mt-4 text-3xl font-semibold">{value}</div>
        </div>
      ))}
    </div>

    <div className="dashboard-card mt-6 p-3 sm:p-4">
      <input
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search by SOP title, number, filename, content..."
        className="h-12 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-main)]/70 px-4 text-sm outline-none focus:border-[var(--primary)]/50"
      />
    </div>

    <div className="mt-6 dashboard-card overflow-hidden">
      <div className="space-y-3 p-3">
        {paginatedDocs.map((doc) => (
          <DocumentCard
            key={doc.sop_id}
            doc={doc}
            markdownContent={expandedContents[doc.sop_id]}
            onExpand={() => handleFetchDetail(doc.sop_id)}
            viewMode={viewMode}
            status={getStatusInfo(doc, 0)}
          />
        ))}
      </div>
    </div>
  </div>
</div>
```

### Opening a review page from a dashboard row

For a dedicated SOP extraction review page, use a route such as `/sop-extraction/review/:sopId` and navigate from the selected document:

```tsx
const navigate = useNavigate();

<button
  type="button"
  onClick={() => navigate(`/sop-extraction/review/${doc.sop_id}`)}
  className="inline-flex items-center gap-2 rounded-lg border border-[var(--primary)]/30 bg-[var(--primary)]/10 px-3 py-2 text-xs font-semibold text-[var(--primary)]"
>
  <Eye size={15} />
  Review extraction
</button>
```

## Extraction Review Page Pattern

The current reference implementation is [src/pages/MigrationReview.tsx](../src/pages/MigrationReview.tsx). It uses local mock data until an extraction API is connected.

Its structure is:

1. Header card with page title, migration/extraction id, and Admin-only actions.
2. Left card listing SOP documents.
3. Main card showing the selected SOP.
4. Inner section navigation for that SOP.
5. Content panel with confidence score and line-level changes.

### Review model

```tsx
type DiffLine = {
  type: 'added' | 'deleted' | 'unchanged';
  text: string;
};

type ReviewSection = {
  id: string;
  title: string;
  confidence: number;
  changes: DiffLine[];
};

type ReviewSop = {
  id: string;
  title: string;
  documentNumber: string;
  sections: ReviewSection[];
};
```

### Review state and selection

```tsx
const [selectedSopId, setSelectedSopId] = useState(mockReviews[0].id);
const [selectedSectionId, setSelectedSectionId] = useState(
  mockReviews[0].sections[0].id,
);
const [decision, setDecision] = useState<'approved' | 'rejected' | null>(null);

const selectedSop =
  mockReviews.find((sop) => sop.id === selectedSopId) ?? mockReviews[0];

const selectedSection =
  selectedSop.sections.find((section) => section.id === selectedSectionId) ??
  selectedSop.sections[0];
```

### Review layout

```tsx
<div className="grid gap-5 lg:grid-cols-[minmax(250px,0.32fr)_minmax(0,1fr)]">
  <aside className="dashboard-card h-fit overflow-hidden">
    <div className="border-b border-[var(--border)] px-5 py-4">
      <h2 className="font-semibold">SOPs to review</h2>
      <p className="mt-1 text-xs text-[var(--text-muted)]">
        {mockReviews.length} documents to review
      </p>
    </div>

    <div className="p-2">
      {mockReviews.map((sop) => (
        <button
          key={sop.id}
          onClick={() => selectSop(sop)}
          className={`flex w-full items-start gap-3 rounded-lg p-3 text-left ${
            selectedSop.id === sop.id
              ? 'bg-[var(--primary)]/12 text-[var(--text-main)]'
              : 'text-[var(--text-muted)] hover:bg-white/5'
          }`}
        >
          <FileText size={17} />
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium">{sop.title}</span>
            <span className="mt-1 block text-xs">{sop.documentNumber}</span>
          </span>
          <ChevronRight size={15} />
        </button>
      ))}
    </div>
  </aside>

  <section className="dashboard-card min-w-0 overflow-hidden">
    <div className="border-b border-[var(--border)] px-5 py-4">
      <p className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">
        {selectedSop.documentNumber}
      </p>
      <h2 className="mt-1 text-xl font-semibold">{selectedSop.title}</h2>
    </div>

    <div className="grid md:grid-cols-[minmax(190px,0.32fr)_minmax(0,1fr)]">
      <nav className="border-b border-[var(--border)] p-3 md:border-b-0 md:border-r">
        {selectedSop.sections.map((section) => (
          <button
            key={section.id}
            onClick={() => setSelectedSectionId(section.id)}
            className="flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm"
          >
            {section.title}
            <ChevronRight size={14} />
          </button>
        ))}
      </nav>

      <article className="min-w-0 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Selected section
            </p>
            <h3 className="mt-1 text-lg font-semibold">{selectedSection.title}</h3>
          </div>

          <div className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-right">
            <p className="text-[10px] uppercase tracking-[0.12em] text-sky-300">
              Confidence score
            </p>
            <p className="mt-0.5 text-xl font-semibold text-sky-200">
              {selectedSection.confidence}%
            </p>
          </div>
        </div>

        <div className="mt-5 space-y-2">
          {selectedSection.changes.map((line, index) => (
            <p
              key={`${line.type}-${index}`}
              className={
                line.type === 'added'
                  ? 'border-l-2 border-blue-400 bg-blue-400/10 px-3 py-2 text-blue-200'
                  : line.type === 'deleted'
                    ? 'border-l-2 border-red-400 bg-red-400/10 px-3 py-2 text-red-200 line-through'
                    : 'border-l-2 border-[var(--border)] px-3 py-2 text-[var(--text-muted)]'
              }
            >
              {line.type === 'added' ? '+' : line.type === 'deleted' ? '-' : ' '}
              {line.text}
            </p>
          ))}
        </div>
      </article>
    </div>
  </section>
</div>
```

## Admin-only Actions

The current mock implementation uses `localStorage.userRole`:

```tsx
const isAdmin =
  (window.localStorage.getItem('userRole') ?? 'Admin').toLowerCase() === 'admin';
```

The buttons are rendered only when `isAdmin` is true. This is a UI mock, not an authorization boundary. Production approval and rejection must be validated by the backend using the authenticated user's role.

## Route Setup

Current route registration is in [src/App.tsx](../src/App.tsx):

```tsx
<Route
  path="/gpdocs"
  element={
    <_PageWrapper title="Documents" heading="GP Repository">
      <Dashboard />
    </_PageWrapper>
  }
/>

<Route
  path="/migration/review"
  element={
    <_PageWrapper title="Restructure with AI" heading="Migration Review">
      <MigrationReview />
    </_PageWrapper>
  }
/>
```

An SOP extraction review route can follow the same pattern:

```tsx
const SopExtractionReview = lazy(() =>
  import('./pages/SopExtractionReview').then((module) => ({
    default: module.SopExtractionReview,
  })),
);

<Route
  path="/sop-extraction/review/:sopId"
  element={
    <_PageWrapper title="Documents" heading="SOP Extraction Review">
      <SopExtractionReview />
    </_PageWrapper>
  }
/>
```

## CSS Entry Point

Global CSS is loaded once from [src/main.tsx](../src/main.tsx):

```tsx
import './styles/globals.css';
```

The theme is applied before the React tree renders:

```tsx
applyTheme(getTheme());
```

## Tailwind CSS

Tailwind is configured in [tailwind.config.js](../tailwind.config.js):

```js
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        primary: '#00E47C',
        'primary-dark': '#00C86D',
        'bg-main': 'var(--bg-main)',
        'bg-card': 'var(--bg-card)',
        'text-main': 'var(--text-main)',
        'text-muted': 'var(--text-muted)',
        'sidebar-bg': 'var(--sidebar-bg)',
        'border-col': 'var(--border)',
      },
      fontFamily: {
        sans: ['Inter', 'Poppins', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
```

Use the existing CSS variables in arbitrary Tailwind values when a design token is required:

```tsx
className="bg-[var(--bg-card)] text-[var(--text-main)] border-[var(--border)]"
```

## PostCSS

PostCSS is configured in [postcss.config.js](../postcss.config.js):

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

Tailwind expands utility classes and Autoprefixer adds browser vendor prefixes during the Vite build.

## Vite Development Server

Vite is configured in [vite.config.ts](../vite.config.ts). The frontend uses React and proxies `/api` requests to the backend:

```ts
server: {
  proxy: {
    '/api': {
      target: 'https://backend-gpdat-dev.apps.eu-dev.ocp.aws.boehringer.com',
      changeOrigin: true,
      secure: false,
    },
  },
},
```

Run the development server with:

```bash
npm run dev
```

The default local URL is normally `http://localhost:5173`.

Build the frontend with:

```bash
npm run build
```

The build runs TypeScript first and then Vite:

```json
"build": "tsc && vite build"
```

## Dependencies Used by These Pages

The relevant packages are listed in [package.json](../package.json):

- `react` and `react-dom` for the page components.
- `react-router-dom` for dashboard and review navigation.
- `lucide-react` for icons.
- `framer-motion` for list and panel transitions.
- `react-markdown` for SOP content rendering.
- `tailwindcss`, `postcss`, `autoprefixer`, and `vite` for styling and development.

## Backend Integration Checklist

When mock extraction data is replaced with API data:

- Add an extraction service method such as `getSopExtraction(sopId)`.
- Load the selected SOP and its sections from the route `sopId`.
- Return structured section changes with `added`, `deleted`, and `unchanged` line types.
- Return a numeric confidence score per section.
- Replace the `localStorage.userRole` check with the authenticated session role.
- Protect approve and reject endpoints server-side.
- Preserve the existing loading, empty, error, and retry states used by `Dashboard.tsx`.
