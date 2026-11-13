"""Подключение к Oracle и запуск SQL-файлов."""
import os
import re
from pathlib import Path

import oracledb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _env():
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith("ORACLE_")})
    return env


def connect():
    e = _env()
    return oracledb.connect(user=e["ORACLE_USER"], password=e["ORACLE_PASSWORD"], dsn=e["ORACLE_DSN"])


def split_sql(text: str):
    """Делит SQL-файл на команды: PL/SQL-блоки заканчиваются строкой '/', остальные — ';'."""
    out = []
    for chunk in re.split(r"^\s*/\s*$", text, flags=re.M):
        chunk = chunk.strip()
        if not chunk:
            continue
        if re.match(r"^(--[^\n]*\n\s*)*(BEGIN|DECLARE)\b", chunk, flags=re.I):
            out.append(chunk)
        else:
            for stmt in chunk.split(";"):
                body = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--")).strip()
                if body:
                    out.append(body)
    return out


def run_file(conn, path: Path):
    with conn.cursor() as cur:
        for stmt in split_sql(path.read_text(encoding="utf-8")):
            cur.execute(stmt)
    conn.commit()


def named_queries(path: Path):
    """Возвращает {name: sql} для блоков, помеченных '-- name: ...'."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^--\s*name:\s*(\w+)\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1].strip().rstrip(";") for i in range(1, len(parts), 2)}


def query_df(conn, sql: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0].lower() for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)
