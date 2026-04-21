from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .db import get_connection, init_db
from .importer import import_archive, upsert_label

settings = get_settings()
app = FastAPI(title="Calligraphy Gallery")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@app.on_event("startup")
def startup() -> None:
    init_db(settings.db_path)
    if settings.archive_dir.exists():
        with get_connection(settings.db_path) as conn:
            existing = conn.execute("SELECT COUNT(*) AS count FROM items").fetchone()["count"]
        if existing == 0:
            import_archive(settings.archive_dir, settings.db_path, settings.metadata_json_path)


def fetch_item_list(
    conn: sqlite3.Connection,
    q: str | None = None,
    person: str | None = None,
    script: str | None = None,
    period: str | None = None,
    theme: str | None = None,
    sort: str = "title",
    include_deleted: bool = False,
    limit: int = 24,
) -> list[sqlite3.Row]:
    clauses = ["1 = 1"]
    params: list[object] = []
    joins = []
    if not include_deleted:
        clauses.append("items.is_deleted = 0")
    if q:
        clauses.append(
            "(items.raw_title LIKE ? OR items.display_title LIKE ? OR items.canonical_title LIKE ? OR persons.display_name LIKE ?)"
        )
        like = f"%{q}%"
        params.extend([like, like, like, like])
        joins.append("LEFT JOIN persons ON persons.id = items.primary_person_id")
    else:
        joins.append("LEFT JOIN persons ON persons.id = items.primary_person_id")
    if person:
        joins.append("LEFT JOIN item_persons ip ON ip.item_id = items.id")
        joins.append("LEFT JOIN persons fp ON fp.id = ip.person_id")
        clauses.append("(fp.id = ? OR fp.display_name = ?)")
        params.extend([person, person])
    if script:
        joins.append("LEFT JOIN item_scripts its ON its.item_id = items.id")
        joins.append("LEFT JOIN scripts s ON s.id = its.script_id")
        clauses.append("(s.id = ? OR s.label = ?)")
        params.extend([script, script])
    if period:
        joins.append("LEFT JOIN item_periods itp ON itp.item_id = items.id")
        joins.append("LEFT JOIN periods p ON p.id = itp.period_id")
        clauses.append("(p.id = ? OR p.label = ?)")
        params.extend([period, period])
    if theme:
        joins.append("LEFT JOIN item_themes itt ON itt.item_id = items.id")
        joins.append("LEFT JOIN themes t ON t.id = itt.theme_id")
        clauses.append("(t.id = ? OR t.label = ?)")
        params.extend([theme, theme])

    order_by = "items.display_title COLLATE NOCASE ASC"
    if sort == "recent":
        order_by = "items.last_viewed_at DESC, items.display_title COLLATE NOCASE ASC"
    elif sort == "popular":
        order_by = "items.view_count DESC, items.last_viewed_at DESC, items.display_title COLLATE NOCASE ASC"
    elif sort == "updated":
        order_by = "items.updated_at DESC"
    elif q:
        order_by = "items.view_count DESC, items.display_title COLLATE NOCASE ASC"

    sql = f"""
        SELECT DISTINCT
          items.*,
          persons.display_name AS primary_person_name,
          (
            SELECT images.id FROM images
            WHERE images.item_id = items.id
            ORDER BY images.page_index ASC
            LIMIT 1
          ) AS cover_image_id
        FROM items
        {' '.join(dict.fromkeys(joins))}
        WHERE {' AND '.join(clauses)}
        ORDER BY {order_by}
        LIMIT ?
    """
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def fetch_options(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    if table == "persons":
        return conn.execute("SELECT id, display_name AS label FROM persons ORDER BY display_name COLLATE NOCASE ASC").fetchall()
    return conn.execute(f"SELECT id, label FROM {table} ORDER BY label COLLATE NOCASE ASC").fetchall()


def fetch_relations(conn: sqlite3.Connection, item_id: str) -> dict[str, list[sqlite3.Row] | sqlite3.Row | None]:
    return {
        "persons": conn.execute(
            "SELECT p.id, p.display_name AS label FROM persons p JOIN item_persons ip ON ip.person_id = p.id WHERE ip.item_id = ? ORDER BY p.display_name",
            (item_id,),
        ).fetchall(),
        "scripts": conn.execute(
            "SELECT s.id, s.label FROM scripts s JOIN item_scripts it ON it.script_id = s.id WHERE it.item_id = ? ORDER BY s.label",
            (item_id,),
        ).fetchall(),
        "periods": conn.execute(
            "SELECT p.id, p.label FROM periods p JOIN item_periods it ON it.period_id = p.id WHERE it.item_id = ? ORDER BY p.label",
            (item_id,),
        ).fetchall(),
        "themes": conn.execute(
            "SELECT t.id, t.label FROM themes t JOIN item_themes it ON it.theme_id = t.id WHERE it.item_id = ? ORDER BY t.label",
            (item_id,),
        ).fetchall(),
        "institutions": conn.execute(
            "SELECT i.id, i.label FROM institutions i JOIN item_institutions it ON it.institution_id = i.id WHERE it.item_id = ? ORDER BY i.label",
            (item_id,),
        ).fetchall(),
        "work_forms": conn.execute(
            "SELECT w.id, w.label FROM work_forms w JOIN item_work_forms it ON it.work_form_id = w.id WHERE it.item_id = ? ORDER BY w.label",
            (item_id,),
        ).fetchall(),
        "series": conn.execute(
            "SELECT id, label FROM series WHERE id = (SELECT series_id FROM items WHERE id = ?)",
            (item_id,),
        ).fetchone(),
    }


def row_to_item_summary(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "display_title": row["display_title"],
        "canonical_title": row["canonical_title"],
        "primary_person_name": row["primary_person_name"],
        "image_count": row["image_count"],
        "view_count": row["view_count"],
        "last_viewed_at": row["last_viewed_at"],
        "cover_image_id": row["cover_image_id"],
    }


def record_view(conn: sqlite3.Connection, item_id: str) -> None:
    item = conn.execute("SELECT last_viewed_at FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        return
    if item["last_viewed_at"]:
        last_viewed = datetime.fromisoformat(item["last_viewed_at"].replace("Z", "+00:00"))
        if datetime.now(UTC) - last_viewed < timedelta(minutes=10):
            return
    timestamp = now_iso()
    conn.execute("INSERT INTO item_views (item_id, viewed_at) VALUES (?, ?)", (item_id, timestamp))
    conn.execute(
        "UPDATE items SET view_count = view_count + 1, last_viewed_at = ?, updated_at = updated_at WHERE id = ?",
        (timestamp, item_id),
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with get_connection(settings.db_path) as conn:
        recent = conn.execute(
            """
            SELECT items.*, persons.display_name AS primary_person_name,
                   (SELECT images.id FROM images WHERE images.item_id = items.id ORDER BY images.page_index LIMIT 1) AS cover_image_id
            FROM items
            LEFT JOIN persons ON persons.id = items.primary_person_id
            WHERE items.is_deleted = 0 AND items.last_viewed_at IS NOT NULL
            ORDER BY items.last_viewed_at DESC
            LIMIT 12
            """
        ).fetchall()
        popular = conn.execute(
            """
            SELECT items.*, persons.display_name AS primary_person_name,
                   (SELECT images.id FROM images WHERE images.item_id = items.id ORDER BY images.page_index LIMIT 1) AS cover_image_id
            FROM items
            LEFT JOIN persons ON persons.id = items.primary_person_id
            WHERE items.is_deleted = 0
            ORDER BY items.view_count DESC, items.last_viewed_at DESC
            LIMIT 12
            """
        ).fetchall()
        counts = conn.execute("SELECT COUNT(*) AS count FROM items WHERE is_deleted = 0").fetchone()["count"]
    return templates.TemplateResponse(
        request,
        "home.html",
        {"request": request, "recent": recent, "popular": popular, "item_count": counts, "archive_dir": settings.archive_dir},
    )


@app.get("/browse", response_class=HTMLResponse)
def browse(
    request: Request,
    q: str | None = None,
    person: str | None = None,
    script: str | None = None,
    period: str | None = None,
    theme: str | None = None,
    sort: str = "title",
):
    with get_connection(settings.db_path) as conn:
        items = fetch_item_list(conn, q=q, person=person, script=script, period=period, theme=theme, sort=sort, limit=100)
        context = {
            "request": request,
            "items": items,
            "filters": {"q": q or "", "person": person or "", "script": script or "", "period": period or "", "theme": theme or "", "sort": sort},
            "persons": fetch_options(conn, "persons"),
            "scripts": fetch_options(conn, "scripts"),
            "periods": fetch_options(conn, "periods"),
            "themes": fetch_options(conn, "themes"),
        }
    return templates.TemplateResponse(request, "browse.html", context)


@app.get("/items/{item_id}", response_class=HTMLResponse)
def item_detail(request: Request, item_id: str):
    with get_connection(settings.db_path) as conn:
        item = conn.execute(
            "SELECT items.*, persons.display_name AS primary_person_name FROM items LEFT JOIN persons ON persons.id = items.primary_person_id WHERE items.id = ?",
            (item_id,),
        ).fetchone()
        if not item or item["is_deleted"]:
            raise HTTPException(status_code=404, detail="Item not found")
        record_view(conn, item_id)
        images = conn.execute("SELECT * FROM images WHERE item_id = ? ORDER BY page_index ASC", (item_id,)).fetchall()
        relations = fetch_relations(conn, item_id)
    return templates.TemplateResponse(
        request,
        "item.html",
        {"request": request, "item": item, "images": images, "relations": relations, "source_labels": json.loads(item["source_labels_json"])},
    )


@app.get("/items/{item_id}/images/{image_id}", response_class=HTMLResponse)
def image_viewer(request: Request, item_id: str, image_id: str):
    with get_connection(settings.db_path) as conn:
        item = conn.execute(
            "SELECT items.*, persons.display_name AS primary_person_name FROM items LEFT JOIN persons ON persons.id = items.primary_person_id WHERE items.id = ?",
            (item_id,),
        ).fetchone()
        if not item or item["is_deleted"]:
            raise HTTPException(status_code=404, detail="Item not found")
        images = conn.execute("SELECT * FROM images WHERE item_id = ? ORDER BY page_index ASC", (item_id,)).fetchall()
        if not images:
            raise HTTPException(status_code=404, detail="No images found")
        current_index = next((index for index, image in enumerate(images) if image["id"] == image_id), None)
        if current_index is None:
            raise HTTPException(status_code=404, detail="Image not found")
        current_image = images[current_index]
        prev_image = images[current_index - 1] if current_index > 0 else None
        next_image = images[current_index + 1] if current_index < len(images) - 1 else None
    return templates.TemplateResponse(
        request,
        "image_viewer.html",
        {
            "request": request,
            "item": item,
            "image": current_image,
            "image_count": len(images),
            "prev_image": prev_image,
            "next_image": next_image,
        },
    )


@app.get("/media/images/{image_id}")
def media_image(image_id: str):
    with get_connection(settings.db_path) as conn:
        image = conn.execute("SELECT storage_uri, file_name FROM images WHERE id = ?", (image_id,)).fetchone()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    path = Path(image["storage_uri"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backing file not found")
    return FileResponse(path)


@app.get("/admin/items/{item_id}/edit", response_class=HTMLResponse)
def edit_item_page(request: Request, item_id: str):
    with get_connection(settings.db_path) as conn:
        item = conn.execute(
            """
            SELECT items.*, persons.display_name AS primary_person_name
            FROM items
            LEFT JOIN persons ON persons.id = items.primary_person_id
            WHERE items.id = ?
            """,
            (item_id,),
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        relations = fetch_relations(conn, item_id)
        options = {
            "scripts": fetch_options(conn, "scripts"),
            "periods": fetch_options(conn, "periods"),
            "themes": fetch_options(conn, "themes"),
            "institutions": fetch_options(conn, "institutions"),
            "work_forms": fetch_options(conn, "work_forms"),
        }
    return templates.TemplateResponse(
        request,
        "edit.html",
        {"request": request, "item": item, "relations": relations, "options": options},
    )


def replace_relations(conn: sqlite3.Connection, item_id: str, table: str, column: str, values: list[str]) -> None:
    conn.execute(f"DELETE FROM {table} WHERE item_id = ?", (item_id,))
    if values:
        conn.executemany(
            f"INSERT INTO {table} (item_id, {column}) VALUES (?, ?)",
            [(item_id, value) for value in values],
        )


@app.post("/admin/items/{item_id}/edit")
def edit_item_submit(
    item_id: str,
    display_title: str = Form(...),
    canonical_title: str = Form(...),
    primary_person_name: str = Form(""),
    script_ids: list[str] = Form(default=[]),
    period_ids: list[str] = Form(default=[]),
    theme_ids: list[str] = Form(default=[]),
    institution_ids: list[str] = Form(default=[]),
    work_form_ids: list[str] = Form(default=[]),
):
    with get_connection(settings.db_path) as conn:
        item = conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        primary_person_name = primary_person_name.strip()
        primary_person_id = None
        if primary_person_name:
            primary_person_id = upsert_label(conn, "persons", "person", primary_person_name)
        conn.execute(
            """
            UPDATE items
            SET display_title = ?, canonical_title = ?, primary_person_id = ?, review_status = 'edited', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (display_title.strip(), canonical_title.strip(), primary_person_id or None, item_id),
        )
        replace_relations(conn, item_id, "item_persons", "person_id", [primary_person_id] if primary_person_id else [])
        if primary_person_id:
            conn.execute("UPDATE item_persons SET role = 'primary' WHERE item_id = ? AND person_id = ?", (item_id, primary_person_id))
        replace_relations(conn, item_id, "item_scripts", "script_id", script_ids)
        replace_relations(conn, item_id, "item_periods", "period_id", period_ids)
        replace_relations(conn, item_id, "item_themes", "theme_id", theme_ids)
        replace_relations(conn, item_id, "item_institutions", "institution_id", institution_ids)
        replace_relations(conn, item_id, "item_work_forms", "work_form_id", work_form_ids)
        payload = json.dumps(
            {
                "display_title": display_title,
                "canonical_title": canonical_title,
                "primary_person_id": primary_person_id or None,
                "primary_person_name": primary_person_name or None,
                "script_ids": script_ids,
                "period_ids": period_ids,
                "theme_ids": theme_ids,
                "institution_ids": institution_ids,
                "work_form_ids": work_form_ids,
            },
            ensure_ascii=False,
        )
        conn.execute("INSERT INTO edit_log (item_id, action, payload_json) VALUES (?, 'edit', ?)", (item_id, payload))
    return RedirectResponse(url=f"/items/{item_id}", status_code=303)


@app.post("/admin/items/{item_id}/delete")
def delete_item(item_id: str):
    with get_connection(settings.db_path) as conn:
        conn.execute("UPDATE items SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (item_id,))
        conn.execute("INSERT INTO edit_log (item_id, action, payload_json) VALUES (?, 'delete', '{}')", (item_id,))
    return RedirectResponse(url="/browse", status_code=303)


@app.post("/admin/items/{item_id}/restore")
def restore_item(item_id: str):
    with get_connection(settings.db_path) as conn:
        conn.execute("UPDATE items SET is_deleted = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (item_id,))
        conn.execute("INSERT INTO edit_log (item_id, action, payload_json) VALUES (?, 'restore', '{}')", (item_id,))
    return RedirectResponse(url=f"/items/{item_id}", status_code=303)


@app.post("/admin/reindex")
def admin_reindex():
    if not settings.archive_dir.exists():
        raise HTTPException(status_code=400, detail="Archive directory does not exist")
    import_archive(settings.archive_dir, settings.db_path)
    return RedirectResponse(url="/browse", status_code=303)


@app.get("/api/history/recent")
def api_recent_history():
    with get_connection(settings.db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, display_title, canonical_title, view_count, last_viewed_at
            FROM items
            WHERE is_deleted = 0 AND last_viewed_at IS NOT NULL
            ORDER BY last_viewed_at DESC
            LIMIT 20
            """
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@app.get("/api/history/most-viewed")
def api_most_viewed():
    with get_connection(settings.db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, display_title, canonical_title, view_count, last_viewed_at
            FROM items
            WHERE is_deleted = 0
            ORDER BY view_count DESC, last_viewed_at DESC
            LIMIT 20
            """
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@app.get("/api/items")
def api_items(
    q: str | None = None,
    person: str | None = None,
    script: str | None = None,
    period: str | None = None,
    theme: str | None = None,
    sort: str = "title",
    limit: int = 50,
):
    with get_connection(settings.db_path) as conn:
        items = fetch_item_list(
            conn,
            q=q,
            person=person,
            script=script,
            period=period,
            theme=theme,
            sort=sort,
            limit=min(max(limit, 1), 200),
        )
        facets = {
            "persons": [dict(row) for row in fetch_options(conn, "persons")[:50]],
            "scripts": [dict(row) for row in fetch_options(conn, "scripts")],
            "periods": [dict(row) for row in fetch_options(conn, "periods")],
            "themes": [dict(row) for row in fetch_options(conn, "themes")],
        }
    return {"items": [row_to_item_summary(row) for row in items], "facets": facets}


@app.get("/api/items/{item_id}")
def api_item(item_id: str):
    with get_connection(settings.db_path) as conn:
        item = conn.execute(
            "SELECT items.*, persons.display_name AS primary_person_name FROM items LEFT JOIN persons ON persons.id = items.primary_person_id WHERE items.id = ?",
            (item_id,),
        ).fetchone()
        if not item or item["is_deleted"]:
            raise HTTPException(status_code=404, detail="Item not found")
        relations = fetch_relations(conn, item_id)
        images = conn.execute("SELECT * FROM images WHERE item_id = ? ORDER BY page_index ASC", (item_id,)).fetchall()
    return {
        "item": {
            "id": item["id"],
            "raw_title": item["raw_title"],
            "display_title": item["display_title"],
            "canonical_title": item["canonical_title"],
            "primary_person_name": item["primary_person_name"],
            "review_status": item["review_status"],
            "is_deleted": bool(item["is_deleted"]),
            "view_count": item["view_count"],
            "last_viewed_at": item["last_viewed_at"],
            "source_labels": json.loads(item["source_labels_json"]),
        },
        "relations": {
            key: ([dict(row) for row in value] if isinstance(value, list) else (dict(value) if value else None))
            for key, value in relations.items()
        },
        "images": [dict(row) for row in images],
    }


@app.get("/api/items/{item_id}/images")
def api_item_images(item_id: str):
    with get_connection(settings.db_path) as conn:
        item = conn.execute("SELECT id FROM items WHERE id = ? AND is_deleted = 0", (item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        images = conn.execute("SELECT * FROM images WHERE item_id = ? ORDER BY page_index ASC", (item_id,)).fetchall()
    return {"images": [dict(row) for row in images]}


@app.get("/api/facets")
def api_facets():
    with get_connection(settings.db_path) as conn:
        return {
            "persons": [dict(row) for row in fetch_options(conn, "persons")[:100]],
            "scripts": [dict(row) for row in fetch_options(conn, "scripts")],
            "periods": [dict(row) for row in fetch_options(conn, "periods")],
            "themes": [dict(row) for row in fetch_options(conn, "themes")],
            "work_forms": [dict(row) for row in fetch_options(conn, "work_forms")],
        }
