# API Documentation — File Management System

All endpoints require `Authorization: Bearer <token>`.

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `ADMIN_ROLE_ID` | 1 | Role ID with full admin access (configurable in `.env`) |

## Key Concepts

- **Admin** (`ADMIN_ROLE_ID`, default role_id=1): separate from org tree, sees everything, can update/delete/move any item. **Cannot** create organization files/folders.
- **Shared roles**: multiple users can have the same role_id (e.g. all staff in Phong A share role_id=6)
- **Same-role isolation**: active users with the same role cannot see each other's files/folders in the tree. Supervisors (parent role) see all subordinates' content. Inactive/departed predecessors' files ARE visible to successors.
- **Private files**: only visible to their creator (admin sees all, supervisors don't)
- **General files**: visible to everyone
- **node_path**: each file stores its full position in the tree: `type_<type>/role_<id>/.../user_<id>/folder_<id>/...`
- **Depth loading**: tree APIs support `depth` param to load multiple levels in one request
- **User nodes**: in the organization tree, each role contains user nodes. Files/folders live under user nodes, not directly under roles.

## Role Tree (seed data)

```
Admin (id=1)             <- separate, not in org tree, level=0
Cuc truong (id=2)        <- org tree root, level=1
+-- Cuc pho (id=3)       <- level=2
    +-- TP Phong A (id=4) <- level=3
    |   +-- NV Phong A (id=6) <- level=4, shared by staff_a1/a2/a3
    +-- TP Phong B (id=5) <- level=3
        +-- NV Phong B (id=7) <- level=4, shared by staff_b1/b2
```

---

## Folder Management -- `/api/v1/folders`

### POST `/` -- Create Folder

`created_by` and `role_id` from auth. `parent_path` computed server-side from `parent_id`.

**Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | -- | Folder name (max 255) |
| `parent_id` | int \| null | No | null | Parent folder ID. null = root |
| `type` | string | No | "private" | `private`, `organization`, `general` |
| `description` | string \| null | No | null | Description |

**Validation (organization type):**
- Admin (`ADMIN_ROLE_ID`) cannot create organization folders -> `403 ADMIN_CANNOT_CREATE_ORG`
- Parent folder must match `type` -> `400 FOLDER_TYPE_MISMATCH`
- Parent folder must belong to same `role_id` -> `400 FOLDER_ROLE_MISMATCH`
- Parent folder must be owned by the current user -> `403 FOLDER_OWNER_MISMATCH`
- Private/general: no owner restriction on parent

**Response `201`:** Folder object with `id`, `created_by`, `role_id`, `parent_path`, etc.

### PUT `/{folder_id}` -- Update Folder

Update name/description. Creator or admin only. **Errors:** `403`, `404`.

### DELETE `/{folder_id}` -- Soft Delete Folder

Soft delete folder + descendants + all files inside. Creator or admin only. **Response `204`.**

### PUT `/{folder_id}/move` -- Move Folder

Move to new parent. Updates `parent_path` for descendants, re-computes `node_path` for all files. Creator or admin only.

**Body:** `new_parent_id` (int \| null).

**Validation:** circular move, self-move, type mismatch, role mismatch, owner mismatch (organization only).

### GET `/{folder_id}` -- Get Folder by ID

### GET `/tree/root` -- Tree Root (with depth)

**Query Params:**

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `type_filter` | Yes | -- | `organization`, `private`, `general` |
| `depth` | No | 1 | Levels to load (1-10) |
| `search_text` | No | -- | Search by file/folder name, owner name, or role name |
| `owner_name` | No | -- | Filter by owner full_name |
| `role_name` | No | -- | Filter by role name |

**Visibility (organization type):**
- **Admin**: sees full org tree from root, all user nodes
- **Other users**: see from own role downward
- **Same-role isolation**: at own role level, only own user node shown + inactive/departed predecessors' user nodes visible
- **Subordinate roles**: all user nodes visible (active + inactive/departed)

**depth behavior:**
- `depth=1`: children with `has_children` flag, `children: null`
- `depth=2+`: children populated recursively, stops when depth runs out

**Order:** user nodes first (current user's own node first if present), then child role nodes. Each group newest-first by `created_at`.

**Example: `GET /tree/root?type_filter=organization&depth=2` (user=head_a, role=4):**
```json
{
  "current_role": {"id": 4, "name": "Truong phong A"},
  "children": [
    {"node_type": "user", "id": 4, "account_name": "head_a",
     "full_name": "Pham Van C", "role_id": 4, "is_active": true,
     "has_children": true,
     "children": [
       {"node_type": "file", "id": 5, "name": "meeting_notes_q1.pdf",
        "node_path": "type_organization/role_2/role_3/role_4/user_4",
        "owner": {"id": 4, "full_name": "Pham Van C"}},
       {"node_type": "folder", "id": 4, "name": "Phong A - Tai lieu",
        "has_children": true, "children": null}
     ]},
    {"node_type": "role", "id": 6, "name": "Nhan vien phong A",
     "has_children": true,
     "children": [
       {"node_type": "user", "id": 6, "account_name": "staff_a1",
        "full_name": "Do Van E", "role_id": 6, "is_active": true,
        "has_children": true},
       {"node_type": "user", "id": 7, "account_name": "staff_a2",
        "full_name": "Le Thi F", "role_id": 6, "is_active": true,
        "has_children": true},
       {"node_type": "user", "id": 8, "account_name": "staff_a3",
        "full_name": "Vo Van G", "role_id": 6, "is_active": true,
        "has_children": true}
     ]}
  ]
}
```

### GET `/tree/{node_id}` -- Expand Node (with depth)

**Query Params:**

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `node_type` | Yes | -- | `role`, `folder`, or `user` |
| `depth` | No | 1 | Levels to load |
| `page` | No | 1 | Page number |
| `page_size` | No | 20 | Items per page (max 100) |
| `search_text` | No | -- | Search by name |
| `owner_name` | No | -- | Filter by creator name |
| `role_name` | No | -- | Filter by role name |
| `parent_role_id` | No | -- | Required when `node_type=user`. Role context where the user node appears. A user may appear under multiple roles (current + historical). |

**`parent_role_id` explanation:**

A user can appear under multiple role nodes:
- Under their current role (active user)
- Under a previous role (if they created files there and have since left or been deactivated)

When expanding a user node, `parent_role_id` tells the server which role context to use:

```
GET /tree/3?node_type=user&parent_role_id=2&depth=2
GET /tree/3?node_type=user&parent_role_id=3&depth=2
```

Same user id (3), different role contexts -> different files returned.

### POST `/query` -- Query Folders (flat list)

**Body:** `parent_id`, `type`, `search_text`, `page`, `page_size` (all optional)

---

## File Management -- `/api/v1/files`

### Existing APIs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload file (via `general-chatbot-files` service) |
| `POST` | `/my-files` | Query user's files (cursor pagination) |
| `POST` | `/my-with-children` | Query files including children hierarchy |
| `POST` | `/extract-file-content` | Extract content from file |
| `GET` | `/dashboard` | File dashboard statistics |
| `POST` | `/period-stats` | Period statistics |
| `POST` | `/country-tech-stats` | Country & tech statistics |

### GET `/detail/{file_id}` -- Get File Detail

Full file detail: all metadata, content, classification, owner info, `node_path`.

**Response `200`:**
```json
{
  "id": 6, "name": "sprint_report.xlsx",
  "size": 128000, "hash": "seed_006",
  "created_by": 4, "folder_id": 5, "role_id": 4,
  "type": "organization",
  "node_path": "type_organization/role_2/role_3/role_4/user_4/folder_4/folder_5",
  "owner": {"id": 4, "full_name": "Pham Van C"},
  "is_processed": null, "content": null, "summary": null,
  "is_deleted": false
}
```

### PUT `/update/{file_id}` -- Update File Name

Creator or admin only. **Body:** `name` (optional). **Response `200`:** file dict.

### DELETE `/delete/{file_id}` -- Soft Delete File

Creator or admin only. **Response `204`.** Re-uploading the same file after soft-delete is allowed (dedup checks `is_deleted=false`).

### PUT `/move/{file_id}` -- Move File

Move to another folder. Re-computes `node_path`. Creator or admin only.

**Body:** `new_folder_id` (int \| null)

### POST `/list-all` -- Get All Accessible Files (flat list)

Returns files the current user is allowed to see.

**Visibility rules:**
- **Organization**: files at own role (only own `created_by`) + files at all subordinate roles (all creators). This ensures files from transferred/inactive predecessors remain visible to successors via role hierarchy.
- **Private**: only files created by current user
- **General**: all general files visible to everyone
- **Admin**: sees all files regardless of type
- **Same-role isolation**: at own role level, only own files shown (peers hidden)

**Body:** all optional.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `started_node` | int | null | Subtree root id. Must be sent with `type_node`. |
| `type_node` | string | null | Subtree root type: `folder`, `role`, or `user`. Must be sent with `started_node`. |
| `type` | string | null | Filter: `private` / `organization` / `general` |
| `owner_name` | string | null | Filter by creator full_name (ilike) |
| `search_text` | string | null | Free-text search across file name, folder name, owner full_name, role name (case-insensitive OR) |
| `is_processed` | bool | null | `true` = processed, `false` = failed, omit/null = all |
| `sort_by` | string | "created_at" | Sort field(s): `created_at`, `size`. Multi: `"size,created_at"` |
| `sort_order` | string | "desc" | Sort direction(s): `asc`, `desc`. Multi: `"asc,desc"` |
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Items per page (max 100) |

**Subtree filter (`started_node` + `type_node`):**

Both must be sent together. Matches files whose `node_path` contains the segment `<type_node>_<started_node>`. Recursive -- any file anywhere below that node is returned.

- `started_node=4, type_node="folder"` -> files with node_path containing `folder_4/`
- `started_node=3, type_node="role"` -> files under role 3 subtree
- `started_node=5, type_node="user"` -> files created by user 5 in their user-node

**Sort:**

Single field:
```json
{"sort_by": "size", "sort_order": "asc"}
```

Multi-field (first sort takes priority):
```json
{"sort_by": "size,created_at", "sort_order": "asc,desc"}
```
If fewer `sort_order` values than `sort_by`, the last direction is reused.

**Visibility examples:**

| User | Sees (organization) |
|------|-----------|
| admin (role=1) | All files |
| director (role=2) | Files at role 2 (own) + all subordinate roles |
| deputy1 (role=3) | Own files at role 3 + files at roles 4,5,6,7 |
| staff_a1 (role=6) | Own files only (not a2/a3 -- same-role isolation) |

**Response:**
```json
{
  "data": [
    {
      "id": 6, "name": "sprint_report.xlsx", "size": 128000,
      "node_path": "type_organization/role_2/role_3/role_4/user_4/folder_4/folder_5",
      "owner": {"id": 4, "full_name": "Pham Van C"},
      "is_processed": null, "processing_duration": null,
      "content": "...", "summary": "...",
      "created_at": "...", "updated_at": "..."
    }
  ],
  "total": 8,
  "message": "succeeded"
}
```

---

## Tree Node Types

### `node_type: "user"`
```json
{
  "node_type": "user", "id": 5, "account_name": "staff_a1",
  "full_name": "Do Van E", "role_id": 6,
  "is_active": true, "has_children": true,
  "children": [...]
}
```
- `role_id`: the role context where this node appears (NOT necessarily `users.role_id` -- a user can appear under a historical role)
- `is_active`: `users.status` -- FE can show `[inactive]` badge for predecessors
- `children`: files + folders the user created at this role's root level. Populated when depth > 1.

**Who appears as a user node under a role:**
1. Active users currently assigned (`users.role_id == X, status=true`)
2. Inactive users at this role who have files (`status=false, role_id=X`)
3. Users who left this role (`role_id != X`) but have files at role X

Groups 2 and 3 only visible when they are NOT active peers at the same role (same-role isolation preserved).

### `node_type: "file"`
```json
{
  "node_type": "file", "id": 6, "name": "sprint_report.xlsx",
  "size": 128000, "extension": ".xlsx",
  "node_path": "type_organization/role_2/role_3/role_4/user_4/folder_4/folder_5",
  "owner": {"id": 4, "full_name": "Pham Van C"},
  "created_at": "...", "is_processed": null,
  "processing_duration": null, "content": "...", "summary": "..."
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
`children`: user nodes + child role nodes. Files/folders no longer appear directly under role.

---

## node_path Format

`type_<type>/role_<id>/.../user_<id>/folder_<id>/...`

For `type=organization`, the path includes the role chain, then the owning user, then the folder chain. For `private`/`general`, user and role segments are omitted.

| Location | node_path |
|----------|-----------|
| Director (user=2) root | `type_organization/role_2/user_2` |
| Director folder 1 | `type_organization/role_2/user_2/folder_1` |
| Deputy1 (user=3) folder 2 | `type_organization/role_2/role_3/user_3/folder_2` |
| Head A (user=4) folder 4 -> 5 | `type_organization/role_2/role_3/role_4/user_4/folder_4/folder_5` |
| Staff A1 (user=6) folder 8 | `type_organization/role_2/role_3/role_4/role_6/user_6/folder_8` |
| Private folder 12 | `type_private/folder_12` |
| General folder 14 -> 15 | `type_general/folder_14/folder_15` |

**Re-computed when:** file created, file moved, folder moved (batch update).

---

## Tree Display Examples

> Each role node contains **user nodes** and child role nodes. Files and folders live under user nodes. Child roles are flat siblings of user nodes.

### admin (role=1) login, depth=4, type=organization

```
V Role: Cuc truong (2)
|  V User: Nguyen Van A
|  |  file bao_cao_q4.pdf
|  |  folder Bao cao tong hop/
|  V Role: Cuc pho (3)
|  |  V User: Tran Van B (deputy1)
|  |  |  folder Ke hoach 2025/
|  |  |  |  folder Du an noi bo/
|  |  V User: Dang Van K (deputy2)
|  |  |  folder Ke hoach deputy2/
|  |  V Role: TP Phong A (4)
|  |  |  V User: head_a
|  |  |  |  file meeting_notes_q1.pdf
|  |  |  |  folder Phong A - Tai lieu/
|  |  |  |  |  folder Sprint Q1/            [>]
|  |  |  V Role: NV Phong A (6)
|  |  |  |  V User: staff_a1
|  |  |  |  |  folder NV_A1 docs/           [>]
|  |  |  |  V User: staff_a2
|  |  |  |  |  file nv_a2_research.docx
|  |  |  |  |  folder NV_A2 docs/           [>]
|  |  |  |  V User: staff_a3
|  |  |  |  |  file nv_a3_draft.pdf
|  |  V Role: TP Phong B (5)
|  |  |  V User: head_b
|  |  |  |  folder Phong B - Tai lieu/      [>]
|  |  |  V Role: NV Phong B (7)             [>]
```

### head_a (role=4) login, depth=2

```
V Role: TP Phong A (4)
|  V User: head_a                           <- only self (same-role isolation)
|  |  file meeting_notes_q1.pdf
|  |  folder Phong A - Tai lieu/
|  |  |  folder Sprint Q1/                  [>]
|  V Role: NV Phong A (6)                   <- subordinate: all users visible
|  |  V User: staff_a1
|  |  |  folder NV_A1 docs/                 [>]
|  |  V User: staff_a2
|  |  |  file nv_a2_research.docx
|  |  |  folder NV_A2 docs/                 [>]
|  |  V User: staff_a3
|  |  |  file nv_a3_draft.pdf
```

### staff_a1 (role=6) login, depth=2

```
V Role: NV Phong A (6)
|  V User: staff_a1                          <- only self (peers hidden)
|  |  folder NV_A1 docs/
|  |  |  file nv_a1_report.docx
|  |  |  file nv_a1_data.xlsx
```

### Role change example: deputy1 promoted to Cuc truong

After deputy1 (user=3) is moved from role 3 to role 2, and director (user=2) is moved away or deactivated:

```
V Role: Cuc truong (2)
|  V User: Nguyen Van A [inactive]           <- predecessor, files inherited
|  |  file bao_cao_q4.pdf                    <- created_by=2, role_id=2
|  V User: Tran Van B                        <- successor, new files go here
|  |  file bao_cao_2026.pdf                  <- created_by=3, role_id=2
|  V Role: Cuc pho (3)
|  |  V User: Tran Van B                     <- historical: files still at role 3
|  |  |  folder Ke hoach 2025/               <- created_by=3, role_id=3
|  |  V User: Nguyen Van X                   <- new deputy
```

---

## Access Control

### Visibility

| Context | Admin | Same role (active peers) | Subordinate role | Inactive/departed predecessors |
|---------|:-----:|:---------:|:----------------:|:---:|
| Org tree & list-all | All | Own only | All (supervisor) | Visible to successors |
| Private | All | Own only | Not visible | Not visible |
| General | All | All | All | All |

**Key rules:**
- Active same-role users cannot see each other's files (isolation)
- Supervisors see all subordinates' files
- When a user leaves a role (inactive or transferred), their files become visible to whoever now holds that role
- Files belong to the position (role), not the person -- they stay at `file.role_id` permanently

### Permissions

| Action | Admin | Creator | Others |
|--------|:-----:|:-------:|:------:|
| Create org file/folder | No (403) | Yes (own role only) | No |
| Create private/general | Yes | Yes | Yes |
| Update/Delete/Move | Any | Own only | 403 |

### Upload validation (organization type)

- `role_id` derived from JWT -- caller cannot override
- Admin cannot create organization files/folders (`ADMIN_CANNOT_CREATE_ORG`)
- Target folder must match `file_type` (`FOLDER_TYPE_MISMATCH`)
- Target folder must belong to same `role_id` (`FOLDER_ROLE_MISMATCH`)
- Target folder must be owned by current user (`FOLDER_OWNER_MISMATCH`)
- Private/general: no owner restriction on target folder
- Duplicate upload after soft-delete: allowed

---

## Error Responses

### Response shape

All error responses include both `detail` and `message`:

```json
{
  "detail": "Folder belongs to a different role",
  "message": "Folder belongs to a different role",
  "code": "FOLDER_ROLE_MISMATCH",
  "status": 400
}
```

- `detail` -- human-readable message (may be string or structured dict/list)
- `message` -- always a string, same as detail for simple errors. FE can use `body.message` for toast display.
- `code` -- stable machine-readable identifier (for i18n / conditional handling). Immutable once shipped.
- `status` -- HTTP status code

Upload batch response also includes top-level `message`:
```json
{
  "total": 1, "succeeded": 0, "failed": 1,
  "message": "Folder belongs to a different role",
  "files": [{"file_name": "...", "success": false, "error": "...", "code": "FOLDER_ROLE_MISMATCH", "data": null}],
  "folders_created": []
}
```

FastAPI request validation errors (422) keep their default shape.

### HTTP status codes

| Code | Meaning |
|------|---------|
| `400` | Bad request |
| `401` | Unauthorized |
| `403` | Forbidden (not creator/admin, admin org block, owner mismatch) |
| `404` | Not found / soft-deleted |
| `422` | Validation error (FastAPI default shape) |
| `500` | Server error |

### Error codes

| Code | Status | When |
|---|---|---|
| `ADMIN_CANNOT_CREATE_ORG` | 403 | Admin tries to create an organization file/folder |
| `FOLDER_NOT_FOUND` | 404 | Folder id does not exist or is soft-deleted |
| `FILE_NOT_FOUND` | 404 | File id does not exist or is soft-deleted |
| `PARENT_FOLDER_NOT_FOUND` | 400 | `parent_id` passed to create does not exist |
| `FOLDER_TYPE_MISMATCH` | 400 | Target folder's type does not match file/folder type |
| `FOLDER_ROLE_MISMATCH` | 400 | Target folder's role_id does not match the user's role_id |
| `FOLDER_OWNER_MISMATCH` | 403 | Target folder belongs to another user (organization type) |
| `CANNOT_MOVE_INTO_DESCENDANT` | 400 | Circular move attempt |
| `CANNOT_MOVE_INTO_SELF` | 400 | Folder moved into itself |
| `ONLY_CREATOR_OR_ADMIN` | 403 | Non-creator, non-admin attempts to update/delete/move |
| `USER_MUST_HAVE_ROLE_FOR_ORG` | 400 | User without role tries to create organization file/folder |
| `HTTP_<status>` | varies | Legacy HTTPException paths return `HTTP_<status_code>` as fallback code |

---

## Test Accounts (seed data)

All passwords: `123456`

| Account | User ID | Role | Sees (organization) |
|---------|---------|------|------|
| `admin` | 1 | Admin (1) | Everything |
| `director` | 2 | Cuc truong (2) | All org tree |
| `deputy1` | 3 | Cuc pho (3) | Own + subtree, not deputy2 |
| `head_a` | 4 | TP A (4) | Own + all NV Phong A |
| `head_b` | 5 | TP B (5) | Own + all NV Phong B |
| `staff_a1` | 6 | NV A (6) | Own only (not a2/a3) |
| `staff_a2` | 7 | NV A (6) | Own only (not a1/a3) |
| `staff_a3` | 8 | NV A (6) | Own only (not a1/a2) |
| `staff_b1` | 9 | NV B (7) | Own only (not b2) |
| `staff_b2` | 10 | NV B (7) | Own only (not b1) |
| `deputy2` | 11 | Cuc pho (3) | Own + subtree, not deputy1 |
