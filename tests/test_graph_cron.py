"""Test the graph extraction cron job: insert mock data, run one cycle, verify results."""

import asyncio
import hashlib
import sys
import os

# Override config to point at local postgres container (port 5432, password=postgres)
os.environ.setdefault("DATABASE_URI", "postgresql+asyncpg://postgres:postgres@localhost:5432/tms")
os.environ.setdefault("OPENAI_API_KEY", "") # Set to empty string to prevent accidental API calls during testing  
os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from sqlalchemy import text
from app.core.database import get_db_session
from app.crons.graph_extraction_job import graph_extraction_job


MOCK_DOCUMENTS = [
    {
        "name": "nato_exercise_report.pdf",
        "type": "pdf",
        "extension": "pdf",
        "content": """
NATO Exercise Steadfast Defender 2024

General Christopher Cavoli, Supreme Allied Commander Europe (SACEUR), commanded the largest
NATO exercise since the Cold War. The exercise involved over 90,000 troops from all 31 NATO
member states across multiple European locations.

The U.S. Army's 101st Airborne Division deployed from Fort Campbell, Kentucky to Romania and
was stationed at Mihail Kogălniceanu Air Base near Constanța. The division operated UH-60 Black
Hawk helicopters and was equipped with Javelin anti-tank missile systems.

The British Army's 3rd Division participated in the exercise alongside the German Bundeswehr's
10th Armoured Division. Both divisions conducted joint maneuvers in Poland, specifically in the
Drawsko Pomorskie Training Area.

The French Navy deployed the aircraft carrier Charles de Gaulle to the Mediterranean Sea, carrying
Rafale M fighter jets. The carrier strike group included the frigate FREMM Aquitaine equipped with
Aster 15 surface-to-air missiles.

Poland's 18th Mechanized Division was subordinate to NATO's Multinational Corps Northeast
headquartered in Szczecin. The corps coordinated operations across the Baltic states, with Estonian
and Latvian units participating in the defense scenario.

The exercise simulated a response to aggression from a hypothetical adversary near NATO's eastern
flank, with cyber warfare elements coordinated by NATO's Cooperative Cyber Defence Centre of
Excellence (CCDCOE) based in Tallinn, Estonia.
""",
    },
    {
        "name": "indo_pacific_brief.pdf",
        "type": "pdf",
        "extension": "pdf",
        "content": """
INTELLIGENCE ASSESSMENT: Indo-Pacific Military Developments — Q3 2024

The People's Liberation Army Navy (PLAN) has increased patrols in the South China Sea,
deploying the Type 055 destroyer Nanchang and the Type 075 amphibious assault ship Hainan
near the Spratly Islands. The PLAN's Southern Theater Command oversees operations in this region.

Admiral John Aquilino, Commander of U.S. Indo-Pacific Command (INDOPACOM), reported that
Chinese military activity around Taiwan has intensified. The U.S. Navy's 7th Fleet, homeported
at Yokosuka Naval Base in Japan, conducted freedom of navigation operations in the Taiwan Strait
with the Arleigh Burke-class destroyer USS Rafael Peralta.

Japan's Maritime Self-Defense Force (JMSDF) deployed the helicopter carrier JS Izumo to the
Philippine Sea. The Izumo is being retrofitted to operate F-35B Lightning II stealth fighters,
manufactured by Lockheed Martin.

Australia's Defence Force signed the AUKUS treaty with the United Kingdom and the United States,
which includes the transfer of nuclear-powered submarine technology. Australia will acquire
Virginia-class submarines produced by General Dynamics Electric Boat.

North Korea, identified as a persistent threat actor, conducted multiple ballistic missile tests
including the Hwasong-18 ICBM. The Korean People's Army Strategic Force is responsible for
North Korea's missile program.
""",
    },
]


async def insert_mock_data():
    """Insert mock documents into the files table."""
    async with get_db_session() as session:
        for doc in MOCK_DOCUMENTS:
            content_hash = hashlib.sha256(doc["content"].encode()).hexdigest()
            await session.execute(
                text("""
                    INSERT INTO files (name, size, hash, path, extension, type, content, is_processed, is_graph_extracted, is_deleted)
                    VALUES (:name, :size, :hash, :path, :extension, :type, :content, true, false, false)
                    ON CONFLICT (hash) DO UPDATE SET
                        content = EXCLUDED.content,
                        is_graph_extracted = false
                """),
                {
                    "name": doc["name"],
                    "size": len(doc["content"]),
                    "hash": content_hash,
                    "path": f"/mock/{doc['name']}",
                    "extension": doc.get("extension"),
                    "type": doc["type"],
                    "content": doc["content"],
                },
            )
        await session.commit()
        print("✓ Inserted mock documents into files table")


async def verify_results():
    """Check the database for extraction results."""
    async with get_db_session() as session:
        # Files status
        result = await session.execute(
            text("SELECT id, name, is_graph_extracted FROM files WHERE is_deleted = false ORDER BY id")
        )
        rows = result.fetchall()
        print(f"\n── Files ({len(rows)} rows) ──")
        for row in rows:
            print(f"  id={row[0]}  name={row[1]}  is_graph_extracted={row[2]}")

        # Nodes
        result = await session.execute(text("SELECT count(*) FROM nodes"))
        node_count = result.scalar()
        print(f"\n── Total Nodes: {node_count} ──")

        result = await session.execute(
            text("SELECT name, entity_type, file_id FROM nodes ORDER BY entity_type, name LIMIT 40")
        )
        for row in result.fetchall():
            print(f"  [{row[1]}] {row[0]}  (file_id={row[2]})")

        # Edges
        result = await session.execute(text("SELECT count(*) FROM edges"))
        edge_count = result.scalar()
        print(f"\n── Total Edges: {edge_count} ──")

        result = await session.execute(
            text("""
                SELECT n1.name, e.edge_type, n2.name, e.file_id
                FROM edges e
                JOIN nodes n1 ON n1.id = e.source_node_id
                JOIN nodes n2 ON n2.id = e.target_node_id
                ORDER BY e.edge_type, n1.name
                LIMIT 40
            """)
        )
        for row in result.fetchall():
            print(f"  {row[0]} --[{row[1]}]--> {row[2]}  (file_id={row[3]})")


async def main():
    print("=" * 60)
    print("Step 1: Insert mock data")
    print("=" * 60)
    await insert_mock_data()

    print("\n" + "=" * 60)
    print("Step 2: Run extraction cycle")
    print("=" * 60)
    await graph_extraction_job()

    print("\n" + "=" * 60)
    print("Step 3: Verify results")
    print("=" * 60)
    await verify_results()


if __name__ == "__main__":
    asyncio.run(main())
