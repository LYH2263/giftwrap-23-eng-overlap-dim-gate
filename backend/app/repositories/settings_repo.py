from app.config import DEFAULT_OVERLAP
from app.db import connect

def get_all():
    c = connect()
    try:
        d = {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM settings").fetchall()}
        d.setdefault("overlap", str(DEFAULT_OVERLAP))
        return d
    finally:
        c.close()

def get_overlap():
    return float(get_all().get("overlap", DEFAULT_OVERLAP))


def set_overlap(value: float) -> float:
    value = float(value)
    if value <= 0:
        raise ValueError("overlap must be positive")
    c = connect()
    try:
        c.execute(
            "INSERT INTO settings(key,value) VALUES('overlap',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(value),),
        )
        c.commit()
    finally:
        c.close()
    return value
