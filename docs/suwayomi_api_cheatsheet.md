# Suwayomi API Cheat Sheet (from WebUI RequestManager)

This summarizes useful GraphQL mutations/queries (and a couple REST endpoints) exposed by Suwayomi, based on the WebUI `RequestManager.ts`.

Use cases for this project:
- Mark chapters read (we already use this)
- Preload chapters for a manga before read-sync (replace sleeps)
- Verify read marks by state
- Map categories/statuses with official mutations
- Optional utilities: download queue ops, update library, metadata

---

## Mark/Verify Chapters

- Mark chapters read (batch)
  - Mutation: `updateChapters`
  - Variables: `{ input: { ids: [Int!], patch: { isRead: true, lastPageRead: 0 } } }`
  - Minimal selection: `updateChapters { chapters { nodes { id isRead } } }`

- Mark chapter read (single)
  - Mutation: `updateChapter`
  - Variables: `{ input: { id: Int!, patch: { isRead: true, lastPageRead: 0 } } }`
  - Minimal selection: `updateChapter { chapter { id isRead } }`

- Verify per-manga chapter states
  - Query: `getMangasChapterIdsWithState`
  - Variables: `{ mangaIds: [Int!], isRead: true|false, isDownloaded?: bool, isBookmarked?: bool }`
  - Returns: per-manga `chapterIds` for the given state(s). Use with `fetchPolicy: no-cache`.

- Trigger server to (re)fetch chapters for a manga (preload before sync)
  - Mutation: `getMangaChaptersFetch`
  - Variables: `{ input: { mangaId: Int! } }`
  - Tip: Call this once per manga and briefly poll `getChaptersManga` until chapters appear, instead of using fixed delays.

---

## Fetch Chapters/Manga

- Chapters for a manga
  - Query: `getChaptersManga`
  - Variables: `{ condition: { mangaId: Int! }, order: [{ by: SourceOrder, byType: Desc }] }`

- Single chapter by index (source order)
  - Query helper pattern: load `getChaptersManga` with `{ mangaId, sourceOrder }` and pick first node.

- Manga by id
  - Query: `getManga`
  - Variables: `{ id: Int! }`

---

## Categories & Status Mapping

- Read categories (ordered)
  - Query: `getCategoriesSettings`
  - Variables: `{ order: [{ by: Order }] }`

- Update categories for one manga
  - Mutation: `updateManga`
  - Variables: `{ input: { id, patch } }` and optionally `updateCategoryInput` + `updateCategories: true`

- Update categories for many mangas
  - Mutation: `updateMangasCategories`
  - Variables: `{ input: { ids: [Int!], patch: { categoryIds: [Int!] } } }`

- Manage categories
  - Mutations: `createCategory`, `updateCategory`, `deleteCategory`, `updateCategoryOrder`

---

## Metadata (optional helpers)

- Set/Delete metadata for manga/source/chapter
  - Mutations: `setMangaMeta`, `deleteMangaMeta`, `setSourceMeta`, `deleteSourceMeta`, `setChapterMeta`, `deleteChapterMeta`
  - Variables: `{ input: { meta: { <scopeId>, key, value } } }` or `{ input: { <scopeId>, key } }`

---

## Download Queue (optional)

- Enqueue/dequeue single or multiple chapters
  - Mutations: `enqueueChapterDownload`, `dequeueChapterDownload`, `enqueueChapterDownloads`, `dequeueChapterDownloads`

- Reorder queue item
  - Mutation: `reorderChapterDownload`

- Observe/download status
  - Query: `getDownloadStatus`
  - Subscription: `downloadStatusSubscription`

- Control downloader
  - Mutations: `startDownloader`, `stopDownloader`, `clearDownloader`

---

## Library Update (optional)

- Trigger global library update
  - Mutation: `updateLibrary`
  - Variables: `{ input: { categories?: [Int] } }`

- Stop updater
  - Mutation: `stopUpdater`

- Observe updater
  - Queries: `getUpdateStatus`, `getLastUpdateTimestamp`
  - Subscription: `updaterSubscription`

---

## Server Settings (optional)

- Get settings
  - Query: `getServerSettings`

- Update settings
  - Mutation: `updateServerSettings`

- Clear server cache (images)
  - Mutation: `clearServerCache`
  - Variables: `{ input: { cachedPages: true, cachedThumbnails: true } }`

---

## Backups (optional)

- Validate backup
  - Query: `validateBackup`

- Restore backup
  - Mutation: `restoreBackup`

- Export backup (REST)
  - GET: `/api/v1/backup/export/file`

---

## Images (REST helper)

- Chapter page image URL (REST)
  - Path: `/api/v1/manga/{mangaId}/chapter/{chapterIndex}/page/{page}`

---

## Practical Patterns for This Project

- Preload before read-sync:
  1) Call `getMangaChaptersFetch(mangaId)`
  2) Poll `getChaptersManga` for the manga until `nodes.length > 0` (with small max wait)
  3) Then run `updateChapters` to mark read

- Verify after apply:
  - Call `getMangasChapterIdsWithState({ mangaIds:[id], isRead: true })` and compare counts against MD progress

- Status mapping via categories:
  - Translate MD status to category id, then call `updateManga`/`updateMangasCategories`

Notes
- All GraphQL calls require appropriate auth (auto/basic/simple/bearer). Some REST write endpoints may be disabled; GraphQL is the recommended path, matching the WebUI behavior.
