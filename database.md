# Database Design - File Management System

## Overview

- **Folder tree** (nested folders using `parent_id` + `parent_path` TEXT, like Explorer/Finder)
- **File-Folder relationship** (files belong to folders)
- **Ownership** (`created_by` = `user_id`)
- **Type**: `private` (personal) / `organization` (pinned to role level) / `general` (visible to all)
- **Shared roles**: multiple users can share the same role (e.g. all NV Phòng A have role_id=5)
- **Admin**: role_id=1 has full access to all files/folders/tree across the entire org
- **node_path**: each file stores its full path in the tree: `type_<type>/role_<id>/.../folder_<id>/...`
- **Depth loading**: tree APIs support `depth` param to load multiple levels in one request

---

## Tables

### `roles` (tree of organizational positions)

Roles represent positions in the org tree. Multiple users can share the same role.
`parent_path` is comma-separated with leading/trailing commas: `,1,2,`

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Role ID |
| `name` | VARCHAR(255) | e.g. "Cuc truong", "NV Phong A" |
| `level` | INTEGER | Hierarchy level (1=admin/top) |
| `parent_path` | TEXT | Comma-separated ancestor IDs: `,1,2,` |
| `description` | TEXT | Description |
| `created_by` | INTEGER | Who created |
| `created_at` | TIMESTAMP | Created time |

**Example:**
```
Cuc truong (id=1)            parent_path=""         level=1  ← ADMIN
├── Cuc pho (id=2)           parent_path=",1,"      level=2
│   ├── TP Phong A (id=3)    parent_path=",1,2,"    level=3
│   │   └── NV Phong A (id=5) parent_path=",1,2,3," level=4  ← shared by staff_a1, staff_a2
│   └── TP Phong B (id=4)    parent_path=",1,2,"    level=3
│       └── NV Phong B (id=6) parent_path=",1,2,4," level=4  ← shared by staff_b1, staff_b2
```

### `users`

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | User ID |
| `account_name` | VARCHAR(50) UNIQUE | Login name |
| `role_id` | INTEGER FK → roles.id | Shared role (many users can have same role_id) |
| `full_name` | VARCHAR(100) | Display name |
| `status` | BOOLEAN | Active/inactive |

### `folders`

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | Folder ID |
| `name` | VARCHAR(255) | Folder name |
| `parent_id` | FK → folders.id | Parent folder (NULL = root) |
| `parent_path` | TEXT | Ancestor folder IDs: `,1,5,` |
| `created_by` | FK → users.id | Folder owner |
| `role_id` | FK → roles.id | Pinned role level (NULL for private/general) |
| `type` | VARCHAR(15) | `private` / `organization` / `general` |
| `description` | TEXT | Optional |
| `is_deleted` | BOOLEAN | Soft delete flag |

### `files`

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PK | File ID |
| `name` | TEXT | File name |
| `size` | INTEGER | Size in bytes |
| `hash` | VARCHAR(128) UNIQUE | SHA-256 hash |
| `path` | TEXT | Storage path (MinIO) |
| `extension` | VARCHAR(20) | File extension |
| `mime_type` | VARCHAR(100) | MIME type |
| `folder_id` | FK → folders.id | Containing folder (NULL = root) |
| `created_by` | FK → users.id | File owner |
| `role_id` | FK → roles.id | Pinned role (NULL for private/general) |
| `type` | VARCHAR(15) | `private` / `organization` / `general` |
| **`node_path`** | TEXT | **Full path in tree** (see below) |
| `is_deleted` | BOOLEAN | Soft delete flag |
| `is_processed` | BOOLEAN | Processing status |
| `processing_duration` | INTEGER | Seconds |
| `content` | TEXT | Extracted content |
| `summary` | TEXT | AI summary |

---

## node_path Format

`type_<type>/role_<id>/.../folder_<id>/...`

Computed from: file type + role's parent_path chain + folder's parent_path chain.

**Examples:**

```
File in director folder (role=1, folder=1):
  → type_organization/role_1/folder_1

File in deputy folder (role chain 1→2, folder=2):
  → type_organization/role_1/role_2/folder_2

File in sprint folder (role chain 1→2→3, folder chain 4→5):
  → type_organization/role_1/role_2/role_3/folder_4/folder_5

Root file at TP A (role chain 1→2→3, no folder):
  → type_organization/role_1/role_2/role_3

Private file in folder 8:
  → type_private/folder_8

General file in folder chain 9→10:
  → type_general/folder_9/folder_10
```

**Re-computed when:** file created, file moved, folder moved (batch update all files inside).

---

## Admin Rule

**role_id = 1** (Cuc truong) is admin:
- **Tree visibility**: sees full org tree from root (all roles, all folders, all files)
- **Permissions**: can update/delete/move any file or folder regardless of owner
- Other users: only see tree from their own role downward, can only modify own files

---

## Tree Display (depth examples)

### Admin (role=1) login, depth=4, type=organization:

