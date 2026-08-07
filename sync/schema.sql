-- 一点不背 · Supabase 云端 schema
-- 执行方式：登录 Supabase Dashboard → SQL Editor → 粘贴本文件全部内容 → Run
-- 可重复执行（用了 IF NOT EXISTS）
--
-- 设计要点：
-- - 所有表用 (user_id, local_id) 复合主键，local_id 对应桌面端 SQLite 的 INTEGER id
-- - 每张表加 updated_at，由触发器自动维护，用于增量同步
-- - 启用 RLS：每个用户只能 CRUD 自己的数据
-- - 桌面端 SQLite schema 完全不改，同步是附加功能

-- ========== 1. categories ==========
create table if not exists categories (
  user_id uuid not null references auth.users(id) on delete cascade,
  local_id integer not null,
  name text not null,
  parent_id integer,
  sort_order integer not null default 0,
  updated_at timestamptz not null default now(),
  primary key (user_id, local_id)
);

-- ========== 2. items ==========
-- 注意：interval 是 Postgres 保留字，云端统一用 interval_days 列名
create table if not exists items (
  user_id uuid not null references auth.users(id) on delete cascade,
  local_id integer not null,
  title text not null,
  content text not null,
  created_date text not null,
  category_id integer,
  status text not null default 'learning',
  round integer not null default 1,
  interval_days integer not null default 0,
  consecutive_correct integer not null default 0,
  next_review_date text not null,
  notes text not null default '',
  deleted_at text,
  updated_at timestamptz not null default now(),
  primary key (user_id, local_id)
);
create index if not exists idx_items_user_next_review on items(user_id, next_review_date);
create index if not exists idx_items_user_status on items(user_id, status);
create index if not exists idx_items_user_updated on items(user_id, updated_at);

-- ========== 3. review_logs ==========
create table if not exists review_logs (
  user_id uuid not null references auth.users(id) on delete cascade,
  local_id integer not null,
  item_local_id integer not null,
  review_date text not null,
  round integer not null,
  result text not null,
  interval_after integer,
  updated_at timestamptz not null default now(),
  primary key (user_id, local_id)
);
create index if not exists idx_review_logs_user_item on review_logs(user_id, item_local_id);
create index if not exists idx_review_logs_user_date on review_logs(user_id, review_date);

-- ========== 4. item_marks ==========
create table if not exists item_marks (
  user_id uuid not null references auth.users(id) on delete cascade,
  local_id integer not null,
  item_local_id integer not null,
  start_pos integer not null,
  end_pos integer not null,
  mark_type text not null,
  created_date text not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, local_id)
);
create index if not exists idx_item_marks_user_item on item_marks(user_id, item_local_id);

-- ========== 5. settings ==========
create table if not exists settings (
  user_id uuid not null references auth.users(id) on delete cascade,
  key text not null,
  value text not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, key)
);

-- ========== 5b. key_folders / key_items（重点条目）==========
create table if not exists key_folders (
  user_id uuid not null references auth.users(id) on delete cascade,
  local_id integer not null,
  name text not null,
  sort_order integer not null default 0,
  created_date text not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, local_id)
);
create index if not exists idx_key_folders_user on key_folders(user_id);

create table if not exists key_items (
  user_id uuid not null references auth.users(id) on delete cascade,
  folder_local_id integer not null,
  item_local_id integer not null,
  created_date text not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, folder_local_id, item_local_id)
);
create index if not exists idx_key_items_user on key_items(user_id, folder_local_id);

-- ========== 6. updated_at 自动更新触发器 ==========
create or replace function touch_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_categories_touch on categories;
create trigger trg_categories_touch before update on categories
  for each row execute function touch_updated_at();

drop trigger if exists trg_items_touch on items;
create trigger trg_items_touch before update on items
  for each row execute function touch_updated_at();

drop trigger if exists trg_review_logs_touch on review_logs;
create trigger trg_review_logs_touch before update on review_logs
  for each row execute function touch_updated_at();

drop trigger if exists trg_item_marks_touch on item_marks;
create trigger trg_item_marks_touch before update on item_marks
  for each row execute function touch_updated_at();

drop trigger if exists trg_settings_touch on settings;
create trigger trg_settings_touch before update on settings
  for each row execute function touch_updated_at();

drop trigger if exists trg_key_folders_touch on key_folders;
create trigger trg_key_folders_touch before update on key_folders
  for each row execute function touch_updated_at();

drop trigger if exists trg_key_items_touch on key_items;
create trigger trg_key_items_touch before update on key_items
  for each row execute function touch_updated_at();

-- ========== 7. 启用 RLS ==========
alter table categories enable row level security;
alter table items enable row level security;
alter table review_logs enable row level security;
alter table item_marks enable row level security;
alter table settings enable row level security;
alter table key_folders enable row level security;
alter table key_items enable row level security;

-- ========== 8. RLS 策略（用户只能 CRUD 自己的数据）==========
-- 用 DO 块包裹，可重复执行（已存在则跳过）
do $$
begin
  if not exists (select 1 from pg_policies where tablename='categories' and policyname='user_own_categories') then
    create policy user_own_categories on categories
      for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where tablename='items' and policyname='user_own_items') then
    create policy user_own_items on items
      for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where tablename='review_logs' and policyname='user_own_review_logs') then
    create policy user_own_review_logs on review_logs
      for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where tablename='item_marks' and policyname='user_own_item_marks') then
    create policy user_own_item_marks on item_marks
      for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where tablename='settings' and policyname='user_own_settings') then
    create policy user_own_settings on settings
      for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where tablename='key_folders' and policyname='user_own_key_folders') then
    create policy user_own_key_folders on key_folders
      for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where tablename='key_items' and policyname='user_own_key_items') then
    create policy user_own_key_items on key_items
      for all using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
end $$;

-- ========== 9. 自动维护 user_id 的触发器（可选，方便手机端直接 INSERT）==========
-- 手机端通过 REST API 写入时，需手动带 user_id（RLS 不会自动填充）
-- 这里提供一个 convenience RPC：get_my_due_items(today)
create or replace function get_my_due_items(p_today text)
returns table (
  local_id integer,
  title text,
  content text,
  created_date text,
  category_id integer,
  status text,
  round integer,
  interval_days integer,
  consecutive_correct integer,
  next_review_date text,
  notes text,
  is_retest boolean
)
language sql
security definer
as $$
  select i.local_id, i.title, i.content, i.created_date, i.category_id,
         i.status, i.round, i.interval_days, i.consecutive_correct,
         i.next_review_date, i.notes,
         exists(select 1 from review_logs rl
                where rl.user_id = auth.uid()
                  and rl.item_local_id = i.local_id
                  and rl.review_date = p_today) as is_retest
  from items i
  where i.user_id = auth.uid()
    and i.deleted_at is null
    and i.status = 'learning'
    and i.next_review_date != ''
    and i.next_review_date <= p_today
  order by i.next_review_date asc;
$$;

comment on function get_my_due_items(text) is '获取当前用户今日待背诵条目（含是否重背标记）';
