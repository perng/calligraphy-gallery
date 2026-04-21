# Calligraphy Archive Web Application - High Level Design

## 1. Overview

This document describes a web application for browsing and querying a calligraphy image archive.

The archive contains image directories whose titles encode rich metadata, such as:

- calligrapher, e.g. `米芾`
- script style, e.g. `行書`
- work title, e.g. `蜀素帖`
- work form, e.g. `尺牘`, `長卷`, `墓誌塔銘`
- dynasty / historical period
- series / collection, e.g. `快雪堂法書`
- topical grouping, e.g. `心經書法`, `蘭亭集序`
- source labels, e.g. `書法碑帖`, `書法圖書`

The goal is to build a web application that allows users to query and browse the archive in many different orders, for example:

- `米芾 -> 行書`
- `王羲之 -> 草書 -> 尺牘`
- `心經 -> 趙孟頫`
- `主題 -> 朝代 -> 書體`
- `唐代 -> 墓誌塔銘`
- `顏真卿 -> 楷書 -> 神道碑`

The system should support both:

1. **Structured navigation**, where the user progressively narrows results through facets.
2. **Free search**, where the user types natural terms and gets matched results.

This design assumes that:

- the image source is an existing archive of directories/images
- metadata is initially derived from directory titles and later may be manually corrected
- the system should support lightweight manual correction of bad metadata
- trusted local users may edit metadata and delete incorrect items
- the archive is mostly fixed in size and is unlikely to grow substantially over time
- the application will run on a low-power machine for at most one or two concurrent users

---

## 2. Goals

### 2.1 Primary goals

- Allow users to browse the archive by many dimensions:
  - calligrapher
  - script
  - dynasty / period
  - work form
  - series / collection
  - theme
- Allow multi-step drill-down navigation:
  - e.g. `米芾 -> 行書`
  - e.g. `王羲之 -> 草書 -> 尺牘`
  - e.g. `主題 -> 朝代 -> 書體`
  - e.g. `主題 -> 朝代 -> 書體 -> 書家`
- Show thumbnails and full image views for matched items
- Show `most viewed` and `recently viewed` items so users can quickly return to works they have been practicing
- Support fuzzy search over Chinese titles and extracted attributes
- Keep metadata model simple, explicit, and easy to maintain in SQLite
- Support incremental cleanup and enrichment of metadata over time

### 2.2 Secondary goals

- Support aliases and variant names:
  - `米芾`, `米元章`, `海嶽外史`
- Support multiple organizational views over the same underlying image set
- Support future tagging, curation, and editorial notes
- Support lightweight metadata editing and item deletion by a trusted curator
- Support lightweight local viewing history without requiring a full account system
- Support a mostly static or low-cost deployment model
- Minimize CPU, RAM, and operational overhead

### 2.3 Non-goals for first version

- Image editing
- Full user account system
- Crowdsourced metadata editing
- Complex access control beyond simple local admin protection
- OCR over image content
- Full-text transcription of calligraphy content

---

## 3. User scenarios

### 3.1 Example user flows

#### Flow A: browse by calligrapher then script

1. User opens site.
2. User clicks `書家`.
3. User chooses `米芾`.
4. Site shows facets and summary:
   - scripts: 行書 / 草書 / 行草 / 尺牘 / 題跋
5. User clicks `行書`.
6. Site shows all matching works with thumbnails.
7. User opens a work and views the directory images.

#### Flow B: browse by theme

1. User clicks `主題`.
2. User chooses `心經書法`.
3. Site shows available calligraphers and works.
4. User selects `趙孟頫`.
5. Site shows relevant images.

#### Flow B2: browse by theme, then period, then script

1. User clicks `主題`.
2. User chooses `心經書法`.
3. Site shows remaining facets and counts.
4. User selects `朝代 = 唐代`.
5. Site narrows results and updates remaining facet counts.
6. User selects `書體 = 楷書`.
7. Site shows items matching all selected facets.

#### Flow C: free search

1. User types `米芾 行書`.
2. Site returns matched works ranked by relevance.
3. User refines with facet filters.

#### Flow D: browse by series

1. User clicks `碑帖法帖叢刊`.
2. User chooses `快雪堂法書`.
3. Site shows all included works grouped by calligrapher or volume.

#### Flow E: correct bad metadata

