from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dedupe import get_discovered_sources, init_db, upsert_discovered_source


class DedupeDiscoverySourceTests(unittest.TestCase):
    def test_upsert_discovered_source_distinguishes_ats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "jobs.sqlite"
            conn = init_db(str(db_path))

            try:
                inserted_greenhouse = upsert_discovered_source(conn, "notion", "", "", ats="greenhouse")
                inserted_lever = upsert_discovered_source(conn, "notion", "", "", ats="lever")
                rows = get_discovered_sources(conn)
            finally:
                conn.close()

        self.assertTrue(inserted_greenhouse)
        self.assertTrue(inserted_lever)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["ats"] for row in rows}, {"greenhouse", "lever"})


if __name__ == "__main__":
    unittest.main()