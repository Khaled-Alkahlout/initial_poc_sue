"""Start (of hergebruik) een ingebedde PostgreSQL en print de verbindings-URI.
Gebruik: python scripts/start_db.py <datamap>   (de server blijft draaien na afloop; stop met scripts/stop_db.py)
De bovenliggende map wordt aangemaakt als die nog niet bestaat."""
import os
import sys

import pgserver

datadir = os.path.abspath(sys.argv[1])
os.makedirs(os.path.dirname(datadir), exist_ok=True)
srv = pgserver.get_server(datadir, cleanup_mode=None)
print(srv.get_uri())
