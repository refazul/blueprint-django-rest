# wait-for-db.py
import socket
import time
import os

host = os.environ.get('DB_HOST')
port = int(os.environ.get('DB_PORT'))

print(f"⏳ Waiting for PostgreSQL at {host}:{port}...")

while True:
    try:
        with socket.create_connection((host, port), timeout=2):
            print("✅ PostgreSQL is up!")
            break
    except OSError:
        time.sleep(0.5)
