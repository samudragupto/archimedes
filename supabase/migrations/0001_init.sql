-- ============================================================================
-- ARCHIMEDES · 0001_init.sql — initial schema
--
-- What lives here, and why:
--   * 9 tables: profiles, projects, documents, requirements, research_findings,
--     sections, compliance_issues, jobs, job_events.
--   * Row Level Security on every table: a user can only read/write rows that
--     belong to their own projects (auth.uid()). Child tables are scoped
--     through the owning project. The agent worker authenticates with the
--     SERVICE_ROLE key, which bypasses RLS by design — that is the only
--     cross-user write path, and it never runs in the browser.
--   * jobs, job_events, sections and compliance_issues are added to the
--     supabase_realtime publication so the UI can stream agent progress
--     live without polling.
--   * A private `documents` storage bucket with one folder per user
--     (folder name = auth.uid()), enforced by storage.objects policies.
--   * A trigger auto-creates a profile row whenever a user signs up.
--
-- Run once on a fresh Supabase project:  supabase db push   (or the SQL editor)
-- ============================================================================

create extension if not exists pgcrypto; -- gen_random_uuid(), crypt()

-- ----------------------------------------------------------------------------
-- Enums — CHECK-free state machines, enforced by the type system
-- ----------------------------------------------------------------------------
create type public.project_status       as enum ('draft','extracting','researching','drafting','auditing','revising','complete','failed');
create type public.document_kind        as enum ('solicitation','organization','supporting');
create type public.requirement_category as enum ('deadline','budget','eligibility','section','format','evaluation','other');
create type public.section_status       as enum ('pending','drafting','done','needs_revision');
create type public.issue_severity       as enum ('blocker','major','minor');
create type public.job_status           as enum ('queued','running','succeeded','failed');
create type public.job_event_level      as enum ('info','model','tool','warn','error');
create type public.job_runtime          as enum ('nebius_serverless','local');

