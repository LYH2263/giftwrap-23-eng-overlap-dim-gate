from app.db import connect

def list_boxes():
    c = connect()
    try:
        return [dict(r) for r in c.execute("SELECT * FROM boxes ORDER BY id").fetchall()]
    finally:
        c.close()

def get_box(bid):
    c = connect()
    try:
        r = c.execute("SELECT * FROM boxes WHERE id=?", (bid,)).fetchone()
        return dict(r) if r else None
    finally:
        c.close()

def update_dimensions(bid, length, width, height):
    c = connect()
    try:
        cur = c.execute(
            "UPDATE boxes SET length=?, width=?, height=? WHERE id=?",
            (float(length), float(width), float(height), bid),
        )
        c.commit()
        return cur.rowcount
    finally:
        c.close()
