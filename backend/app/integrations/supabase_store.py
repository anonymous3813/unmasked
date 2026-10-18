"""Registry logs and purchases stored in the Supabase Postgres database."""

import hashlib
import json
import os
from datetime import datetime
from urllib.parse import quote, unquote, urlparse

from backend.app.integrations.gemini_client import _load_local_env

_failed = False
_connection = None


def _dsn() -> str:
    _load_local_env()
    raw = os.environ.get("SUPABASE_URL", "").strip()
    if not raw.startswith("postgres"):
        return ""
    marker = "@db."
    if marker not in raw:
        dsn = raw
    else:
        scheme, rest = raw.split("://", 1)
        creds, host = rest.rsplit(marker, 1)
        user, _, password = creds.partition(":")
        dsn = f"{scheme}://{quote(user, safe='')}:{quote(password, safe='')}@db.{host}"
    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return dsn


def _open(psycopg):
    """Open the direct database, then the IPv4 pooler when this network has no IPv6 route."""
    dsn = _dsn()
    try:
        return psycopg.connect(dsn, connect_timeout=8, autocommit=True)
    except Exception:
        parsed = urlparse(dsn)
    host = parsed.hostname or ""
    if not (host.startswith("db.") and host.endswith(".supabase.co")):
        raise RuntimeError("Supabase is not reachable")
    project_ref = host.split(".")[1]
    user = f"{parsed.username}.{project_ref}"
    password = unquote(parsed.password or "")
    last_error = None
    for region in ("us-east-1", "us-west-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1"):
        try:
            return psycopg.connect(
                host=f"aws-0-{region}.pooler.supabase.com",
                port=5432,
                user=user,
                password=password,
                dbname=(parsed.path or "/postgres").lstrip("/"),
                sslmode="require",
                connect_timeout=5,
                autocommit=True,
            )
        except Exception as exc:
            last_error = exc
    raise RuntimeError("Supabase pooler is not reachable") from last_error


def _conn():
    """Open the database once. Tests and a missing driver leave the shop in memory."""
    global _connection, _failed
    if os.environ.get("PYTEST_CURRENT_TEST") or _failed:
        return None
    if _connection is not None:
        return _connection
    if not _dsn():
        return None
    try:
        import psycopg
    except ImportError:
        _failed = True
        return None
    try:
        _connection = _open(psycopg)
        _connection.execute(
            """
            create table if not exists unmasked_registry (
                id text primary key,
                kind text not null,
                title text not null,
                detail text not null default '',
                url text not null default '',
                at timestamptz not null
            )
            """
        )
        _connection.execute(
            """
            create table if not exists unmasked_orders (
                order_id text primary key,
                product_name text not null,
                product_url text not null,
                store text not null default '',
                price text not null default '',
                environment_score integer,
                materials text not null default '',
                delivery_status text not null default 'Placed',
                notified_status text not null default '',
                ordered_at timestamptz not null
            )
            """
        )
        _connection.execute(
            """
            create table if not exists unmasked_receipts (
                id text primary key,
                filename text not null,
                body text not null default '',
                items text not null default '[]',
                saved_at timestamptz not null
            )
            """
        )
        _connection.execute(
            """
            create table if not exists unmasked_users (
                id text primary key,
                email text not null unique,
                name text not null default '',
                password text not null,
                created_at timestamptz not null
            )
            """
        )
        _connection.execute(
            """
            create table if not exists unmasked_sessions (
                digest text primary key,
                user_id text not null,
                created_at timestamptz not null
            )
            """
        )
        _connection.execute("alter table unmasked_users add column if not exists phone text not null default ''")
        _connection.execute("alter table unmasked_orders add column if not exists user_id text not null default ''")
        _connection.execute("alter table unmasked_receipts add column if not exists user_id text not null default ''")
        _connection.execute(
            """
            create table if not exists unmasked_wishlist (
                url text primary key,
                name text not null,
                store text not null default '',
                price text not null default '',
                image_url text not null default '',
                environment_score integer,
                saved_at timestamptz not null
            )
            """
        )
        _connection.execute(
            """
            create table if not exists unmasked_saved (
                user_id text not null,
                url text not null,
                name text not null,
                store text not null default '',
                price text not null default '',
                image_url text not null default '',
                environment_score integer,
                saved_at timestamptz not null,
                primary key (user_id, url)
            )
            """
        )
        return _connection
    except Exception:
        _failed = True
        _connection = None
        return None


