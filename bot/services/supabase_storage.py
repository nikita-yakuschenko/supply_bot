import os
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


FORM_TYPES = {"delivery", "refund", "painting", "checkin"}

APP_FIELD_TO_COLUMN = {
    "contract": "contract_number",
    "text": "form_text",
    "date_checkin": "checkin_date",
    "brigadier_name": "brig_name",
    "brigadier_phone": "brig_phone",
    "carrying": "carring",
    "contract_number": "contract_number",
    "form_text": "form_text",
    "checkin_date": "checkin_date",
    "brig_name": "brig_name",
    "brig_phone": "brig_phone",
    "carring": "carring",
}


def resolve_database_url() -> str | None:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    supabase_host = os.getenv("SUPABASE_HOST")
    postgres_password = os.getenv("POSTGRES_PASSWORD")
    if supabase_host and postgres_password:
        db = os.getenv("POSTGRES_DB", "postgres")
        tenant = os.getenv("POOLER_TENANT_ID")
        base_user = os.getenv("POSTGRES_USER", "postgres")
        user = f"{base_user}.{tenant}" if tenant else base_user
        port = os.getenv("POOLER_PROXY_PORT_TRANSACTION", "6543")
        return f"postgresql://{user}:{postgres_password}@{supabase_host}:{port}/{db}"

    host = os.getenv("SUPABASE_DB_HOST")
    port = os.getenv("SUPABASE_DB_PORT", "5432")
    db = os.getenv("SUPABASE_DB_NAME", "postgres")
    user = os.getenv("SUPABASE_DB_USER", "postgres")
    password = os.getenv("SUPABASE_DB_PASSWORD")
    if host and password:
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    return None


def _connect():
    database_url = resolve_database_url()
    if not database_url:
        raise RuntimeError("Supabase/Postgres is not configured. Set DATABASE_URL or SUPABASE variables.")
    return psycopg.connect(database_url, prepare_threshold=None)


def _normalize_form_type(form_type: str | None) -> str:
    return (form_type or "").strip().lower()


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _to_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_payload_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _format_ts(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value or ""


def _row_to_user(row: dict) -> dict:
    payload = _to_payload_dict(row.get("payload"))
    return {
        "user_id": row["user_id"],
        "username": row.get("username") or payload.get("username") or "",
        "fullname": row.get("fullname") or payload.get("fullname") or "",
        "phone": row.get("phone") or payload.get("phone") or "",
        "position": row.get("position") or payload.get("position") or "",
        "department": row.get("department") or payload.get("department") or "",
        "approved": bool(row.get("approved", False)),
        "admin": bool(row.get("admin", False)),
    }


def _row_to_form_data(row: dict) -> dict:
    payload = _to_payload_dict(row.get("payload"))
    form_type = row["application_type"]
    base = {
        "user_id": row.get("user_id"),
        "type": form_type,
        "form_number": row.get("form_number"),
        "created_at": _format_ts(row.get("created_at")),
        "creator_fullname": row.get("creator_fullname") or payload.get("creator_fullname") or "",
    }
    if form_type == "checkin":
        base.update(
            {
                "num_contract": row.get("contract_number") or payload.get("num_contract") or payload.get("contract_number") or "",
                "date": row.get("checkin_date") or payload.get("date") or payload.get("checkin_date") or "",
                "name_brig": row.get("brig_name") or payload.get("name_brig") or payload.get("brigadier_name") or "",
                "phone_brig": row.get("brig_phone") or payload.get("phone_brig") or payload.get("brigadier_phone") or "",
                "carring": row.get("carring") or payload.get("carring") or payload.get("carrying") or "",
            }
        )
    else:
        base.update(
            {
                "contract_number": row.get("contract_number") or payload.get("contract_number") or payload.get("contract") or "",
                "form_text": row.get("form_text") or payload.get("form_text") or payload.get("text") or "",
            }
        )
    return base


def _row_to_application(row: dict) -> dict:
    payload = _to_payload_dict(row.get("payload"))
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "form_type": row.get("application_type"),
        "date": _format_ts(row.get("created_at")),
        "form_number": row.get("form_number"),
        "creator_fullname": row.get("creator_fullname") or payload.get("creator_fullname") or "",
        "contract": row.get("contract_number") or payload.get("contract") or payload.get("contract_number") or payload.get("num_contract") or "",
        "text": row.get("form_text") or payload.get("text") or payload.get("form_text") or "",
        "date_checkin": row.get("checkin_date") or payload.get("date_checkin") or payload.get("date") or "",
        "brigadier_name": row.get("brig_name") or payload.get("brigadier_name") or payload.get("name_brig") or "",
        "brigadier_phone": row.get("brig_phone") or payload.get("brigadier_phone") or payload.get("phone_brig") or "",
        "carrying": row.get("carring") or payload.get("carrying") or payload.get("carring") or "",
    }


