# API Documentation — File Management System

All endpoints require `Authorization: Bearer <token>`.

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `ADMIN_ROLE_ID` | 1 | Role ID with full admin access (configurable in `.env`) |

## Key Concepts

- **Admin** (`ADMIN_ROLE_ID`, default role_id=1): separate from org tree, sees everything, can update/delete/move any item
- **Shared roles**: multiple users can have the same role_id (e.g. all staff in Phòng A share role_id=6)
- **Same-role isolation**: users with the same role cannot see each other's files/folders. Only supervisors (parent role) see subordinates' content
- **Private files**: only visible to their creator, even admin sees them but supervisors don't
- **node_path**: each file stores its full position in the tree: `type_<type>/role_<id>/.../folder_<id>/...`
- **Depth loading**: tree APIs support `depth` param to load multiple levels in one request

## Role Tree (seed data)

```
Admin (id=1)             ← separate, not in org tree, level=0
Cuc truong (id=2)        ← org tree root, level=1
└── Cuc pho (id=3)       ← level=2
    ├── TP Phong A (id=4) ← level=3
    │   └── NV Phong A (id=6) ← level=4, shared by staff_a1/a2/a3
    └── TP Phong B (id=5) ← level=3
        └── NV Phong B (id=7) ← level=4, shared by staff_b1/b2
```

---

## Folder Management — `/api/v1/folders`

### POST `/` — Create Folder

`created_by` and `role_id` from auth. `parent_path` computed server-side from `parent_id`.

**Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | — | Folder name (max 255) |
| `parent_id` | int \| null | No | null | Parent folder ID. null = root |
| `type` | string | No | "private" | `private`, `organization`, `general` |
| `description` | string \| null | No | null | Description |

**Response `201`:** Folder object with `id`, `created_by`, `role_id`, `parent_path`, etc.

### PUT `/{folder_id}` — Update Folder

Update name/description. Creator or admin only. **Errors:** `403`, `404`.

### DELETE `/{folder_id}` — Soft Delete Folder

Soft delete folder + descendants + all files inside. Creator or admin only. **Response `204`.**

### PUT `/{folder_id}/move` — Move Folder

Move to new parent. Updates `parent_path` for descendants, re-computes `node_path` for all files. Creator or admin only.

**Body:** `new_parent_id` (int \| null). **Errors:** `400` circular, `403`, `404`.

### GET `/{folder_id}` — Get Folder by ID

### GET `/tree/root` — Tree Root (with depth)

**Query Params:**

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `type_filter` | Yes | — | `organization`, `private`, `general` |
| `depth` | No | 1 | Levels to load (1–10) |

**Visibility:**
- **Admin**: sees full org tree from root
- **Other users**: see from own role downward
- **Same-role isolation**: at own role level, only own files/folders shown

**depth behavior:**
- `depth=1`: children with `has_children` flag, `children: null`
- `depth=2+`: children populated recursively, stops when depth runs out

**Order:** files → folders → roles (newest first)

**Example: `GET /tree/root?type_filter=organization&depth=2` (user=head_a, role=4):**
```json
{
  "current_role": {"id": 4, "name": "Truong phong A"},
  "children": [
    {"node_type": "file", "id": 5, "name": "meeting_notes_q1.pdf",
     "node_path": "type_organization/role_2/role_3/role_4",
     "owner": {"id": 4, "full_name": "Pham Van C"}},
    {"node_type": "folder", "id": 4, "name": "Phong A - Tai lieu",
     "created_by": 4, "has_children": true,
     "children": [
       {"node_type": "file", "id": 6, "name": "sprint_report.xlsx"},
       {"node_type": "folder", "id": 5, "name": "Sprint Q1", "children": null}
     ]},
    {"node_type": "role", "id": 6, "name": "Nhan vien phong A",
     "has_children": true,
     "children": [
       {"node_type": "folder", "id": 8, "name": "NV_A1 docs"},
       {"node_type": "folder", "id": 9, "name": "NV_A2 docs"}
     ]}
  ]
}
```

### GET `/tree/{node_id}` — Expand Node (with depth)

**Query Params:**

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `node_type` | Yes | — | `role` or `folder` |
| `depth` | No | 1 | Levels to load |
| `page` | No | 1 | Page number |
| `page_size` | No | 20 | Items per page (max 100) |
| `search_text` | No | — | Search by name |
| `owner_name` | No | — | Filter by creator name |
| `role_name` | No | — | Filter by role name |

