import os
import time

import psycopg2

from rules import weigh


def connect():
    last = None
    for _ in range(30):
        try:
            return psycopg2.connect(os.environ["DATABASE_URL"])
        except psycopg2.OperationalError as exc:
            last = exc
            time.sleep(1)
    raise last


def main():
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS cuppings (
            id serial PRIMARY KEY,
            lot text NOT NULL,
            aroma double precision NOT NULL,
            taste double precision NOT NULL,
            liquor double precision NOT NULL,
            score double precision NOT NULL,
            verdict text NOT NULL,
            note text NOT NULL,
            created_by text NOT NULL
        )"""
    )
    # 母叶比例尺：一批一条，生效后该批才可交审评
    cur.execute(
        """CREATE TABLE IF NOT EXISTS blend_scales (
            id serial PRIMARY KEY,
            lot text NOT NULL UNIQUE,
            created_by text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS blend_leaves (
            id serial PRIMARY KEY,
            scale_id integer NOT NULL REFERENCES blend_scales(id) ON DELETE CASCADE,
            leaf text NOT NULL,
            percent numeric(5,2) NOT NULL CHECK (percent > 0 AND percent <= 100),
            UNIQUE (scale_id, leaf)
        )"""
    )
    cur.execute("SELECT COUNT(*) FROM cuppings")
    if cur.fetchone()[0] == 0:
        for lot, aroma, taste, liquor in (("春茶-A", 8, 8, 7), ("夏茶-C", 5, 4, 6)):
            verdict, note, score = weigh(aroma, taste, liquor)
            cur.execute(
                """INSERT INTO cuppings (lot, aroma, taste, liquor, score, verdict, note, created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (lot, aroma, taste, liquor, score, verdict, note, "taster"),
            )
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