1. User opens an item detail page.
2. User notices that the calligrapher, script, or title is incorrect.
3. User clicks `Edit metadata`.
4. Site shows an edit form with current normalized fields.
5. User updates fields such as title, person, script, period, or theme.
6. Site saves the change to SQLite and refreshes search/facet data for that item.

#### Flow F: delete an invalid item

1. User opens an item that is a duplicate, broken import, or unwanted record.
2. User clicks `Delete item`.
3. Site asks for confirmation.
4. User confirms deletion.
5. Site removes or soft-deletes the item and excludes it from browse/search results.

#### Flow G: resume practice from recent history

1. User opens the home page.
2. Site shows a `Recently viewed` section.
3. User sees items they opened during recent practice sessions.
4. User clicks one item and resumes viewing or practicing it.

#### Flow H: reopen a frequently practiced work

1. User opens the home page or browse page.
2. Site shows a `Most viewed` section.
3. User sees works they have opened many times.
4. User clicks one of those items to continue practice.

---

## 4. High-level architecture

### 4.1 System components

```text
[Image Storage]
    |
    v
[Metadata Extraction / Curation Pipeline]
    |
    v
[SQLite Database]
    |
    +--> [Backend Web App]
    |         |
    |         v
    |     [Server-rendered HTML UI]
    |
    +--> [Admin / Metadata QA tools - future]
```

### 4.2 Main layers

#### Image storage layer

Stores the actual images and original directory structure.

#### Metadata layer

Stores normalized extracted metadata from titles.

#### Search/query layer

Supports structured filters and lightweight search using SQLite queries and optional FTS.

#### Frontend

Provides browse, filter, search, and image viewing UX with mostly server-rendered pages.

#### Admin / curation layer

Provides lightweight metadata correction tools for trusted local users, including item editing, deletion, alias cleanup, and reindex actions.

---

## 5. Data source assumptions

The existing archive consists of image directories whose titles encode metadata.

Example title patterns:

```text
米芾行書_章侯帖_上海博物館藏_蘇黃米蔡_書法欣賞
王羲之草書欣賞_秋中帖_尺牘4種_二王書法_書法欣賞
趙孟頫行書真跡_南谷帖_附題跋_顏柳歐趙_書法欣賞
```

A directory usually maps to:

- one work, or
- one edition / series volume, or
- one thematic collection

Each directory contains one or more image files representing scanned pages.

---

## 6. Data model

### 6.1 Core entity model

The system should not treat directory titles as the final authoritative structure. Instead, it should normalize them into entities.

Recommended core entities:

- `Item`
- `Image`
- `Person`
- `Script`
- `Theme`
- `Series`
- `Period`
- `Institution`
- `Tag`

### 6.2 Primary entity: Item

An `Item` is the main unit users browse and search.

Examples:

- a specific work
- a specific 碑帖 volume
- a specific 長卷
- a thematic grouped item if the source is inherently thematic

Suggested fields:

```json
{
  "id": "item_000001",
  "raw_title": "米芾行書_章侯帖_上海博物館藏_蘇黃米蔡_書法欣賞",
  "display_title": "章侯帖",
  "canonical_title": "章侯帖",
  "primary_person_id": "person_mifu",
  "person_ids": ["person_mifu"],
  "script_ids": ["script_xingshu"],
  "period_ids": ["period_song"],
  "work_form_ids": ["form_fatie_or_work"],
  "theme_ids": [],
  "series_id": null,
  "institution_ids": ["inst_shanghai_museum"],
  "source_labels": ["蘇黃米蔡", "書法欣賞"],
  "top_level_bucket": "書家作品",
  "directory_path": "...",
  "image_count": 12,
  "view_count": 27,
  "last_viewed_at": "2026-04-20T21:30:00Z",
  "review_status": "edited",
  "is_deleted": false,
  "updated_at": "2026-04-20T12:00:00Z"
}
```

### 6.3 Image

Each item has one or more images.

Suggested fields:

```json
{
  "id": "img_000001",
  "item_id": "item_000001",
  "storage_uri": "...",
  "page_index": 1,
  "file_name": "001.jpg",
  "width": 2000,
  "height": 3000,
  "thumbnail_uri": "...",
  "sort_key": "0001"
}
```

### 6.4 Person

Represents a calligrapher or named historical person associated with a work.

Suggested fields:

```json
{
  "id": "person_mifu",
  "display_name": "米芾",
  "normalized_name": "米芾",
  "aliases": ["米元章", "海嶽外史", "米南宮"],
  "period_label": "北宋",
  "notes": ""
}
```