def upsert_user(user_data: dict) -> bool:
    user_id = _to_int(user_data.get("user_id"))
    if user_id is None:
        return False

    payload = _to_payload_dict(user_data).copy()
    payload["user_id"] = user_id

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into bot.users (
                  user_id, username, fullname, phone, position, department,
                  approved, admin, payload, updated_at
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                on conflict (user_id) do update set
                  username = excluded.username,
                  fullname = excluded.fullname,
                  phone = excluded.phone,
                  position = excluded.position,
                  department = excluded.department,
                  approved = excluded.approved,
                  admin = excluded.admin,
                  payload = excluded.payload,
                  updated_at = now()
                """,
                (
                    user_id,
                    user_data.get("username"),
                    user_data.get("fullname"),
                    user_data.get("phone"),
                    user_data.get("position"),
                    user_data.get("department"),
                    bool(user_data.get("approved", False)),
                    bool(user_data.get("admin", False)),
                    Jsonb(payload),
                ),
            )
        conn.commit()
    return True


def get_user_by_id(user_id: int) -> dict | None:
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select * from bot.users where user_id = %s", (_to_int(user_id),))
            row = cur.fetchone()
    return _row_to_user(row) if row else None


def list_users() -> list[dict]:
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select * from bot.users order by created_at, user_id")
            rows = cur.fetchall()
    return [_row_to_user(row) for row in rows]


def update_user_fields(user_id: int, new_data: dict) -> bool:
    existing = get_user_by_id(user_id)
    if not existing:
        return False
    merged = existing.copy()
    merged.update(new_data or {})
    return upsert_user(merged)


def delete_user(user_id: int) -> bool:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("delete from bot.users where user_id = %s", (_to_int(user_id),))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def is_user_registered(user_id: int) -> bool:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select approved from bot.users where user_id = %s", (_to_int(user_id),))
            row = cur.fetchone()
    return bool(row and row[0])


def is_user_admin(user_id: int) -> bool:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select admin from bot.users where user_id = %s", (_to_int(user_id),))
            row = cur.fetchone()
    return bool(row and row[0])


def get_admin_username(admin_ids: list[int] | None = None) -> str | None:
    admin_ids = [int(x) for x in (admin_ids or [])]
    with _connect() as conn:
        with conn.cursor() as cur:
            if admin_ids:
                cur.execute(
                    """
                    select username
                    from bot.users
                    where user_id = any(%s)
                      and username is not null
                      and username <> ''
                    order by admin desc, approved desc, updated_at desc
                    limit 1
                    """,
                    (admin_ids,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return row[0]

            cur.execute(
                """
                select username
                from bot.users
                where admin = true
                  and username is not null
                  and username <> ''
                order by updated_at desc
                limit 1
                """
            )
            row = cur.fetchone()
    return row[0] if row and row[0] else None


def get_user_settings_from_supabase(user_id: int) -> dict:
    user_id = _to_int(user_id)
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select auto_numbering, payload from bot.user_settings where user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                default_payload = {"auto_numbering": False}
                cur.execute(
                    """
                    insert into bot.user_settings (user_id, auto_numbering, payload, updated_at)
                    values (%s, %s, %s, now())
                    on conflict (user_id) do nothing
                    """,
                    (user_id, False, Jsonb(default_payload)),
                )
                conn.commit()
                return default_payload

    payload = _to_payload_dict(row.get("payload")).copy()
    payload["auto_numbering"] = bool(row.get("auto_numbering", False))
    return payload


def update_user_settings_in_supabase(user_id: int, new_settings: dict) -> bool:
    user_id = _to_int(user_id)
    existing = get_user_settings_from_supabase(user_id)
    merged = existing.copy()
    merged.update(new_settings or {})
    auto_numbering = bool(merged.get("auto_numbering", False))

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into bot.user_settings (user_id, auto_numbering, payload, updated_at)
                values (%s, %s, %s, now())
                on conflict (user_id) do update set
                  auto_numbering = excluded.auto_numbering,
                  payload = excluded.payload,
                  updated_at = now()
                """,
                (user_id, auto_numbering, Jsonb(merged)),
            )
        conn.commit()
    return True


