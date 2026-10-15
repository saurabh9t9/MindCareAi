create table if not exists public.wellness_checkins (
    id bigint generated always as identity primary key,
    uid text not null,
    ts double precision not null,
    mood integer not null check (mood between 1 and 5),
    stress integer not null check (stress between 1 and 5),
    sleep double precision not null check (sleep between 0 and 24)
);

create index if not exists wellness_checkins_uid_ts_idx
    on public.wellness_checkins (uid, ts desc);
create index if not exists wellness_checkins_ts_idx
    on public.wellness_checkins (ts);

create table if not exists public.self_screenings (
    id bigint generated always as identity primary key,
    uid text not null,
    ts double precision not null,
    phq2 integer not null check (phq2 between 0 and 6),
    gad2 integer not null check (gad2 between 0 and 6)
);

create index if not exists self_screenings_uid_idx
    on public.self_screenings (uid);

create table if not exists public.crisis_events (
    id bigint generated always as identity primary key,
    uid text not null,
    ts double precision not null
);

create index if not exists crisis_events_ts_idx
    on public.crisis_events (ts);

create table if not exists public.website_assessments (
    id bigint generated always as identity primary key,
    created_at timestamptz not null default now(),
    data jsonb not null check (jsonb_typeof(data) = 'object')
);

alter table public.wellness_checkins enable row level security;
alter table public.self_screenings enable row level security;
alter table public.crisis_events enable row level security;
alter table public.website_assessments enable row level security;

revoke all on public.wellness_checkins, public.self_screenings,
    public.crisis_events, public.website_assessments from public, anon, authenticated;
grant all on public.wellness_checkins, public.self_screenings,
    public.crisis_events, public.website_assessments to service_role;