### 6.5 Supporting entities

#### Script

- 篆書
- 隸書
- 楷書
- 行書
- 草書
- 行草
- 小楷
- 章草
- 隸楷

#### WorkForm

- 尺牘
- 長卷
- 手卷
- 冊頁
- 碑帖
- 墓誌
- 神道碑
- 拓本
- 印譜
- 寫經
- 題跋
- 題簽

#### Theme

- 心經書法
- 蘭亭集序
- 春聯
- 福字
- 楹聯
- 集字作品
- 千字文
- 道德經
- 赤壁賦

#### Series

- 快雪堂法書
- 玉煙堂法帖
- 渤海藏真帖
- 秋碧堂法書
- 寶賢堂集古法帖
- 鬱岡齋墨妙
- 天香樓藏帖
- 絳帖

#### Institution

- 上海博物館
- 北京故宮博物院
- 美國大都會博物館
- 哈佛大學
- 大英圖書館

---

## 7. Metadata normalization strategy

### 7.1 Principles

Metadata extraction from titles is useful but imperfect.

Therefore the system should preserve three layers:

- raw source title
- machine-extracted attributes
- normalized / curated attributes

### 7.2 Example approach

For each item:

- preserve original title exactly
- extract probable fields using parser rules
- normalize known entities against controlled vocabularies
- store confidence / review status

Suggested fields:

```json
{
  "raw_title": "...",
  "parsed": {
    "primary_person": "米芾",
    "scripts": ["行書"],
    "title_candidate": "章侯帖"
  },
  "normalized": {
    "primary_person_id": "person_mifu",
    "script_ids": ["script_xingshu"]
  },
  "review_status": "auto"
}
```

### 7.3 Why this matters

This makes it possible to:

- improve parsing later
- correct ambiguous items
- keep the system stable even when rules evolve

---

## 8. Query and browse model

The application should support both navigation-first and search-first use cases.

### 8.1 Faceted navigation

Users should be able to filter results by multiple dimensions.

Recommended top-level facets:

- 書家
- 書體
- 朝代 / 時代
- 作品形態
- 主題
- 叢帖 / 系列
- 館藏 / 機構
- 上層分類

Users must be able to begin with any of these facets and then add any other facets in any sequence.

Example:

```text
書家 = 米芾
書體 = 行書
```

Returns all items matching both.

### 8.2 Facet ordering

Users should be able to start from any facet, not only from calligrapher.

Examples:

- 米芾 -> 行書
- 行書 -> 米芾
- 北宋 -> 行書 -> 米芾
- 心經書法 -> 趙孟頫
- 主題 -> 朝代 -> 書體
- 主題 = 心經書法 -> 朝代 = 唐代 -> 書體 = 楷書
- 書體 -> 主題 -> 朝代
- 墓誌塔銘 -> 唐代

This means the API and query engine must support commutative filtering: all facet selections combine into one boolean query, regardless of the order in which the user selected them.

The UI should therefore:

- always show the currently active filters
- recalculate remaining facet counts after every selection
- allow users to add the next filter from any remaining facet group
- avoid hard-coding a single browse path such as `書家 -> 書體 -> 作品`

### 8.3 Free search

Support full-text search over:

- raw title
- canonical title
- person names and aliases
- themes
- series
- institutions
- source labels

Example queries:

- `米芾 行書`
- `趙孟頫 心經`
- `王羲之 草書 尺牘`
- `快雪堂法書 米芾`

### 8.4 Result ranking

Ranking should prioritize:

- exact match on person name
- exact match on canonical title
- exact match on script / theme / series
- alias matches
- raw title term matches

---

## 9. Frontend application design

### 9.1 Main pages

#### Home

- global search box
- recently viewed items
- most viewed items
- featured entry points
- quick browse by:
  - 書家
  - 書體
  - 朝代
  - 主題
  - 叢帖

#### Browse page

- left sidebar or top filter bar
- result list/grid
- active filter chips
- sort options
- optional shortcut modules for `Recently viewed` and `Most viewed`

#### Item detail page

- title
- calligrapher
- script
- period
- theme / series links
- image gallery
- metadata panel
- related items
- view count / last viewed metadata if useful
- edit metadata action for trusted local users
- delete item action for trusted local users

#### Image viewer

- full-resolution image
- previous / next page navigation
- zoom / pan
- optional filmstrip of thumbnails

