import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from phone_agent.config import get_settings


def db_path() -> Path:
    return get_settings().app_base_dir / "dashboard" / "dashboard.sqlite3"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        create table if not exists email_drafts (
            id integer primary key autoincrement,
            call_id text,
            recipient text,
            subject text not null,
            body text not null,
            internal_note text not null,
            status text not null default 'draft',
            error text not null default '',
            sent_at text not null default '',
            audience text not null default 'external',
            created_at text not null
        )
        """
    )
    _ensure_column(conn, "sent_at", "text not null default ''")
    _ensure_column(conn, "audience", "text not null default 'external'")
    return conn


def _ensure_column(conn: sqlite3.Connection, name: str, definition: str) -> None:
    columns = [row["name"] for row in conn.execute("pragma table_info(email_drafts)").fetchall()]
    if name not in columns:
        conn.execute(f"alter table email_drafts add column {name} {definition}")


def create_draft(
    call_id: str,
    recipient: str,
    subject: str,
    body: str,
    internal_note: str,
    audience: str = "external",
    status: str = "draft",
) -> int:
    with connect() as conn:
        existing = conn.execute(
            "select id from email_drafts where call_id = ? and audience = ?",
            (call_id, audience),
        ).fetchone()
        if existing:
            return int(existing["id"])
        cur = conn.execute(
            """
            insert into email_drafts (call_id, recipient, subject, body, internal_note, status, audience, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (call_id, recipient, subject, body, internal_note, status, audience, datetime.utcnow().isoformat()),
        )
        return int(cur.lastrowid)


def list_drafts(status: str | None = None) -> list[dict[str, Any]]:
    with connect() as conn:
        if status:
            rows = conn.execute("select * from email_drafts where status = ? order by created_at desc", (status,)).fetchall()
        else:
            rows = conn.execute("select * from email_drafts order by created_at desc").fetchall()
        return [dict(row) for row in rows]


def get_draft(draft_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("select * from email_drafts where id = ?", (draft_id,)).fetchone()
        return dict(row) if row else None


def update_draft(draft_id: int, recipient: str, subject: str, body: str, internal_note: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            update email_drafts
            set recipient = ?, subject = ?, body = ?, internal_note = ?, status = 'draft', error = ''
            where id = ? and status in ('draft', 'failed', 'queued')
            """,
            (recipient, subject, body, internal_note, draft_id),
        )


def delete_draft(draft_id: int) -> None:
    with connect() as conn:
        conn.execute("delete from email_drafts where id = ? and status != 'sent'", (draft_id,))


def mark_sent(draft_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "update email_drafts set status = 'sent', error = '', sent_at = ? where id = ?",
            (datetime.utcnow().isoformat(), draft_id),
        )


def mark_error(draft_id: int, error: str) -> None:
    with connect() as conn:
        conn.execute(
            "update email_drafts set status = 'failed', error = ? where id = ?",
            (error[:500], draft_id),
        )
