#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb


def _strip_host_scheme(value: str | None) -> str:
    """Убирает https:// и http:// из хоста."""
    if not value:
        return value or ""
    s = value.strip()
    for prefix in ("https://", "http://"):
        if s.lower().startswith(prefix):
            return s[len(prefix) :].strip()
    return s


def resolve_database_url(cli_value: str | None) -> str | None:
    if cli_value:
        return cli_value
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        if "@https://" in env_url or "@http://" in env_url:
            env_url = env_url.replace("@https://", "@").replace("@http://", "@")
        return env_url

    supabase_host = _strip_host_scheme(os.getenv("SUPABASE_HOST"))
    postgres_password = os.getenv("POSTGRES_PASSWORD")
    if supabase_host and postgres_password:
        db = os.getenv("POSTGRES_DB", "postgres")
        tenant = os.getenv("POOLER_TENANT_ID")
        base_user = os.getenv("POSTGRES_USER", "postgres")
        user = f"{base_user}.{tenant}" if tenant else base_user
        port = os.getenv("POOLER_PROXY_PORT_TRANSACTION", "6543")
        return f"postgresql://{user}:{postgres_password}@{supabase_host}:{port}/{db}"

    host = _strip_host_scheme(os.getenv("SUPABASE_DB_HOST"))
    port = os.getenv("SUPABASE_DB_PORT", "5432")
    db = os.getenv("SUPABASE_DB_NAME", "postgres")
    user = os.getenv("SUPABASE_DB_USER", "postgres")
    password = os.getenv("SUPABASE_DB_PASSWORD")
    if host and password:
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return None


def parse_dt(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            parsed = dt.datetime.strptime(value, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def apply_schema(cur: psycopg.Cursor, schema_file: Path) -> None:
    sql = schema_file.read_text(encoding="utf-8")
    cur.execute(sql)


def import_users(cur: psycopg.Cursor, users: list[dict]) -> int:
    if not users:
        return 0
    cur.executemany(
        """
        insert into bot.users (
          user_id, username, fullname, phone, position, department, approved, admin, payload, updated_at
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
        [
            (
                int(item["user_id"]),
                item.get("username"),
                item.get("fullname"),
                item.get("phone"),
                item.get("position"),
                item.get("department"),
                bool(item.get("approved", False)),
                bool(item.get("admin", False)),
                Jsonb(item),
            )
            for item in users
            if item.get("user_id") is not None
        ],
    )
    return len(users)


def import_settings(cur: psycopg.Cursor, settings: dict) -> int:
    if not settings:
        return 0
    cur.executemany(
        """
        insert into bot.user_settings (user_id, auto_numbering, payload, updated_at)
        values (%s, %s, %s, now())
        on conflict (user_id) do update set
          auto_numbering = excluded.auto_numbering,
          payload = excluded.payload,
          updated_at = now()
        """,
        [
            (int(user_id), bool(payload.get("auto_numbering", False)), Jsonb(payload))
            for user_id, payload in settings.items()
        ],
    )
    return len(settings)


def import_forms(cur: psycopg.Cursor, application_type: str, forms: list[dict]) -> int:
    if not forms:
        return 0

    def form_record(item: dict):
        if application_type == "checkin":
            contract_number = item.get("num_contract")
            form_text = None
            checkin_date = item.get("date")
            brig_name = item.get("name_brig")
            brig_phone = item.get("phone_brig")
            carring = item.get("carring")
        else:
            contract_number = item.get("contract_number")
            form_text = item.get("form_text")
            checkin_date = None
            brig_name = None
            brig_phone = None
            carring = None

        return (
            application_type,
            int(item.get("form_number")) if item.get("form_number") is not None else None,
            int(item.get("user_id")) if item.get("user_id") is not None else None,
            item.get("creator_fullname"),
            contract_number,
            form_text,
            checkin_date,
            brig_name,
            brig_phone,
            carring,
            parse_dt(item.get("created_at")),
            Jsonb(item),
        )

    records = [form_record(item) for item in forms if item.get("form_number") is not None]
    cur.executemany(
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
        records,
    )
    return len(records)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Import local JSON data files into Supabase/Postgres."
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--schema-file", default="database/supabase/001_schema.sql")
    parser.add_argument("--skip-schema", action="store_true")
    args = parser.parse_args()

    database_url = resolve_database_url(args.database_url)
    if not database_url:
        raise SystemExit("DATABASE_URL is not set and --database-url is missing.")

    data_dir = Path(args.data_dir)

    users = load_json(data_dir / "users.json", [])
    settings = load_json(data_dir / "user_settings.json", {})
    delivery_forms = load_json(data_dir / "delivery_forms.json", [])
    refund_forms = load_json(data_dir / "refund_forms.json", [])
    painting_forms = load_json(data_dir / "painting_forms.json", [])
    checkin_forms = load_json(data_dir / "checkin_forms.json", [])

    with psycopg.connect(database_url, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            if not args.skip_schema:
                apply_schema(cur, Path(args.schema_file))

            users_count = import_users(cur, users)
            settings_count = import_settings(cur, settings)
            delivery_count = import_forms(cur, "delivery", delivery_forms)
            refund_count = import_forms(cur, "refund", refund_forms)
            painting_count = import_forms(cur, "painting", painting_forms)
            checkin_count = import_forms(cur, "checkin", checkin_forms)

        conn.commit()

    print(
        "Local JSON import complete. "
        f"users={users_count} settings={settings_count} "
        f"forms={{delivery:{delivery_count}, refund:{refund_count}, painting:{painting_count}, checkin:{checkin_count}}}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