#### Admin / edit page

- editable metadata form
- review status controls
- alias correction helpers
- delete / restore controls
- save and reindex action

### 9.2 UI interaction model

Users should be able to:

- click into a facet
- refine with more filters
- remove filters
- deep link to current state via URL

Example URL:

```text
/browse?person=米芾&script=行書
```

Or normalized IDs:

```text
/browse?person=person_mifu&script=script_xingshu
```

### 9.3 Suggested UI components

- global search bar
- facet filter panel
- result cards
- recently viewed strip
- most viewed strip
- item metadata sidebar
- image lightbox / full viewer
- breadcrumbs
- related-items section
- metadata edit form
- delete confirmation dialog
- review status badge

---

## 10. Backend / API design

A lightweight backend is recommended because it simplifies:

- structured queries
- search ranking
- metadata normalization
- image URL abstraction
- future admin tools

For this deployment profile, the backend should preferably be a single process serving both HTML pages and JSON endpoints. A separate frontend application is unnecessary overhead for one or two users.

### 10.1 Core API endpoints

#### Search / browse

```http
GET /api/items
```

Query params:

- `q`
- `person`
- `script`
- `period`
- `theme`
- `series`
- `form`
- `bucket`
- `page`
- `page_size`
- `sort`

Example:

```http
GET /api/items?person=person_mifu&script=script_xingshu
```

#### Item detail

```http
GET /api/items/:id
```

Returns:

- item metadata
- related entities
- ordered image list

When an item detail page is opened, the system should record a lightweight view event or update per-item view counters and last-viewed timestamps.

#### Facet values

```http
GET /api/facets
GET /api/facets/persons
GET /api/facets/scripts
GET /api/facets/themes
```

#### Image metadata

```http
GET /api/items/:id/images
```

#### Suggest / autocomplete

```http
GET /api/suggest?q=米
```

Returns matching:

- person names
- titles
- series
- themes

#### Usage history

```http
GET /api/history/recent
GET /api/history/most-viewed
```

Returns:

- a small list of item summaries
- thumbnail
- title
- primary calligrapher
- last viewed timestamp or total view count

#### Admin pages

```http
GET /admin/items/:id/edit
```

Returns:

- editable metadata form
- normalized entity choices
- review status and delete state

### 10.2 Admin write endpoints

```http
PATCH /api/admin/items/:id
POST /api/admin/items/:id/delete
POST /api/admin/items/:id/restore
POST /api/admin/person-aliases
POST /api/admin/reindex
```

Recommended behavior:

- edits should update only normalized metadata, not overwrite the raw source title
- deletion should default to soft delete via `is_deleted = true`
- browse and search queries should exclude deleted items by default
- reindex should refresh only the edited item unless a full rebuild is explicitly requested

---

## 11. Search / indexing options

### 11.1 Recommended options

#### Option A: SQLite only

- SQLite for primary data
- normal indexed SQL queries for faceted browsing
- simple `LIKE` queries for early search
- optional SQLite `FTS5` for better text search if needed

Best if:

- the dataset is mostly fixed
- there are only one or two concurrent users
- operational simplicity is more important than advanced ranking

#### Option B: SQLite + `FTS5`

- SQLite for storage
- SQLite `FTS5` virtual tables for title and alias search

Best if:

- search quality needs to improve without adding another service
- the machine should still run only one application process
- the archive fits comfortably on local disk

#### Option C: static JSON + client-side filtering

Best only for a prototype or small dataset.

Not recommended long-term if:

- metadata normalization is still evolving
- image counts are non-trivial
- browse filters need stable relational semantics

### 11.2 Recommendation

Start with:

- SQLite as the metadata source of truth
- normal indexed SQL queries for browse filters
- optional `FTS5` only if plain SQLite search feels insufficient

This is the lightest stack that still preserves a clean data model and good enough search behavior.

---

## 12. Image delivery design

### 12.1 Requirements

The application must:

- show thumbnails in lists
- show full images in item view
- preserve page order
- handle large scans efficiently

### 12.2 Recommended model

For each source image:

- store original image
- generate thumbnail and optionally medium-sized preview
- serve image URLs through a stable app-managed path

Example:

```text
/media/thumbs/item_001/0001.jpg
/media/preview/item_001/0001.jpg
/media/full/item_001/0001.jpg
```

### 12.3 Why not depend directly on directory names

