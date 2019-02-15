from contextlib import contextmanager

import psycopg2


@contextmanager
def connect(connstring):
    conn = psycopg2.connect(connstring)
    try:
        yield conn
    finally:
        conn.close()
