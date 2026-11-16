create table if not exists items (
  id         bigserial primary key,
  kind       text not null default 'task',      -- task | deadline | birthday | event
  title      text not null,
  due_date   date,
  due_time   time,
  yearly     boolean not null default false,
  offsets    int[] not null default '{0}',      -- days before the due date to remind
  done       boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists reminders (
  id          bigserial primary key,
  item_id     bigint not null references items(id) on delete cascade,
  remind_at   timestamptz not null,
  days_before int not null,
  sent        boolean not null default false
);
create index if not exists reminders_due_idx on reminders (remind_at) where not sent;

create table if not exists notes (
  id         bigserial primary key,
  content    text not null,
  created_at timestamptz not null default now()
);

create table if not exists messages (
  id         bigserial primary key,
  role       text not null,
  content    text not null,
  created_at timestamptz not null default now()
);