-- ----------------------------------------------------------------------------
-- profiles — extension of auth.users with org metadata
-- ----------------------------------------------------------------------------
create table public.profiles (
  id              uuid primary key references auth.users (id) on delete cascade,
  org_name        text not null default '',
  org_description text not null default '',
  website         text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- projects — one grant application workspace
-- status walks the enum in pipeline order; the UI keys progress UI off it.
-- The two document FKs are added after `documents` exists (circular ref).
-- ----------------------------------------------------------------------------
create table public.projects (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users (id) on delete cascade,
  title               text not null,
  funder_name         text,
  status              public.project_status not null default 'draft',
  solicitation_doc_id uuid,
  org_doc_id          uuid,
  compliance_score    integer check (compliance_score between 0 and 100),
  abstract            text,  -- written by the finalize node (150-word summary)
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- documents — parsed source material (PDF upload or fetched URL)
-- extracted_text is the chunkable plain text the agent nodes consume.
-- ----------------------------------------------------------------------------
create table public.documents (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references public.projects (id) on delete cascade,
  kind           public.document_kind not null,
  filename       text,
  storage_path   text,                         -- key inside the `documents` bucket
  source_url     text,                         -- set when ingested from a URL
  extracted_text text not null default '',
  page_count     integer,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

-- A project holds at most one solicitation and one org profile; the API
-- replaces a document by deleting the old row first (ON DELETE SET NULL
-- on projects keeps the pointer honest in every interleaving).
create unique index documents_one_solicitation on public.documents (project_id) where kind = 'solicitation';
create unique index documents_one_organization on public.documents (project_id) where kind = 'organization';

alter table public.projects
  add constraint projects_solicitation_doc_fkey
    foreign key (solicitation_doc_id) references public.documents (id) on delete set null,
  add constraint projects_org_doc_fkey
    foreign key (org_doc_id)          references public.documents (id) on delete set null;

-- ----------------------------------------------------------------------------
-- requirements — structured extraction output of the solicitation
-- source_excerpt keeps the verbatim quote so the UI can prove every extracted
-- rule against the source document (hover-proof, no hallucinated rules).
-- ----------------------------------------------------------------------------
create table public.requirements (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references public.projects (id) on delete cascade,
  category       public.requirement_category not null default 'other',
  key            text not null,                -- short label, e.g. "Page limit"
  value          text not null default '',     -- normalized value, e.g. "16 pages"
  is_mandatory   boolean not null default false,
  source_excerpt text,
  confidence     double precision not null default 0.0 check (confidence between 0 and 1),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- research_findings — only URLs actually returned by Tavily ever land here,
-- which is what makes the proposal's inline citations non-fabricated.
-- ----------------------------------------------------------------------------
create table public.research_findings (
  id               uuid primary key default gen_random_uuid(),
  project_id       uuid not null references public.projects (id) on delete cascade,
  query            text not null,
  title            text not null,
  url              text not null,
  snippet          text,
  relevance        double precision not null default 0.0 check (relevance between 0 and 1),
  used_in_sections text[] not null default '{}', -- section titles citing this finding
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- sections — the proposal draft, one row per section
-- Persisted section-by-section as the ULTRA node finishes each one, so the
-- editor fills in live during a run. model_used proves which Nemotron tier
-- wrote what.
-- ----------------------------------------------------------------------------
create table public.sections (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references public.projects (id) on delete cascade,
  order_index integer not null,
  title       text not null,
  content_md  text not null default '',
  model_used  text,
  token_count integer default 0,
  status      public.section_status not null default 'pending',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (project_id, order_index)
);

-- ----------------------------------------------------------------------------
-- compliance_issues — audit output, one row per found problem
-- requirement_id links an issue back to the exact extracted rule it violates.
-- ----------------------------------------------------------------------------
create table public.compliance_issues (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references public.projects (id) on delete cascade,
  section_id     uuid references public.sections (id) on delete set null,
  requirement_id uuid references public.requirements (id) on delete set null,
  severity       public.issue_severity not null,
  description    text not null,
  suggested_fix  text,
  resolved       boolean not null default false,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- jobs + job_events — background pipeline execution and its live trace
-- job_events is the append-only stream behind the terminal-style Agent Run
-- console (model / tool / info / warn / error), including per-call
-- tokens_in / tokens_out / latency_ms / model_used for the Model Router panel.
-- ----------------------------------------------------------------------------
create table public.jobs (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references public.projects (id) on delete cascade,
  kind         text not null default 'full_pipeline',
  status       public.job_status not null default 'queued',
  progress     integer not null default 0 check (progress between 0 and 100),
  current_step text,
  error        text,
  runtime      public.job_runtime not null default 'local',
  started_at   timestamptz,
  finished_at  timestamptz,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create table public.job_events (
  id         uuid primary key default gen_random_uuid(),
  job_id     uuid not null references public.jobs (id) on delete cascade,
  ts         timestamptz not null default now(),
  level      public.job_event_level not null default 'info',
  step       text,
  message    text not null,
  model_used text,
  tokens_in  integer,
  tokens_out integer,
  latency_ms integer
);

-- ----------------------------------------------------------------------------
-- Indexes — every query the API makes is covered
-- ----------------------------------------------------------------------------
create index projects_user_idx        on public.projects (user_id, created_at desc);
create index documents_project_idx    on public.documents (project_id);
create index requirements_project_idx on public.requirements (project_id, category);
create index findings_project_idx     on public.research_findings (project_id);
create index sections_project_idx     on public.sections (project_id, order_index);
create index issues_project_idx       on public.compliance_issues (project_id);
create index issues_open_idx          on public.compliance_issues (project_id) where not resolved;
create index jobs_project_idx         on public.jobs (project_id, created_at desc);
create index job_events_job_idx       on public.job_events (job_id, ts);

-- ----------------------------------------------------------------------------
-- updated_at bookkeeping for all mutable tables (job_events is append-only)
-- ----------------------------------------------------------------------------
create or replace function public.set_updated_at ()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

do $$
declare t text;
begin
  foreach t in array array[
    'profiles', 'projects', 'documents', 'requirements',
    'research_findings', 'sections', 'compliance_issues', 'jobs'
  ] loop
    execute format(
      'create trigger set_%s_updated_at before update on public.%I
       for each row execute function public.set_updated_at()', t, t
    );
  end loop;
end;
$$;

-- ============================================================================
-- Row Level Security — owners only, scoped through projects
-- ============================================================================
alter table public.profiles          enable row level security;
alter table public.projects          enable row level security;
alter table public.documents         enable row level security;
alter table public.requirements      enable row level security;
alter table public.research_findings enable row level security;
alter table public.sections          enable row level security;
alter table public.compliance_issues enable row level security;
alter table public.jobs              enable row level security;
alter table public.job_events        enable row level security;

-- profiles: a user sees exactly their own row
create policy "profiles_select_own" on public.profiles for select to authenticated
  using (id = auth.uid());
create policy "profiles_insert_own" on public.profiles for insert to authenticated
  with check (id = auth.uid());
create policy "profiles_update_own" on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());
create policy "profiles_delete_own" on public.profiles for delete to authenticated
  using (id = auth.uid());

-- projects: direct ownership
create policy "projects_owner_all" on public.projects for all to authenticated
  using      (user_id = auth.uid())
  with check (user_id = auth.uid());

-- child tables: scoped through the owning project
create policy "documents_owner_all" on public.documents for all to authenticated
  using      (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()));

create policy "requirements_owner_all" on public.requirements for all to authenticated
  using      (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()));

create policy "findings_owner_all" on public.research_findings for all to authenticated
  using      (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()));

create policy "sections_owner_all" on public.sections for all to authenticated
  using      (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()));

create policy "issues_owner_all" on public.compliance_issues for all to authenticated
  using      (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()));

create policy "jobs_owner_all" on public.jobs for all to authenticated
  using      (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = auth.uid()));

