"""Stop de ingebedde PostgreSQL in de opgegeven datamap.
Gebruik: python scripts/stop_db.py <datamap>   (dezelfde map als bij start_db.py)"""
import sys

import pgserver

pgserver.get_server(sys.argv[1], cleanup_mode="stop").cleanup()
print("gestopt")