Directory names are messy, inconsistent, and contain mixed metadata. The app should reference images by stable internal IDs, not raw paths.

---

## 13. Proposed logical navigation structure

The frontend should expose multiple browse paths over the same data.

### 13.1 Primary browse entries

- 書家
- 書體
- 朝代
- 題材 / 主題
- 作品形態
- 叢帖 / 法帖
- 墓誌塔銘
- 敦煌寫經
- 篆刻
- 傳世字畫

### 13.2 Example navigation trees

#### Example A

- 書家
- 米芾
- 行書
- 草書
- 行草
- 尺牘
- 題跋

#### Example B

- 主題
- 心經書法
- 趙孟頫
- 于右任
- 日本古寫經
- 敦煌寫經

#### Example C

- 系列
- 快雪堂法書
- 米芾
- 蘇軾
- 顏真卿

---

## 14. Data ingestion pipeline

### 14.1 Steps

1. Read directory titles and image paths.
2. Create raw item records.
3. Run metadata parser.
4. Normalize entities against vocabularies.
5. Create item-image relationships.
6. Generate thumbnails.
7. Build database records.
8. Optionally build SQLite `FTS5` search tables.

### 14.2 Re-ingestion strategy

The ingestion pipeline should be repeatable.

Recommended approach:

- source scan job generates raw inventory
- parser generates extracted JSON
- normalizer resolves entities
- importer writes to DB
- manual edits remain in curated fields and must not be overwritten blindly by re-import
- optional `FTS5` builder updates SQLite search tables

This makes future metadata improvements easy.

---

## 15. Entity normalization rules

### 15.1 Person normalization

Need alias mapping for:

- courtesy names
- alternate names
- sobriquets
- different forms in titles

Examples:

- 米芾 / 米元章 / 海嶽外史
- 趙孟頫 / 趙子昂 / 松雪道人
- 蘇軾 / 蘇東坡

### 15.2 Script normalization

Need mapping from title text to controlled values:

- 行書
- 草書
- 行草
- 楷書
- 小楷
- 篆書
- 隸書
- 章草
- 隸楷

### 15.3 Work form normalization

Examples:

- 墓誌銘
- 神道碑
- 尺牘
- 手卷
- 長卷
- 冊頁
- 印譜
- 題跋
- 寫經
- 集字

### 15.4 Theme normalization

Examples:

- 心經
- 蘭亭集序
- 道德經
- 千字文
- 赤壁賦
- 岳陽樓記
- 春聯
- 福字

---

## 16. Recommended tech stack

### 16.1 Frontend

- server-rendered HTML templates with `Jinja2`
- `htmx` for lightweight partial-page updates
- small hand-written CSS or a minimal CSS utility layer
- lightweight image viewer JavaScript only where zoom/pan is needed

### 16.2 Backend

- Python + `FastAPI`
- server-rendered pages plus small JSON endpoints
- run as a single `uvicorn` process

### 16.3 Data layer

- SQLite
- optional SQLite `FTS5` for search
- local filesystem for images and thumbnails

### 16.4 Why this stack

- minimal RAM and CPU usage
- one deployable application process
- straightforward local backup and restore
- no external database or search service to operate
- sufficient for a mostly fixed archive and very low concurrency

---

## 17. Suggested phases

### Phase 1: metadata import + basic browse application

- import extracted JSON
- show home, browse page, and item page
- basic filters
- plain SQLite search or simple title matching
- simple local-only metadata edit form for items

### Phase 2: refined metadata + optional `FTS5`

- alias normalization
- improve search ranking inside SQLite
- add `FTS5` only if needed
- related items
- soft delete and restore workflow

### Phase 3: metadata correction tools

- review queue
- alias editor
- manual merge/split
- curator notes
- batch reindex for edited records

### Phase 4: advanced viewer and curation

- deep zoom
- curated collections
- comparison view
- save/bookmark feature

---

## 18. Risks and design considerations

### 18.1 Metadata ambiguity

Titles are noisy and inconsistent.

Mitigation:

- preserve raw title
- keep extracted + normalized forms separate
- support manual correction

### 18.2 Duplicate or near-duplicate items

Some items may represent different editions or printings of the same work.

Mitigation:

- support work-level grouping later
- distinguish item from future work abstraction if needed

### 18.3 Alias complexity

Many people and works have variant names.

Mitigation:

- alias dictionary
- normalized IDs
- search expansion

### 18.4 Image scale