create policy "job_events_owner_all" on public.job_events for all to authenticated
  using      (exists (
    select 1 from public.jobs j
    join public.projects p on p.id = j.project_id
    where j.id = job_id and p.user_id = auth.uid()))
  with check (exists (
    select 1 from public.jobs j
    join public.projects p on p.id = j.project_id
    where j.id = job_id and p.user_id = auth.uid()));

-- ============================================================================
-- Realtime — stream agent progress to the UI without polling
-- ============================================================================
alter publication supabase_realtime add table public.jobs;
alter publication supabase_realtime add table public.job_events;
alter publication supabase_realtime add table public.sections;
alter publication supabase_realtime add table public.compliance_issues;

-- ----------------------------------------------------------------------------
-- Grants (Supabase grants most of this by default; kept explicit so the same
-- migration also works on a self-hosted stack)
-- ----------------------------------------------------------------------------
grant usage on schema public to anon, authenticated, service_role;
grant select, insert, update, delete on all tables in schema public to authenticated;
grant all on all tables in schema public to service_role;

-- ============================================================================
-- Storage — private `documents` bucket, one folder per user (folder = user id)
-- ============================================================================
insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do update set public = false;

create policy "documents_bucket_select" on storage.objects for select to authenticated
  using (bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "documents_bucket_insert" on storage.objects for insert to authenticated
  with check (bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "documents_bucket_update" on storage.objects for update to authenticated
  using      (bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "documents_bucket_delete" on storage.objects for delete to authenticated
  using (bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text);

-- ============================================================================
-- Auto-create a profile whenever a user signs up (magic link or OAuth)
-- ============================================================================
create or replace function public.handle_new_user ()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, org_name)
  values (
    new.id,
    coalesce(
      new.raw_user_meta_data ->> 'org_name',
      split_part(coalesce(new.email, ''), '@', 1)
    )
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
