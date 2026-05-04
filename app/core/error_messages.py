"""Centralized error codes and message templates.

Every entry is a (CODE, MSG) tuple. CODE is stable/immutable once shipped
(frontend uses it for i18n and conditional logic). MSG is a human-readable
template; use .format() for parameterized values.
"""

# ── Folder / File tree ──────────────────────────────────────────────
ADMIN_CANNOT_CREATE_ORG = (
    "ADMIN_CANNOT_CREATE_ORG",
    "Admin cannot create organization files or folders",
)
FOLDER_NOT_FOUND = ("FOLDER_NOT_FOUND", "Folder not found")
FILE_NOT_FOUND = ("FILE_NOT_FOUND", "File not found")
PARENT_FOLDER_NOT_FOUND = (
    "PARENT_FOLDER_NOT_FOUND",
    "Parent folder {parent_id} not found",
)
FOLDER_TYPE_MISMATCH = (
    "FOLDER_TYPE_MISMATCH",
    "Folder type does not match file/folder type",
)
FOLDER_ROLE_MISMATCH = (
    "FOLDER_ROLE_MISMATCH",
    "Folder belongs to a different role",
)
FOLDER_OWNER_MISMATCH = (
    "FOLDER_OWNER_MISMATCH",
    "Folder belongs to another user",
)
CANNOT_MOVE_INTO_DESCENDANT = (
    "CANNOT_MOVE_INTO_DESCENDANT",
    "Cannot move a folder into its own descendant",
)
CANNOT_MOVE_INTO_SELF = (
    "CANNOT_MOVE_INTO_SELF",
    "Cannot move a folder into itself",
)
ONLY_CREATOR_OR_ADMIN = (
    "ONLY_CREATOR_OR_ADMIN",
    "Only the creator or admin can perform this action",
)
USER_MUST_HAVE_ROLE_FOR_ORG = (
    "USER_MUST_HAVE_ROLE_FOR_ORG",
    "User must have a role to create organization files or folders",
)
INVALID_NODE_TYPE = (
    "INVALID_NODE_TYPE",
    "node_type must be one of: role, folder, user",
)