Large scans can be slow.

Mitigation:

- generate thumbnails and previews
- lazy loading
- zoom only on demand

---

## 19. Recommended first database tables

If starting with SQL, create these first:

- `items`
- `images`
- `persons`
- `scripts`
- `periods`
- `themes`
- `series`
- `institutions`
- `tags`

Join tables:

- `item_persons`
- `item_scripts`
- `item_periods`
- `item_themes`
- `item_tags`
- `item_institutions`

Additional useful fields or tables for curation:

- `items.is_deleted`
- `items.review_status`
- `items.view_count`
- `items.last_viewed_at`
- `items.updated_at`
- `edit_log` for simple audit history
- `item_views` for lightweight recent-history tracking
- `deleted_items` only if hard delete tracking is required

This is enough to support the browse patterns discussed above.

For this deployment profile, `most viewed` can be derived from `items.view_count`, and `recently viewed` can be derived from `items.last_viewed_at` or a small `item_views` history table. This should remain lightweight and local to the machine, not a full analytics subsystem.

### 19.1 Suggested SQLite schema

The following schema is a practical starting point for this application.

#### Core tables

```sql
CREATE TABLE items (
  id TEXT PRIMARY KEY,
  raw_title TEXT NOT NULL,
  display_title TEXT,
  canonical_title TEXT,
  primary_person_id TEXT REFERENCES persons(id),
  series_id TEXT REFERENCES series(id),
  top_level_bucket TEXT,
  directory_path TEXT NOT NULL UNIQUE,
  image_count INTEGER NOT NULL DEFAULT 0,
  view_count INTEGER NOT NULL DEFAULT 0,
  last_viewed_at TEXT,
  review_status TEXT NOT NULL DEFAULT 'auto',
  is_deleted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE images (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  storage_uri TEXT NOT NULL,
  thumbnail_uri TEXT,
  preview_uri TEXT,
  file_name TEXT NOT NULL,
  page_index INTEGER NOT NULL,
  sort_key TEXT,
  width INTEGER,
  height INTEGER
);

CREATE TABLE persons (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL UNIQUE,
  period_label TEXT,
  notes TEXT
);

CREATE TABLE person_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id TEXT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  UNIQUE(person_id, alias)
);

CREATE TABLE scripts (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);

CREATE TABLE periods (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE,
  sort_order INTEGER
);

CREATE TABLE themes (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);

CREATE TABLE series (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);

CREATE TABLE institutions (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);

CREATE TABLE tags (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);

CREATE TABLE work_forms (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);
```

#### Join tables

```sql
CREATE TABLE item_persons (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  person_id TEXT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  role TEXT DEFAULT 'associated',
  PRIMARY KEY (item_id, person_id)
);

CREATE TABLE item_scripts (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  script_id TEXT NOT NULL REFERENCES scripts(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, script_id)
);

CREATE TABLE item_periods (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  period_id TEXT NOT NULL REFERENCES periods(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, period_id)
);

CREATE TABLE item_themes (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  theme_id TEXT NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, theme_id)
);

CREATE TABLE item_tags (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, tag_id)
);

CREATE TABLE item_institutions (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  institution_id TEXT NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, institution_id)
);

CREATE TABLE item_work_forms (
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  work_form_id TEXT NOT NULL REFERENCES work_forms(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, work_form_id)
);
```

#### Curation and usage-history tables

