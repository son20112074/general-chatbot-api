"""
Seed Data Script — Comprehensive test data

Role tree:
  Admin (1)          ← separate, not in org tree, full access
  Cuc truong (2)     ← root of org tree
  └── Cuc pho (3)
      ├── TP A (4)
      │   └── NV A (6) ← shared: staff_a1, staff_a2, staff_a3
      └── TP B (5)
          └── NV B (7) ← shared: staff_b1, staff_b2

Usage:
    python seed_data.py
"""
import asyncio
import bcrypt
from sqlalchemy import text
from app.core.database import AsyncSessionLocal


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


async def seed():
    async with AsyncSessionLocal() as db:
        try:
            # Always wipe and re-seed. TRUNCATE ... RESTART IDENTITY CASCADE
            # resets sequences and cascades through FKs.
            print("Wiping existing data (files, folders, users, roles)...")
            await db.execute(text(
                "TRUNCATE TABLE files, folders, users, roles "
                "RESTART IDENTITY CASCADE"
            ))

            pw = hash_password("123456")

            # ══════════════════════════════════════════════
            # 1. ROLES
            #   Admin (1)            ""        level=0  ← ADMIN, separate from org tree
            #   Cuc truong (2)       ""        level=1  ← org tree root
            #   └── Cuc pho (3)      ",2,"     level=2
            #       ├── TP A (4)     ",2,3,"   level=3
            #       │   └── NV A (6) ",2,3,4," level=4
            #       └── TP B (5)     ",2,3,"   level=3
            #           └── NV B (7) ",2,3,5," level=4
            # ══════════════════════════════════════════════
            print("Inserting roles...")
            await db.execute(text("""
                INSERT INTO roles (id, name, level, parent_path, description, created_by, created_at) VALUES
                (1, 'Admin',             0, '',         'System admin — full access, outside org tree', NULL, NOW()),
                (2, 'Cuc truong',        1, '',         'Director — org tree root',                    1,    NOW()),
                (3, 'Cuc pho',           2, ',2,',      'Deputy Director',                             1,    NOW()),
                (4, 'Truong phong A',    3, ',2,3,',    'Head of Dept A',                              1,    NOW()),
                (5, 'Truong phong B',    3, ',2,3,',    'Head of Dept B',                              1,    NOW()),
                (6, 'Nhan vien phong A', 4, ',2,3,4,',  'Staff Dept A (shared role)',                  4,    NOW()),
                (7, 'Nhan vien phong B', 4, ',2,3,5,',  'Staff Dept B (shared role)',                  5,    NOW())
            """))
            await db.execute(text("SELECT setval('roles_id_seq', (SELECT MAX(id) FROM roles))"))

            # ══════════════════════════════════════════════
            # 2. USERS
            #  id=1  admin      role=1 (Admin)
            #  id=2  director   role=2 (Cuc truong)
            #  id=3  deputy1    role=3 (Cuc pho)
            #  id=4  head_a     role=4 (TP A)
            #  id=5  head_b     role=5 (TP B)
            #  id=6  staff_a1   role=6 (NV A)  ┐
            #  id=7  staff_a2   role=6 (NV A)  ┤ same role
            #  id=8  staff_a3   role=6 (NV A)  ┘
            #  id=9  staff_b1   role=7 (NV B)  ┐
            #  id=10 staff_b2   role=7 (NV B)  ┘ same role
            #  id=11 deputy2    role=3 (another deputy)
            # ══════════════════════════════════════════════
            print("Inserting users...")
            await db.execute(text("""
                INSERT INTO users (id, account_name, full_name, role_id, password, status, created_at) VALUES
                (1,  'admin',     'System Admin',   1, :pw, true, NOW()),
                (2,  'director',  'Nguyen Van A',   2, :pw, true, NOW()),
                (3,  'deputy1',   'Tran Van B',     3, :pw, true, NOW()),
                (4,  'head_a',    'Pham Van C',     4, :pw, true, NOW()),
                (5,  'head_b',    'Hoang Thi D',    5, :pw, true, NOW()),
                (6,  'staff_a1',  'Do Van E',       6, :pw, true, NOW()),
                (7,  'staff_a2',  'Le Thi F',       6, :pw, true, NOW()),
                (8,  'staff_a3',  'Vo Van G',       6, :pw, true, NOW()),
                (9,  'staff_b1',  'Vu Van H',       7, :pw, true, NOW()),
                (10, 'staff_b2',  'Bui Thi I',      7, :pw, true, NOW()),
                (11, 'deputy2',   'Dang Van K',     3, :pw, true, NOW())
            """), {"pw": pw})
            await db.execute(text("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users))"))

            # ══════════════════════════════════════════════
            # 3. FOLDERS
            # ══════════════════════════════════════════════
            print("Inserting folders...")
            await db.execute(text("""
                INSERT INTO folders (id, name, parent_id, parent_path, created_by, role_id, type, description, is_deleted, created_at, updated_at) VALUES
                -- Organization
                (1,  'Bao cao tong hop',   NULL, NULL,   2,  2, 'organization', 'Director reports',        false, NOW(), NOW()),
                (2,  'Ke hoach 2025',      NULL, NULL,   3,  3, 'organization', 'Deputy1 plans',           false, NOW(), NOW()),
                (3,  'Du an noi bo',       2,    ',2,',  3,  3, 'organization', 'Internal projects',       false, NOW(), NOW()),
                (4,  'Phong A - Tai lieu', NULL, NULL,   4,  4, 'organization', 'Dept A documents',        false, NOW(), NOW()),
                (5,  'Sprint Q1',          4,    ',4,',  4,  4, 'organization', 'Q1 sprint docs',          false, NOW(), NOW()),
                (6,  'Sprint Q2',          4,    ',4,',  4,  4, 'organization', 'Q2 sprint docs',          false, NOW(), NOW()),
                (7,  'Phong B - Tai lieu', NULL, NULL,   5,  5, 'organization', 'Dept B documents',        false, NOW(), NOW()),
                (8,  'NV_A1 docs',         NULL, NULL,   6,  6, 'organization', 'Staff A1 org docs',       false, NOW(), NOW()),
                (9,  'NV_A2 docs',         NULL, NULL,   7,  6, 'organization', 'Staff A2 org docs',       false, NOW(), NOW()),
                (10, 'NV_B1 docs',         NULL, NULL,   9,  7, 'organization', 'Staff B1 org docs',       false, NOW(), NOW()),
                (11, 'Ke hoach deputy2',   NULL, NULL,   11, 3, 'organization', 'Deputy2 plans',           false, NOW(), NOW()),
                -- Private
                (12, 'My private A1',      NULL, NULL,   6,  NULL, 'private', 'staff_a1 personal',         false, NOW(), NOW()),
                (13, 'My private A2',      NULL, NULL,   7,  NULL, 'private', 'staff_a2 personal',         false, NOW(), NOW()),
                -- General
                (14, 'Tai lieu chung',     NULL, NULL,   1,  NULL, 'general', 'Shared docs',               false, NOW(), NOW()),
                (15, 'Mau bieu',           14,   ',14,', 1,  NULL, 'general', 'Form templates',            false, NOW(), NOW())
            """))
            await db.execute(text("SELECT setval('folders_id_seq', (SELECT MAX(id) FROM folders))"))

            # ══════════════════════════════════════════════
            # 4. FILES (20 files with node_path)
            # ══════════════════════════════════════════════
            print("Inserting files...")
            await db.execute(text("""
                INSERT INTO files (id, name, size, hash, path, extension, mime_type,
                    folder_id, created_by, role_id, type, node_path, is_deleted,
                    created_at, updated_at, is_processed, processing_duration, content, summary, is_embedded) VALUES
                -- Director files (role=2, user=2)
                (1, 'bao_cao_q4.pdf', 2048000, 'seed_001', 'uploads/seed_001.pdf', '.pdf', 'application/pdf',
                    1, 2, 2, 'organization', 'type_organization/role_2/user_2/folder_1', false,
                    NOW() - interval '10 days', NOW(), true, 12, 'Q4 report', 'Q4 summary', true),
                (2, 'chi_thi_2025.docx', 500000, 'seed_002', 'uploads/seed_002.docx', '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    NULL, 2, 2, 'organization', 'type_organization/role_2/user_2', false,
                    NOW() - interval '9 days', NOW(), true, 5, 'Directive', 'Directive summary', false),
                -- Deputy1 files (role=3, user=3)
                (3, 'ke_hoach_2025.docx', 512000, 'seed_003', 'uploads/seed_003.docx', '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    2, 3, 3, 'organization', 'type_organization/role_2/role_3/user_3/folder_2', false,
                    NOW() - interval '8 days', NOW(), true, 8, 'Plan 2025', '2025 plan', false),
                -- Deputy2 files (role=3, user=11) — deputy1 should NOT see
                (4, 'deputy2_report.pdf', 300000, 'seed_004', 'uploads/seed_004.pdf', '.pdf', 'application/pdf',
                    11, 11, 3, 'organization', 'type_organization/role_2/role_3/user_11/folder_11', false,
                    NOW() - interval '7 days', NOW(), true, 3, 'Deputy2 report', 'D2 summary', false),
                -- Head A files (role=4, user=4)
                (5, 'meeting_notes_q1.pdf', 56000, 'seed_005', 'uploads/seed_005.pdf', '.pdf', 'application/pdf',
                    NULL, 4, 4, 'organization', 'type_organization/role_2/role_3/role_4/user_4', false,
                    NOW() - interval '6 days', NOW(), true, 5, 'Meeting Q1', 'Q1 summary', false),
                (6, 'sprint_report.xlsx', 128000, 'seed_006', 'uploads/seed_006.xlsx', '.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    5, 4, 4, 'organization', 'type_organization/role_2/role_3/role_4/user_4/folder_4/folder_5', false,
                    NOW() - interval '5 days', NOW(), NULL, NULL, NULL, NULL, NULL),
                (7, 'q2_plan.docx', 90000, 'seed_007', 'uploads/seed_007.docx', '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    6, 4, 4, 'organization', 'type_organization/role_2/role_3/role_4/user_4/folder_4/folder_6', false,
                    NOW() - interval '4 days', NOW(), true, 4, 'Q2 plan', 'Q2 plan summary', false),
                -- Head B files (role=5, user=5)
                (8, 'phongb_report.pdf', 200000, 'seed_008', 'uploads/seed_008.pdf', '.pdf', 'application/pdf',
                    7, 5, 5, 'organization', 'type_organization/role_2/role_3/role_5/user_5/folder_7', false,
                    NOW() - interval '3 days', NOW(), true, 6, 'Phong B report', 'B report', false),
                -- Staff A1 (role=6, user=6) — a2/a3 NOT see
                (9, 'nv_a1_report.docx', 88000, 'seed_009', 'uploads/seed_009.docx', '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    8, 6, 6, 'organization', 'type_organization/role_2/role_3/role_4/role_6/user_6/folder_8', false,
                    NOW() - interval '2 days', NOW(), true, 2, 'A1 report', 'A1 summary', false),
                (10, 'nv_a1_data.xlsx', 45000, 'seed_010', 'uploads/seed_010.xlsx', '.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    8, 6, 6, 'organization', 'type_organization/role_2/role_3/role_4/role_6/user_6/folder_8', false,
                    NOW() - interval '1 day', NOW(), NULL, NULL, NULL, NULL, NULL),
                -- Staff A2 (role=6, user=7) — a1/a3 NOT see
                (11, 'nv_a2_notes.pdf', 32000, 'seed_011', 'uploads/seed_011.pdf', '.pdf', 'application/pdf',
                    9, 7, 6, 'organization', 'type_organization/role_2/role_3/role_4/role_6/user_7/folder_9', false,
                    NOW() - interval '2 days', NOW(), true, 2, 'A2 notes', 'A2 summary', false),
                (12, 'nv_a2_research.docx', 67000, 'seed_012', 'uploads/seed_012.docx', '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    NULL, 7, 6, 'organization', 'type_organization/role_2/role_3/role_4/role_6/user_7', false,
                    NOW() - interval '1 day', NOW(), true, 3, 'A2 research', 'A2 research', false),
                -- Staff A3 (role=6, user=8) — a1/a2 NOT see
                (13, 'nv_a3_draft.pdf', 25000, 'seed_013', 'uploads/seed_013.pdf', '.pdf', 'application/pdf',
                    NULL, 8, 6, 'organization', 'type_organization/role_2/role_3/role_4/role_6/user_8', false,
                    NOW() - interval '12 hours', NOW(), false, 1, 'A3 draft', 'A3 draft', false),
                -- Staff B1 (role=7, user=9)
                (14, 'nv_b1_report.docx', 55000, 'seed_014', 'uploads/seed_014.docx', '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    10, 9, 7, 'organization', 'type_organization/role_2/role_3/role_5/role_7/user_9/folder_10', false,
                    NOW() - interval '2 days', NOW(), true, 2, 'B1 report', 'B1 summary', false),
                -- Staff B2 (role=7, user=10) — b1 NOT see
                (15, 'nv_b2_analysis.xlsx', 78000, 'seed_015', 'uploads/seed_015.xlsx', '.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    NULL, 10, 7, 'organization', 'type_organization/role_2/role_3/role_5/role_7/user_10', false,
                    NOW() - interval '1 day', NOW(), true, 4, 'B2 analysis', 'B2 analysis', false),
                -- Private
                (16, 'private_a1.txt', 4096, 'seed_016', 'uploads/seed_016.txt', '.txt', 'text/plain',
                    12, 6, NULL, 'private', 'type_private/folder_12', false,
                    NOW() - interval '3 days', NOW(), true, 1, 'A1 private', 'Private', false),
                (17, 'private_a2.txt', 3000, 'seed_017', 'uploads/seed_017.txt', '.txt', 'text/plain',
                    13, 7, NULL, 'private', 'type_private/folder_13', false,
                    NOW() - interval '2 days', NOW(), true, 1, 'A2 private', 'Private', false),
                -- General
                (18, 'mau_don_nghi_phep.docx', 64000, 'seed_018', 'uploads/seed_018.docx', '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    15, 1, NULL, 'general', 'type_general/folder_14/folder_15', false,
                    NOW() - interval '30 days', NOW(), true, 3, 'Leave form', 'Leave form', false),
                (19, 'noi_quy.pdf', 120000, 'seed_019', 'uploads/seed_019.pdf', '.pdf', 'application/pdf',
                    14, 1, NULL, 'general', 'type_general/folder_14', false,
                    NOW() - interval '60 days', NOW(), true, 5, 'Rules', 'Rules', true),
                -- Edge case: orphan private
                (20, 'orphan.txt', 1000, 'seed_020', 'uploads/seed_020.txt', '.txt', 'text/plain',
                    NULL, 1, NULL, 'private', 'type_private', false,
                    NOW() - interval '1 day', NOW(), false, 0, 'Orphan', 'Orphan', false)
            """))
            await db.execute(text("SELECT setval('files_id_seq', (SELECT MAX(id) FROM files))"))

            await db.commit()
            print("")
            print("=" * 60)
            print("  Seed data inserted successfully!")
            print("=" * 60)
            print("")
            print("  Roles:   7  (Admin + 6 org roles)")
            print("  Users:   11")
            print("  Folders: 15")
            print("  Files:   20")
            print("")
            print("  Login: password = 123456")
            print("")
            print("  Test accounts:")
            print("    admin     (role=1, ADMIN)    → sees everything, separate from org")
            print("    director  (role=2, Cuc truong) → org root, sees all org")
            print("    deputy1   (role=3)            → sees own + subtree, NOT deputy2")
            print("    deputy2   (role=3)            → sees own + subtree, NOT deputy1")
            print("    head_a    (role=4)            → sees own + all NV Phong A")
            print("    head_b    (role=5)            → sees own + all NV Phong B")
            print("    staff_a1  (role=6)            → own only (not a2/a3)")
            print("    staff_a2  (role=6)            → own only (not a1/a3)")
            print("    staff_a3  (role=6)            → own only (not a1/a2)")
            print("    staff_b1  (role=7)            → own only (not b2)")
            print("    staff_b2  (role=7)            → own only (not b1)")

        except Exception as e:
            await db.rollback()
            print(f"Error seeding data: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(seed())