### POST `/query` — Query Folders (flat list)

**Body:** `parent_id`, `type`, `search_text`, `page`, `page_size` (all optional)

---

## File Management — `/api/v1/files`

### Existing APIs (unchanged)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload file |
| `POST` | `/my-files` | Query user's files (cursor pagination) |
| `POST` | `/my-with-children` | Query files including children hierarchy |
| `POST` | `/extract-file-content` | Extract content from file |
| `GET` | `/dashboard` | File dashboard statistics |
| `POST` | `/period-stats` | Period statistics |
| `POST` | `/country-tech-stats` | Country & tech statistics |

### New APIs

### GET `/detail/{file_id}` — Get File Detail

Full file detail: all metadata, content, classification, owner info, `node_path`.

**Response `200`:**
```json
{
  "id": 6, "name": "sprint_report.xlsx",
  "size": 128000, "hash": "seed_006",
  "created_by": 4, "folder_id": 5, "role_id": 4,
  "type": "organization",
  "node_path": "type_organization/role_2/role_3/role_4/folder_4/folder_5",
  "owner": {"id": 4, "full_name": "Pham Van C"},
  "is_processed": null, "content": null, "summary": null,
  "is_deleted": false
}
```

### PUT `/update/{file_id}` — Update File Name

Creator or admin only. **Body:** `name` (optional). **Response `200`:** file dict.

### DELETE `/delete/{file_id}` — Soft Delete File

Creator or admin only. **Response `204`.**

### PUT `/move/{file_id}` — Move File

Move to another folder. Re-computes `node_path`. Creator or admin only.

**Body:** `new_folder_id` (int \| null)

### POST `/list-all` — Get All Accessible Files (flat list)

Returns files the current user can see, sorted by `created_at DESC`.