```sql
CREATE TABLE item_views (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  viewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE edit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT REFERENCES items(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

#### Recommended indexes

```sql
CREATE INDEX idx_items_primary_person_id ON items(primary_person_id);
CREATE INDEX idx_items_series_id ON items(series_id);
CREATE INDEX idx_items_is_deleted ON items(is_deleted);
CREATE INDEX idx_items_last_viewed_at ON items(last_viewed_at);
CREATE INDEX idx_images_item_id_page_index ON images(item_id, page_index);
CREATE INDEX idx_item_views_item_id_viewed_at ON item_views(item_id, viewed_at DESC);
CREATE INDEX idx_person_aliases_alias ON person_aliases(alias);
```

#### Optional FTS5 table

If plain SQLite `LIKE` queries become insufficient, add an `FTS5` table for search:

```sql
CREATE VIRTUAL TABLE item_search USING fts5(
  item_id UNINDEXED,
  raw_title,
  display_title,
  canonical_title,
  person_names,
  aliases,
  themes,
  series,
  institutions,
  source_labels
);
```

#### Notes

- `items.is_deleted` supports soft delete.
- `items.view_count` and `items.last_viewed_at` support fast lookup for `most viewed` and `recently viewed`.
- `item_views` is optional but useful if you want a more precise recent-history list.
- `person_aliases` should be a separate table rather than a JSON column, because aliases are part of search behavior.
- `work_forms` should be a first-class table even though it is conceptually similar to tags.

---

## 20. Example query behavior

### Query: 米芾 -> 行書

System behavior:

- resolve `米芾` to `person_mifu`
- resolve `行書` to `script_xingshu`
- query items where:
  - item linked to `person_mifu`
  - item linked to `script_xingshu`
- return ranked results
- display thumbnails and facet counts

### Query: 心經 -> 趙孟頫

System behavior:

- resolve `心經` as theme or text subject
- resolve `趙孟頫` as person
- search items matching both
- show grouped results by work / edition if needed

---

## 21. Implementation decisions

This section defines the missing implementation details needed to build the first working version consistently.

### 21.1 Canonical storage rules

The database should treat these fields as authoritative:

- `items.raw_title` stores the original source directory title exactly as imported
- `items.display_title` stores the title shown in the UI
- `items.canonical_title` stores the normalized title used for search and grouping
- join tables store normalized relationships such as persons, scripts, periods, themes, institutions, and work forms

The system should not store arrays such as `person_ids` or `script_ids` inside `items`. Those arrays are conceptual examples only. In SQLite, those relationships should live in join tables.

`source_labels` should be stored relationally. The simplest first version is:

- add a `source_labels` lookup table
- add an `item_source_labels` join table

If the team wants to keep the first version smaller, `source_labels` may temporarily be stored as JSON text on `items`, but that should be treated as a short-term compromise because it weakens search and filtering.

### 21.2 Parsing and normalization rules

The ingestion parser should follow this order:

1. Preserve `raw_title` exactly.
2. Split the source title into tokens using `_` first.
3. Run dictionary matching against controlled vocabularies for:
   - person names and aliases
   - script names
   - period names
   - work forms
   - institutions
   - known themes
   - known series
4. After known entities are removed from consideration, treat the best remaining title-like token as the initial title candidate.
5. Store both parsed values and normalized IDs.

Parsing precedence should be:

1. Exact canonical match
2. Exact alias match
3. longest known token match
4. heuristic fallback

Normalization rules:

- a token may map to more than one candidate during parsing
- the parser should record ambiguity instead of silently picking a wrong value
- `review_status = auto` means fully machine-generated
- `review_status = edited` means a local user changed one or more curated fields
- `review_status = needs_review` means parsing confidence was too low or there were conflicting candidates

The first implementation should keep the parser deterministic. Avoid ML extraction in the initial version.

### 21.3 Re-import identity and merge rules

Re-import must be idempotent.

Item identity should be determined by:

1. exact `directory_path` match, if the source directory still exists at the same path
2. otherwise an explicit import mapping table, if introduced later

Re-import behavior:

- if an existing `directory_path` is found, update machine-derived fields only
- do not overwrite curator-edited fields when `review_status = edited`
- do not clear `is_deleted` automatically on re-import
- do not reset `view_count`, `last_viewed_at`, or `item_views`
- if images have changed inside the directory, rebuild the image rows for that item
- if the item was soft deleted, keep it hidden until a user explicitly restores it

Recommended field ownership:

- machine-owned fields: raw import inventory, image file list, parser output cache
- curator-owned fields: normalized title, person assignment, script assignment, theme assignment, deletion state

### 21.4 API response contracts

The first implementation should standardize responses as JSON objects with predictable shapes.

`GET /api/items` response:

```json
{
  "items": [
    {
      "id": "item_000001",
      "display_title": "章侯帖",
      "canonical_title": "章侯帖",
      "primary_person": { "id": "person_mifu", "name": "米芾" },
      "scripts": [{ "id": "script_xingshu", "label": "行書" }],
      "periods": [{ "id": "period_song", "label": "北宋" }],
      "themes": [],
      "thumbnail_uri": "/media/thumbs/item_001/0001.jpg",
      "image_count": 12,
      "view_count": 27,
      "last_viewed_at": "2026-04-20T21:30:00Z"
    }
  ],
  "page": 1,
  "page_size": 24,
  "total": 153,
  "facets": {
    "persons": [],
    "scripts": [],
    "periods": [],
    "themes": [],
    "series": [],
    "work_forms": []
  }
}
```

`GET /api/items/:id` response:

```json
{
  "item": {
    "id": "item_000001",
    "raw_title": "米芾行書_章侯帖_上海博物館藏_蘇黃米蔡_書法欣賞",
    "display_title": "章侯帖",
    "canonical_title": "章侯帖",
    "review_status": "edited",
    "is_deleted": false,
    "view_count": 27,
    "last_viewed_at": "2026-04-20T21:30:00Z"
  },
  "relations": {
    "persons": [],
    "scripts": [],
    "periods": [],
    "themes": [],
    "series": null,
    "institutions": [],
    "work_forms": []
  },
  "images": []
}
```

`PATCH /api/admin/items/:id` request body:

```json
{
  "display_title": "章侯帖",
  "canonical_title": "章侯帖",
  "primary_person_id": "person_mifu",
  "script_ids": ["script_xingshu"],
  "period_ids": ["period_song"],
  "theme_ids": [],
  "institution_ids": ["inst_shanghai_museum"],
  "work_form_ids": ["form_chidu"],
  "review_status": "edited"
}
```

Patch rules:

- omitted fields mean "leave unchanged"
- empty arrays mean "clear this relation"
- `raw_title` and `directory_path` are not editable from the UI in the first version

Error format:

```json
{
  "error": {
    "code": "not_found",
    "message": "Item not found"
  }
}
```

### 21.5 Browse and search semantics

All facet filters combine with logical `AND`.

Within a single facet group:

- multi-select values combine with logical `OR`
- example: `script=行書,草書` means items matching either script

Search semantics for the first version:

- tokenize query text by whitespace
- try exact matches on canonical fields first
- then try alias matches
- then try `LIKE` or `FTS5` term matches

Default sort order:

1. relevance when `q` is present
2. otherwise `last_viewed_at DESC` for history endpoints
3. otherwise `display_title ASC` for browse results

### 21.6 View-history rules

Viewing behavior must be lightweight and deterministic.

Rules:

- a view is recorded when an item detail page is opened successfully
- image navigation inside the same item does not create extra item views
- refreshing the same item within a short debounce window should not increment the count repeatedly
- recommended debounce window: 10 minutes per item
- `items.view_count` increments only when a debounced view is accepted
- `items.last_viewed_at` updates when a debounced view is accepted
- `item_views` stores accepted debounced views only

History scope for the first version:

- machine-local or app-local, not user-account-specific
- acceptable because the deployment target is one or two trusted users on one machine

History list behavior:

- `recently viewed` should deduplicate by item and sort by most recent accepted view
- `most viewed` should sort by `view_count DESC`, with `last_viewed_at DESC` as a tiebreaker
- deleted items should not appear in either list

### 21.7 Admin and deletion rules

Deletion behavior:

- delete means soft delete in the first version
- soft-deleted items are hidden from browse, search, recent history, and most-viewed modules
- restore reverses `is_deleted` and makes the item visible again
- hard delete should not exist in the UI for the first version

Edit behavior:

- every successful admin edit should write an `edit_log` row
- every successful admin edit should update `items.updated_at`
- every successful admin edit should refresh derived search data for that item

Access control:

- no account system is required
- no special protection is required for admin routes in the first version
- admin and curation features can be available to all users of this local deployment

### 21.8 Implementation order

Recommended implementation order:

1. SQLite schema and migrations
2. source scan + import pipeline
3. read-only browse and item detail pages
4. faceted filtering and basic search
5. recent / most-viewed tracking
6. admin item edit form
7. soft delete / restore
8. optional `FTS5`

This order reduces risk because it validates the ingestion and query model before adding curation complexity.

---

## 22. Recommendation summary

The archive should be modeled as a metadata-driven image library, not as a raw directory browser.

Recommended design principles:

- keep raw titles but normalize aggressively
- make `Item` the central browse/search entity
- support many simultaneous facet orders
- decouple image storage from display logic
- keep the deployment simple enough for a low-power single-machine setup
- prefer SQLite and one backend process over multi-service architecture
- allow trusted local users to correct and delete bad records from the UI
- optimize for maintainability, not horizontal scale

The most important product behavior is this:

> A user should be able to start from any meaningful attribute - person, script, dynasty, theme, series, or work form - and progressively narrow to a set of images.

That is the core design requirement the whole system should optimize for.