def get_next_form_number(application_type: str) -> int:
    form_type = _normalize_form_type(application_type)
    if form_type not in FORM_TYPES:
        raise ValueError(f"Unsupported form type: {application_type}")

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select coalesce(max(form_number), 0) + 1 from bot.forms where application_type = %s",
                (form_type,),
            )
            row = cur.fetchone()
    return int(row[0] if row else 1)


def save_form_to_supabase(form_data: dict) -> None:
    application_type = _normalize_form_type(form_data.get("type"))
    if application_type not in FORM_TYPES:
        raise ValueError(f"Unsupported form type: {application_type}")

    form_number = _to_int(form_data.get("form_number"))
    if form_number is None:
        raise ValueError("form_number is required")

    created_at = _parse_datetime(form_data.get("created_at"))
    user_id = _to_int(form_data.get("user_id"))
    creator_fullname = form_data.get("creator_fullname")

    if application_type == "checkin":
        contract_number = form_data.get("num_contract")
        form_text = None
        checkin_date = form_data.get("date")
        brig_name = form_data.get("name_brig")
        brig_phone = form_data.get("phone_brig")
        carring = form_data.get("carring")
    else:
        contract_number = form_data.get("contract_number")
        form_text = form_data.get("form_text")
        checkin_date = None
        brig_name = None
        brig_phone = None
        carring = None

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into bot.forms (
                  application_type, form_number, user_id, creator_fullname,
                  contract_number, form_text, checkin_date, brig_name, brig_phone, carring,
                  created_at, payload
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (application_type, form_number) do update set
                  user_id = excluded.user_id,
                  creator_fullname = excluded.creator_fullname,
                  contract_number = excluded.contract_number,
                  form_text = excluded.form_text,
                  checkin_date = excluded.checkin_date,
                  brig_name = excluded.brig_name,
                  brig_phone = excluded.brig_phone,
                  carring = excluded.carring,
                  created_at = excluded.created_at,
                  payload = excluded.payload
                """,
                (
                    application_type,
                    form_number,
                    user_id,
                    creator_fullname,
                    contract_number,
                    form_text,
                    checkin_date,
                    brig_name,
                    brig_phone,
                    carring,
                    created_at,
                    Jsonb(form_data),
                ),
            )
        conn.commit()


def get_form_by_type_and_number(application_type: str, form_number: int) -> dict | None:
    form_type = _normalize_form_type(application_type)
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select application_type, form_number, user_id, creator_fullname,
                       contract_number, form_text, checkin_date, brig_name, brig_phone, carring,
                       created_at, payload
                from bot.forms
                where application_type = %s and form_number = %s
                limit 1
                """,
                (form_type, _to_int(form_number)),
            )
            row = cur.fetchone()
    return _row_to_form_data(row) if row else None


def list_applications_by_type(application_type: str) -> list[dict]:
    form_type = _normalize_form_type(application_type)
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select id, application_type, form_number, user_id, creator_fullname,
                       contract_number, form_text, checkin_date, brig_name, brig_phone, carring,
                       created_at, payload
                from bot.forms
                where application_type = %s
                order by created_at nulls last, id
                """,
                (form_type,),
            )
            rows = cur.fetchall()
    return [_row_to_application(row) for row in rows]


def list_applications_by_user(user_id: int) -> list[dict]:
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select id, application_type, form_number, user_id, creator_fullname,
                       contract_number, form_text, checkin_date, brig_name, brig_phone, carring,
                       created_at, payload
                from bot.forms
                where user_id = %s
                order by created_at nulls last, id
                """,
                (_to_int(user_id),),
            )
            rows = cur.fetchall()
    return [_row_to_application(row) for row in rows]