```
▼ Cuc truong (role=1)
│  📄 bao_cao_q4_2024.pdf
│  📁 Bao cao tong hop/
│  ▼ Cuc pho (role=2)
│  │  📄 ke_hoach_2025.docx
│  │  📁 Ke hoach 2025/
│  │  │  📁 Du an noi bo/
│  │  ▼ TP Phong A (role=3)
│  │  │  📄 meeting_notes_q1.pdf
│  │  │  📁 Phong A - Tai lieu/
│  │  │  │  📁 Sprint Q1/                [▶] ← depth=4 reached
│  │  │  ▼ NV Phong A (role=5)
│  │  │  │  📁 NV_A notes/              [▶] ← depth=4 reached
│  │  ▼ TP Phong B (role=4)
│  │  │  📁 Phong B - Tai lieu/          [▶]
│  │  │  ▷ NV Phong B (role=6)           [▶]
```

### head_a (TP Phong A, role=3) login, depth=2:

```
▼ TP Phong A (role=3)
│  📄 meeting_notes_q1.pdf
│  📁 Phong A - Tai lieu/
│  │  📁 Sprint Q1/                      [▶] ← depth=2 reached
│  │  📄 sprint_report.xlsx
│  ▼ NV Phong A (role=5)
│  │  📁 NV_A notes/                     [▶] ← depth=2 reached
```

### staff_a1 (NV Phong A, role=5) login, depth=2:

```
▼ NV Phong A (role=5)
│  📁 NV_A notes/
│  │  📄 nv_a_report.docx               ← owned by staff_a1
│  │  📄 nv_a2_notes.pdf                ← owned by staff_a2 (same role)
```

### private (staff_a1):
```
📁 My private/
│  📄 ghi_chu_ca_nhan.txt
```

### general (everyone):
```
📁 Tai lieu chung/
│  📁 Mau bieu/
│  │  📄 mau_don_nghi_phep.docx
```

---

## Sample Data (JSON)

### roles
```json
[
  {"id": 1, "name": "Cuc truong",        "level": 1, "parent_path": ""},
  {"id": 2, "name": "Cuc pho",           "level": 2, "parent_path": ",1,"},
  {"id": 3, "name": "Truong phong A",    "level": 3, "parent_path": ",1,2,"},
  {"id": 4, "name": "Truong phong B",    "level": 3, "parent_path": ",1,2,"},
  {"id": 5, "name": "Nhan vien phong A", "level": 4, "parent_path": ",1,2,3,"},
  {"id": 6, "name": "Nhan vien phong B", "level": 4, "parent_path": ",1,2,4,"}
]
```

### users (shared roles)
```json
[
  {"id": 1, "account_name": "director", "role_id": 1, "full_name": "Nguyen Van A"},
  {"id": 2, "account_name": "deputy1",  "role_id": 2, "full_name": "Tran Van B"},
  {"id": 3, "account_name": "head_a",   "role_id": 3, "full_name": "Pham Van C"},
  {"id": 4, "account_name": "head_b",   "role_id": 4, "full_name": "Hoang Thi D"},
  {"id": 5, "account_name": "staff_a1", "role_id": 5, "full_name": "Do Van E"},
  {"id": 6, "account_name": "staff_a2", "role_id": 5, "full_name": "Le Thi F"},
  {"id": 7, "account_name": "staff_b1", "role_id": 6, "full_name": "Vu Van G"},
  {"id": 8, "account_name": "staff_b2", "role_id": 6, "full_name": "Bui Thi H"}
]
```

### files (with node_path)
```json
[
  {"id": 1, "name": "bao_cao_q4.pdf",       "folder_id": 1,    "role_id": 1, "type": "organization", "node_path": "type_organization/role_1/folder_1"},
  {"id": 2, "name": "ke_hoach_2025.docx",   "folder_id": 2,    "role_id": 2, "type": "organization", "node_path": "type_organization/role_1/role_2/folder_2"},
  {"id": 3, "name": "sprint_report.xlsx",   "folder_id": 5,    "role_id": 3, "type": "organization", "node_path": "type_organization/role_1/role_2/role_3/folder_4/folder_5"},
  {"id": 4, "name": "ghi_chu.txt",          "folder_id": 8,    "role_id": null, "type": "private",   "node_path": "type_private/folder_8"},
  {"id": 5, "name": "mau_don.docx",         "folder_id": 10,   "role_id": null, "type": "general",   "node_path": "type_general/folder_9/folder_10"},
  {"id": 6, "name": "meeting_notes.pdf",    "folder_id": null,  "role_id": 3, "type": "organization", "node_path": "type_organization/role_1/role_2/role_3"},
  {"id": 7, "name": "nv_a_report.docx",     "folder_id": 7,    "role_id": 5, "type": "organization", "node_path": "type_organization/role_1/role_2/role_3/role_5/folder_7"},
  {"id": 8, "name": "nv_a2_notes.pdf",      "folder_id": 7,    "role_id": 5, "type": "organization", "node_path": "type_organization/role_1/role_2/role_3/role_5/folder_7"}
]
```
