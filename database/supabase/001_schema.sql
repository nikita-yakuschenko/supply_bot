create schema if not exists bot;

create table if not exists bot.import_batches (
  id bigint generated always as identity primary key,
  source text not null,
  source_ref text,
  exported_at timestamptz,
  imported_at timestamptz not null default now(),
  meta jsonb not null default '{}'::jsonb
);

create table if not exists bot.sheet_rows_raw (
  id bigint generated always as identity primary key,
  batch_id bigint not null references bot.import_batches(id) on delete cascade,
  sheet_name text not null,
  source_row_number integer not null,
  row_data jsonb not null,
  created_at timestamptz not null default now(),
  unique (batch_id, sheet_name, source_row_number)
);

create index if not exists idx_sheet_rows_raw_sheet_row
  on bot.sheet_rows_raw (sheet_name, source_row_number);

create index if not exists idx_sheet_rows_raw_row_data_gin
  on bot.sheet_rows_raw using gin (row_data);

create table if not exists bot.applications_sheet_legacy (
  id bigint generated always as identity primary key,
  batch_id bigint not null references bot.import_batches(id) on delete cascade,
  sheet_name text not null,
  application_type text not null check (application_type in ('delivery', 'refund', 'painting', 'checkin', 'unknown')),
  source_row_number integer not null,
  submitted_at timestamptz,
  creator_fullname text,
  form_number bigint,
  contract_number text,
  form_text text,
  checkin_date text,
  brig_name text,
  brig_phone text,
  carring text,
  payload jsonb not null default '{}'::jsonb,
  imported_at timestamptz not null default now(),
  unique (batch_id, sheet_name, source_row_number)
);

create index if not exists idx_applications_sheet_legacy_type_submitted
  on bot.applications_sheet_legacy (application_type, submitted_at);

create index if not exists idx_applications_sheet_legacy_form_number
  on bot.applications_sheet_legacy (form_number);

create table if not exists bot.users (
  user_id bigint primary key,
  username text,
  fullname text,
  phone text,
  position text,
  department text,
  approved boolean not null default false,
  admin boolean not null default false,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists bot.user_settings (
  user_id bigint primary key,
  auto_numbering boolean not null default false,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists bot.forms (
  id bigint generated always as identity primary key,
  application_type text not null check (application_type in ('delivery', 'refund', 'painting', 'checkin')),
  form_number bigint not null,
  user_id bigint,
  creator_fullname text,
  contract_number text,
  form_text text,
  checkin_date text,
  brig_name text,
  brig_phone text,
  carring text,
  created_at timestamptz,
  payload jsonb not null default '{}'::jsonb,
  inserted_at timestamptz not null default now(),
  unique (application_type, form_number)
);

create index if not exists idx_forms_type_created_at
  on bot.forms (application_type, created_at);

create index if not exists idx_forms_user_id
  on bot.forms (user_id);