def get_application_by_id(application_id: int | str) -> dict | None:
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select id, application_type, form_number, user_id, creator_fullname,
                       contract_number, form_text, checkin_date, brig_name, brig_phone, carring,
                       created_at, payload
                from bot.forms
                where id = %s
                limit 1
                """,
                (_to_int(application_id),),
            )
            row = cur.fetchone()
    return _row_to_application(row) if row else None


def update_application_field(application_id: int | str, field: str, value: str) -> bool:
    form_id = _to_int(application_id)
    column = APP_FIELD_TO_COLUMN.get(field)

    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select payload from bot.forms where id = %s", (form_id,))
            row = cur.fetchone()
            if not row:
                return False

            payload = _to_payload_dict(row.get("payload")).copy()
            payload[field] = value

            if field == "contract":
                payload["contract_number"] = value
                payload["num_contract"] = value
            elif field == "text":
                payload["form_text"] = value
            elif field == "date_checkin":
                payload["checkin_date"] = value
                payload["date"] = value
            elif field == "brigadier_name":
                payload["brig_name"] = value
                payload["name_brig"] = value
            elif field == "brigadier_phone":
                payload["brig_phone"] = value
                payload["phone_brig"] = value
            elif field == "carrying":
                payload["carring"] = value

            if column:
                cur.execute(
                    f"update bot.forms set {column} = %s, payload = %s where id = %s",
                    (value, Jsonb(payload), form_id),
                )
            else:
                cur.execute(
                    "update bot.forms set payload = %s where id = %s",
                    (Jsonb(payload), form_id),
                )
            updated = cur.rowcount > 0
        conn.commit()
    return updated


def delete_application(application_id: int | str) -> bool:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("delete from bot.forms where id = %s", (_to_int(application_id),))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def get_usage_stats() -> dict:
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select count(*) as total_users from bot.users")
            total_users = int(cur.fetchone()["total_users"])

            cur.execute("select count(*) as total_applications from bot.forms")
            total_applications = int(cur.fetchone()["total_applications"])

            cur.execute(
                """
                select count(*) as today_applications
                from bot.forms
                where coalesce(created_at::date, inserted_at::date) = current_date
                """
            )
            today_applications = int(cur.fetchone()["today_applications"])

    return {
        "total_users": total_users,
        "total_applications": total_applications,
        "today_applications": today_applications,
        "messages_sent": 0,
    }


def get_forms_grouped_for_export() -> dict:
    grouped = {
        "delivery": [],
        "refund": [],
        "painting": [],
        "checkin": [],
    }

    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select
                  application_type, created_at, creator_fullname, form_number, contract_number,
                  form_text, checkin_date, brig_name, brig_phone, carring
                from bot.forms
                order by created_at nulls last, id
                """
            )
            rows = cur.fetchall()

    for row in rows:
        application_type = row["application_type"]
        if application_type not in grouped:
            continue

        if application_type == "checkin":
            grouped[application_type].append(
                {
                    "created_at": _format_ts(row["created_at"]),
                    "creator_fullname": row["creator_fullname"] or "",
                    "form_number": row["form_number"] or "",
                    "contract_number": row["contract_number"] or "",
                    "checkin_date": row["checkin_date"] or "",
                    "brig_name": row["brig_name"] or "",
                    "brig_phone": row["brig_phone"] or "",
                    "carring": row["carring"] or "",
                }
            )
        else:
            grouped[application_type].append(
                {
                    "created_at": _format_ts(row["created_at"]),
                    "creator_fullname": row["creator_fullname"] or "",
                    "form_number": row["form_number"] or "",
                    "contract_number": row["contract_number"] or "",
                    "form_text": row["form_text"] or "",
                }
            )

    return grouped