def save_entry(entry: dict) -> None:
    connection = _conn()
    if connection is None:
        return
    try:
        connection.execute(
            """
            insert into unmasked_registry (id, kind, title, detail, url, at)
            values (%s, %s, %s, %s, %s, %s)
            on conflict (id) do nothing
            """,
            (entry["id"], entry["kind"], entry["title"], entry.get("detail") or "", entry.get("url") or "", entry["at"]),
        )
    except Exception:
        return


def load_entries() -> list[dict] | None:
    connection = _conn()
    if connection is None:
        return None
    try:
        rows = connection.execute(
            "select id, kind, title, detail, url, at from unmasked_registry order by at desc limit 200"
        ).fetchall()
    except Exception:
        return None
    loaded = []
    for row in rows:
        stamp = row[5]
        loaded.append(
            {
                "id": row[0],
                "kind": row[1],
                "title": row[2],
                "detail": row[3],
                "url": row[4],
                "at": stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp),
            }
        )
    return loaded


def save_order(order, user_id: str = "") -> None:
    connection = _conn()
    if connection is None:
        return
    try:
        connection.execute(
            """
            insert into unmasked_orders (
                order_id, product_name, product_url, store, price,
                environment_score, materials, delivery_status, notified_status, ordered_at, user_id
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (order_id) do update set
                delivery_status = excluded.delivery_status,
                notified_status = excluded.notified_status,
                environment_score = excluded.environment_score,
                materials = excluded.materials,
                user_id = excluded.user_id
            """,
            (
                order.order_id,
                order.product_name,
                str(order.product_url),
                order.store,
                order.price,
                order.environment_score,
                order.materials,
                order.delivery_status,
                order.notified_status,
                order.ordered_at,
                user_id,
            ),
        )
    except Exception:
        return


def load_orders() -> list[dict]:
    connection = _conn()
    if connection is None:
        return []
    try:
        rows = connection.execute(
            """
            select order_id, product_name, product_url, store, price, environment_score,
                   materials, delivery_status, notified_status, ordered_at, user_id
            from unmasked_orders order by ordered_at
            """
        ).fetchall()
    except Exception:
        return []
    loaded = []
    for row in rows:
        loaded.append(
            {
                "order_id": row[0],
                "product_name": row[1],
                "product_url": row[2],
                "store": row[3],
                "price": row[4],
                "environment_score": row[5],
                "materials": row[6],
                "delivery_status": row[7] or "Placed",
                "notified_status": row[8] or "",
                "ordered_at": row[9],
                "user_id": row[10] if len(row) > 10 else "",
            }
        )
    return loaded


def save_wishlist(item: dict, user_id: str = "shopper") -> None:
    connection = _conn()
    if connection is None:
        return
    try:
        connection.execute(
            """
            insert into unmasked_saved (user_id, url, name, store, price, image_url, environment_score, saved_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (user_id, url) do update set
                name = excluded.name,
                store = excluded.store,
                price = excluded.price,
                image_url = excluded.image_url,
                environment_score = excluded.environment_score,
                saved_at = excluded.saved_at
            """,
            (
                user_id,
                item["url"],
                item["name"],
                item.get("store") or "",
                item.get("price") or "",
                item.get("imageUrl") or "",
                item.get("environmentScore"),
                item["savedAt"],
            ),
        )
    except Exception:
        return


def load_wishlist(user_id: str = "shopper") -> list[dict] | None:
    connection = _conn()
    if connection is None:
        return None
    try:
        rows = connection.execute(
            """
            select url, name, store, price, image_url, environment_score, saved_at
            from unmasked_saved where user_id = %s order by saved_at desc
            """,
            (user_id,),
        ).fetchall()
    except Exception:
        return None
    loaded = []
    for row in rows:
        stamp = row[6]
        loaded.append(
            {
                "url": row[0],
                "name": row[1],
                "store": row[2],
                "price": row[3],
                "imageUrl": row[4],
                "environmentScore": row[5],
                "savedAt": stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp),
            }
        )
    return loaded