**Visibility rules:**
- Own files (`created_by = current_user`)
- Files from subordinate roles (child roles in hierarchy)
- Admin sees all files
- Same role: does NOT show other users' files
- Private files: only visible to creator (admin sees all, supervisors don't)

**Body:** all optional.

| Field | Type | Description |
|-------|------|-------------|
| `folder_id` | int \| null | Filter by folder |
| `type` | string | `private`, `organization`, `general` |
| `owner_name` | string | Filter by creator name |
| `search_text` | string | Search by file name |
| `page` | int | Default 1 |
| `page_size` | int | Default 20, max 100 |

**Visibility examples:**

| User | Sees files |
|------|-----------|
| admin (role=1) | All 20 files |
| director (role=2) | Own + all org subtree |
| deputy1 (role=3) | Own + subtree, NOT deputy2's |
| deputy2 (role=3) | Own + subtree, NOT deputy1's |
| head_a (role=4) | Own (5,6,7) + all NV A (9-13) = 8 files, no private |
| staff_a1 (role=6) | Own only (9,10,16) — not a2/a3 |
| staff_a2 (role=6) | Own only (11,12,17) — not a1/a3 |

---

## Tree Node Types

### `node_type: "file"`
```json
{
  "node_type": "file", "id": 6, "name": "sprint_report.xlsx",
  "size": 128000, "extension": ".xlsx",
  "node_path": "type_organization/role_2/role_3/role_4/folder_4/folder_5",
  "owner": {"id": 4, "full_name": "Pham Van C"},
  "created_at": "...", "is_processed": null
}
```

### `node_type: "folder"`
```json
{
  "node_type": "folder", "id": 4, "name": "Phong A - Tai lieu",
  "parent_id": null, "created_by": 4, "type": "organization",
  "has_children": true, "children": [...]
}
```
`children`: populated when depth > 1. `null` when depth limit reached.

### `node_type: "role"`
```json
{
  "node_type": "role", "id": 6, "name": "Nhan vien phong A",
  "level": 4, "parent_path": ",2,3,4,",
  "has_children": true, "children": [...]
}
```

---

## node_path Format

`type_<type>/role_<id>/.../folder_<id>/...`

| Location | node_path |
|----------|-----------|
| Director → folder 1 | `type_organization/role_2/folder_1` |
| Deputy → folder 2 | `type_organization/role_2/role_3/folder_2` |
| TP A → folder 4 → folder 5 | `type_organization/role_2/role_3/role_4/folder_4/folder_5` |
| TP A → root (no folder) | `type_organization/role_2/role_3/role_4` |
| NV A → folder 8 | `type_organization/role_2/role_3/role_4/role_6/folder_8` |
| Private → folder 12 | `type_private/folder_12` |
| General → folder 14 → 15 | `type_general/folder_14/folder_15` |

**Re-computed when:** file created, file moved, folder moved (batch update).

---

## Tree Display Examples

### admin (role=1) login, depth=4, type=organization

```
▼ Cuc truong (role=2)
│  📄 bao_cao_q4.pdf
│  📁 Bao cao tong hop/
│  ▼ Cuc pho (role=3)
│  │  📄 ke_hoach_2025.docx
│  │  📁 Ke hoach 2025/
│  │  │  📁 Du an noi bo/
│  │  ▼ TP Phong A (role=4)
│  │  │  📄 meeting_notes_q1.pdf
│  │  │  📁 Phong A - Tai lieu/
│  │  │  │  📁 Sprint Q1/               [▶]
│  │  │  ▼ NV Phong A (role=6)
│  │  │  │  📁 NV_A1 docs/              [▶]
│  │  │  │  📁 NV_A2 docs/              [▶]
│  │  ▼ TP Phong B (role=5)
│  │  │  📁 Phong B - Tai lieu/          [▶]
│  │  │  ▷ NV Phong B (role=7)           [▶]
```

### head_a (role=4) login, depth=2

```
▼ TP Phong A (role=4)
│  📄 meeting_notes_q1.pdf              ← own file
│  📁 Phong A - Tai lieu/
│  │  📁 Sprint Q1/                      [▶]
│  ▼ NV Phong A (role=6)                ← sees ALL NV A files (supervisor)
│  │  📁 NV_A1 docs/ (by staff_a1)      [▶]
│  │  📁 NV_A2 docs/ (by staff_a2)      [▶]
│  │  📄 nv_a3_draft.pdf (by staff_a3)
```

### staff_a1 (role=6) login, depth=2

```
▼ NV Phong A (role=6)
│  📁 NV_A1 docs/                        ← only staff_a1's folder
│  │  📄 nv_a1_report.docx
│  │  📄 nv_a1_data.xlsx
│  (staff_a2/a3 files NOT shown — same role isolation)
```

### staff_a2 (role=6) login, depth=2

```
▼ NV Phong A (role=6)
│  📄 nv_a2_research.docx                ← only staff_a2's files
│  📁 NV_A2 docs/
│  │  📄 nv_a2_notes.pdf
│  (staff_a1/a3 NOT shown)
```

---

## Access Control

### Visibility

| Context | Admin | Same role | Subordinate role |
|---------|:-----:|:---------:|:----------------:|
| Org tree & list-all | All | Own only | All (supervisor) |
| Private | All | Own only | Not visible |
| General | All | All | All |

**Key rule**: same-role users cannot see each other's files. Supervisors see all subordinates'.

### Permissions

| Action | Admin | Creator | Others |
|--------|:-----:|:-------:|:------:|
| Create file/folder | Yes | Yes | Yes |
| Update/Delete/Move | Any | Own only | 403 |

---

## Error Responses

```json
{"detail": "Error message"}
```

| Code | Meaning |
|------|---------|
| `400` | Bad request |
| `401` | Unauthorized |
| `403` | Not creator/admin |
| `404` | Not found / soft-deleted |
| `422` | Validation error |
| `500` | Server error |

---

## Test Accounts (seed data)

All passwords: `123456`

| Account | Role | Sees |
|---------|------|------|
| `admin` | Admin (1) | Everything |
| `director` | Cuc truong (2) | All org tree |
| `deputy1` | Cuc pho (3) | Own + subtree, not deputy2 |
| `deputy2` | Cuc pho (3) | Own + subtree, not deputy1 |
| `head_a` | TP A (4) | Own + all NV Phong A |
| `head_b` | TP B (5) | Own + all NV Phong B |
| `staff_a1` | NV A (6) | Own only |
| `staff_a2` | NV A (6) | Own only |
| `staff_a3` | NV A (6) | Own only |
| `staff_b1` | NV B (7) | Own only |
| `staff_b2` | NV B (7) | Own only |