def save_receipt(record: dict) -> None:
    """Keep an uploaded bill so similar products still use it after a restart."""
    connection = _conn()
    if connection is None:
        return
    body = str(record.get("text") or "")
    filename = str(record.get("filename") or "Receipt")
    user_id = str(record.get("userId") or "shopper")
    receipt_id = hashlib.sha256(f"{user_id}|{filename}|{body}".encode()).hexdigest()[:16]
    try:
        connection.execute(
            """
            insert into unmasked_receipts (id, filename, body, items, saved_at, user_id)
            values (%s, %s, %s, %s, %s, %s)
            on conflict (id) do nothing
            """,
            (receipt_id, filename, body, json.dumps(record.get("items") or []), datetime.now(), user_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()


def load_receipts() -> list[dict]:
    """Return bills saved for this shopper."""
    connection = _conn()
    if connection is None:
        return []
    try:
        rows = connection.execute(
            "select filename, body, items, user_id from unmasked_receipts order by saved_at desc limit 40"
        ).fetchall()
    except Exception:
        connection.rollback()
        return []
    records = []
    for filename, body, items, user_id in rows:
        try:
            parsed = json.loads(items or "[]")
        except json.JSONDecodeError:
            parsed = []
        records.append(
            {
                "filename": filename,
                "text": body,
                "items": parsed if isinstance(parsed, list) else [],
                "userId": user_id or "shopper",
            }
        )
    return records


def save_user(user: dict) -> None:
    connection = _conn()
    if connection is None:
        return
    try:
        connection.execute(
            """
            insert into unmasked_users (id, email, name, password, created_at, phone)
            values (%s, %s, %s, %s, %s, %s)
            on conflict (id) do update set phone = excluded.phone
            """,
            (user["id"], user["email"], user["name"], user["password"], user["createdAt"], user.get("phone") or ""),
        )
        connection.commit()
    except Exception:
        connection.rollback()


def save_session(digest: str, user_id: str) -> None:
    connection = _conn()
    if connection is None:
        return
    try:
        connection.execute(
            """
            insert into unmasked_sessions (digest, user_id, created_at)
            values (%s, %s, %s)
            on conflict (digest) do nothing
            """,
            (digest, user_id, datetime.now()),
        )
        connection.commit()
    except Exception:
        connection.rollback()


def delete_session(digest: str) -> None:
    connection = _conn()
    if connection is None:
        return
    try:
        connection.execute("delete from unmasked_sessions where digest = %s", (digest,))
        connection.commit()
    except Exception:
        connection.rollback()


def load_accounts() -> tuple[list[dict], list[dict]]:
    connection = _conn()
    if connection is None:
        return [], []
    try:
        users = connection.execute("select id, email, name, password, created_at, phone from unmasked_users").fetchall()
        sessions = connection.execute("select digest, user_id from unmasked_sessions").fetchall()
    except Exception:
        connection.rollback()
        return [], []
    return (
        [
            {
                "id": row[0],
                "email": row[1],
                "name": row[2],
                "password": row[3],
                "createdAt": row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4]),
                "phone": row[5] if len(row) > 5 else "",
            }
            for row in users
        ],
        [{"digest": row[0], "user_id": row[1]} for row in sessions],
    )


def hydrate() -> None:
    """Load saved purchases into the assistant profile when the API starts."""
    from backend.app.models.agent import FinePrintOrderContext, PastOrder
    from backend.app.services.shop.accounts import remember_users
    from backend.app.services.shop.cart import SHOPPER_ID, contact
    from backend.app.services.shop.receipts import remember_receipts

    remember_users(*load_accounts())
    remember_receipts(load_receipts())
    rows = load_orders()
    if not rows:
        return
    shopper = contact()
    seen: set[tuple[str, str]] = set()
    for row in rows:
        user_id = row.get("user_id") or SHOPPER_ID
        if (user_id, row["order_id"]) in seen:
            continue
        seen.add((user_id, row["order_id"]))
        try:
            if any(order.order_id == row["order_id"] for order in shopper.past_orders(user_id)):
                continue
        except KeyError:
            shopper.open_profile(user_id, "unknown")
        ordered_at = row["ordered_at"]
        if isinstance(ordered_at, str):
            ordered_at = datetime.fromisoformat(ordered_at)
        shopper.add_order(
            user_id,
            PastOrder(
                order_id=row["order_id"],
                product_name=row["product_name"],
                product_url=row["product_url"],
                ordered_at=ordered_at,
                store=row["store"] or "",
                price=row["price"] or "",
                environment_score=row["environment_score"],
                materials=row["materials"] or "",
                delivery_status=row["delivery_status"],
                notified_status=row["notified_status"],
                fine_print=FinePrintOrderContext(price=row["price"] or "", checked_at=ordered_at),
            ),
        )
