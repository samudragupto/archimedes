-- ============================================================================
-- ARCHIMEDES · seed.sql — optional demo data
--
-- Seeds one demo account (demo@archimedes.dev / archimedes-demo) with a fully
-- populated sample project: an original, NSF-STYLE mock solicitation ("CRPG-
-- 2026", written for this repo, not a real program) and a mock non-profit
-- profile, plus a finished pipeline run (requirements, sections, findings,
-- compliance issues, job + events) so the dashboard is never empty.
--
-- The in-app "Demo Project" button (scripts/demo_seed.py) seeds the same
-- fixture for whichever user is logged in — this file exists so a fresh
-- Supabase project has something to show immediately.
--
-- Idempotent (fixed UUIDs + ON CONFLICT DO NOTHING). Run as postgres /
-- service role (bypasses RLS): Supabase SQL editor, or
--   psql "$SUPABASE_DB_URL" -f supabase/seed.sql
-- ============================================================================

begin;

-- -----------------------------------------------------------------------------
-- Demo user (password sign-in enabled; magic link also works)
-- -----------------------------------------------------------------------------
insert into auth.users (
  id, aud, role, email, encrypted_password, email_confirmed_at,
  created_at, updated_at, raw_app_meta_data, raw_user_meta_data
) values (
  '00000000-0000-4000-8000-000000000001',
  'authenticated',
  'authenticated',
  'demo@archimedes.dev',
  crypt('archimedes-demo', gen_salt('bf')),
  now(), now(), now(),
  '{"provider":"email","providers":["email"]}'::jsonb,
  '{"org_name":"Riverbend Community Health Collective"}'::jsonb
) on conflict (id) do nothing;

insert into auth.identities (
  provider, provider_id, user_id, identity_data, last_sign_in_at, created_at, updated_at
) values (
  'email',
  '00000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000001',
  jsonb_build_object(
    'sub', '00000000-0000-4000-8000-000000000001',
    'email', 'demo@archimedes.dev',
    'provider', 'email'
  ),
  now(), now(), now()
) on conflict (provider_id, provider) do nothing;

-- handle_new_user trigger fires on the insert above; make the profile richer
insert into public.profiles (id, org_name, org_description, website) values (
  '00000000-0000-4000-8000-000000000001',
  'Riverbend Community Health Collective',
  'A 501(c)(3) community health non-profit (est. 2016) serving flood-prone neighborhoods of Cedar Falls, Iowa. Runs resident-led resilience, outreach, and preparedness programs with 6 FTE staff and 40 trained volunteers.',
  'https://riverbendhealth.example.org'
) on conflict (id) do update set
  org_name        = excluded.org_name,
  org_description = excluded.org_description,
  website         = excluded.website;

-- -----------------------------------------------------------------------------
-- Demo project + its two parsed documents (original fixture text)
-- -----------------------------------------------------------------------------
insert into public.projects (
  id, user_id, title, funder_name, status, compliance_score, created_at, updated_at
) values (
  '00000000-0000-4000-8000-000000000002',
  '00000000-0000-4000-8000-000000000001',
  'Community Flood-Sensor Network & Resident Response Program',
  'National Resilience Foundation (mock NSF-style program)',
  'complete',
  84,
  now() - interval '3 hours', now() - interval '117 minutes'
) on conflict (id) do nothing;

insert into public.documents (id, project_id, kind, filename, extracted_text, page_count, created_at) values (
  '00000000-0000-4000-8000-000000000003',
  '00000000-0000-4000-8000-000000000002',
  'solicitation',
  'CRPG-2026-solicitation.pdf',
  $sol$COMMUNITY RESILIENCE PLANNING GRANTS PROGRAM (CRPG-2026)
Request for Proposals — National Resilience Foundation (mock NSF-style program)

1. OVERVIEW. The National Resilience Foundation invites proposals for community-
led projects that strengthen local capacity to anticipate, withstand, and
recover from climate-driven hazards such as flooding and extreme heat.

2. DEADLINE. Proposals are due November 15, 2026, 5:00 PM ET. Late proposals
will not be reviewed.

3. AWARD CEILING AND PERIOD. Up to $250,000 in total costs per award for a
project period of up to 24 months. Cost sharing is not required.

4. ELIGIBILITY. U.S. 501(c)(3) non-profit organizations, accredited
institutions of higher education, and state, local, or tribal government
entities may apply.

5. REQUIRED PROPOSAL SECTIONS (page limits strictly enforced):
   (a) Project Summary — max 1 page
   (b) Statement of Need — max 3 pages; must include cited demographic and
       hazard data
   (c) Project Design and Methodology — max 6 pages
   (d) Evaluation Plan — max 2 pages; must define measurable outcomes
   (e) Budget and Budget Justification — max 2 pages
   (f) Organizational Capacity — max 2 pages
   (g) Appendices — unlimited; not counted toward the narrative limit

6. FORMATTING. 11-point font or larger, single-spaced, 1-inch margins, PDF
upload. Total narrative limit: 16 pages across sections (a)-(f).

7. REVIEW CRITERIA. Proposals are scored as follows: Intellectual Merit (30%),
Community Impact (30%), Feasibility and Capacity (25%), Budget Adequacy (15%).

8. REPORTING. Grantees submit quarterly progress reports and a final outcomes
report within 90 days of the project period end date.$sol$,
  3, now() - interval '3 hours'
) on conflict (id) do nothing;

insert into public.documents (id, project_id, kind, filename, extracted_text, page_count, created_at) values (
  '00000000-0000-4000-8000-000000000004',
  '00000000-0000-4000-8000-000000000002',
  'organization',
  'riverbend-profile.txt',
  $org$Riverbend Community Health Collective — Organizational Profile

501(c)(3) non-profit founded 2016, serving Cedar Falls and surrounding Black
Hawk County, Iowa. Mission: community-led health and resilience programs for
underserved neighborhoods.

Capacity: 6 FTE staff, 40 trained resident volunteers, annual operating budget
$780,000. Prior awards: Iowa Watershed Approach community grant (2022–2024,
$180,000), Wellmark Foundation healthy-communities grant (2021, $45,000).

Programs: block-captain preparedness network, mobile outreach clinic, summer
heat-safety campaign. During the 2024 flood season Riverbend coordinated door-
to-door warnings for 1,900 households in partnership with county emergency
management.

Proposed project team: Dr. Maya Ellison (Executive Director, 15 yrs community
health), T. Okafor (Programs Director), Prof. L. Whitfield (evaluation
partner, University of Northern Iowa).$org$,
  1, now() - interval '3 hours'
) on conflict (id) do nothing;

-- link the documents to the project (after both sides exist — FK ordering)
update public.projects set
  solicitation_doc_id = '00000000-0000-4000-8000-000000000003',
  org_doc_id          = '00000000-0000-4000-8000-000000000004'
where id = '00000000-0000-4000-8000-000000000002';

-- -----------------------------------------------------------------------------
-- Requirements (extracted from the solicitation above)
-- -----------------------------------------------------------------------------
insert into public.requirements (id, project_id, category, key, value, is_mandatory, source_excerpt, confidence, created_at) values
  ('00000000-0000-4000-8000-000000000011', '00000000-0000-4000-8000-000000000002', 'deadline',    'Proposal deadline',     '2026-11-15 17:00 ET',                                              true,  'Proposals are due November 15, 2026, 5:00 PM ET.', 0.99, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000012', '00000000-0000-4000-8000-000000000002', 'budget',      'Maximum total award',   '$250,000 (total costs, 24-month project period)',                  true,  'Up to $250,000 in total costs per award for a project period of up to 24 months.', 0.97, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000013', '00000000-0000-4000-8000-000000000002', 'eligibility', 'Eligible applicants',   '501(c)(3) nonprofits; accredited IHEs; state/local/tribal govts',  true,  'U.S. 501(c)(3) non-profit organizations, accredited institutions of higher education, and state, local, or tribal government entities may apply.', 0.95, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000014', '00000000-0000-4000-8000-000000000002', 'section',     'Project Summary',       'max 1 page',                                                       true,  '(a) Project Summary — max 1 page', 0.96, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000015', '00000000-0000-4000-8000-000000000002', 'section',     'Statement of Need',     'max 3 pages; must cite demographic and hazard data',               true,  '(b) Statement of Need — max 3 pages; must include cited demographic and hazard data', 0.96, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000016', '00000000-0000-4000-8000-000000000002', 'section',     'Evaluation Plan',       'max 2 pages; measurable outcomes required',                        true,  '(d) Evaluation Plan — max 2 pages; must define measurable outcomes', 0.95, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000017', '00000000-0000-4000-8000-000000000002', 'format',      'Formatting rules',      '11-pt font, single-spaced, 1-inch margins, PDF upload',            true,  '11-point font or larger, single-spaced, 1-inch margins, PDF upload.', 0.98, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000018', '00000000-0000-4000-8000-000000000002', 'format',      'Narrative page limit',  '16 pages across sections (a)-(f)',                                 true,  'Total narrative limit: 16 pages across sections (a)-(f).', 0.93, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000019', '00000000-0000-4000-8000-000000000002', 'evaluation',  'Review criteria',       'Intellectual Merit 30% · Community Impact 30% · Feasibility & Capacity 25% · Budget Adequacy 15%', true, 'Intellectual Merit (30%), Community Impact (30%), Feasibility and Capacity (25%), Budget Adequacy (15%).', 0.94, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000020', '00000000-0000-4000-8000-000000000002', 'other',       'Cost sharing',          'Not required',                                                     false, 'Cost sharing is not required.', 0.90, now() - interval '2 hours')
on conflict (id) do nothing;

-- -----------------------------------------------------------------------------
-- Research findings (FIXTURE rows with placeholder URLs — the live pipeline
-- only ever stores URLs actually returned by Tavily)
-- -----------------------------------------------------------------------------
insert into public.research_findings (id, project_id, query, title, url, snippet, relevance, used_in_sections, created_at) values
  ('00000000-0000-4000-8000-000000000021', '00000000-0000-4000-8000-000000000002',
   'FEMA National Risk Index Black Hawk County riverine flood risk rating',
   'National Risk Index for Natural Hazards — Black Hawk County, IA',
   'https://example.org/archimedes-demo/nri-black-hawk',
   'County-level riverine flood risk rated in the 92nd national percentile; annualized loss estimate driven by residential structures.',
   0.93, '{Statement of Need}', now() - interval '115 minutes'),
  ('00000000-0000-4000-8000-000000000022', '00000000-0000-4000-8000-000000000002',
   'community-operated flood sensor networks warning lead time improvement',
   'Dense community flood-sensing networks extend actionable warning lead time',
   'https://example.org/archimedes-demo/community-sensing-study',
   'Volunteer gauge networks increased usable lead time by 45–90 minutes in flash-flood-prone watersheds compared with single upstream gauges.',
   0.88, '{Statement of Need,Project Design and Methodology}', now() - interval '114 minutes'),
  ('00000000-0000-4000-8000-000000000023', '00000000-0000-4000-8000-000000000002',
   'Cedar Falls 2024 flood after action report water rescues east side',
   'Black Hawk County 2024 Flood After-Action Report (excerpt)',
   'https://example.org/archimedes-demo/2024-aar',
   'After-action survey found most east-side residents received official warning only after water had entered streets; 14 of 21 water rescues in two tracts.',
   0.81, '{Statement of Need}', now() - interval '113 minutes')
on conflict (id) do nothing;

-- -----------------------------------------------------------------------------
-- Sections — 3 drafted by the fixture run, 3 left pending
-- -----------------------------------------------------------------------------
insert into public.sections (id, project_id, order_index, title, content_md, model_used, token_count, status, created_at, updated_at) values
  ('00000000-0000-4000-8000-000000000031', '00000000-0000-4000-8000-000000000002', 1,
   'Project Summary',
   E'## Project Summary\n\nRiverbend Community Health Collective will deploy a low-cost, community-operated flood sensor network across four underserved neighborhoods in Cedar Falls, Iowa, converting real-time water-level data into plain-language alerts and resident-led response drills. The 24-month project pursues three objectives: (1) install and maintain 40 open-hardware sensors at flood-prone stormwater outfalls; (2) train 60 resident "flood wardens" to interpret data and run block-level response protocols; and (3) co-produce with county emergency management a data-driven evacuation playbook for the Route 955 corridor.\n\nThe project directly answers CRPG-2026''s goal of community-led resilience: sensors are assembled and calibrated by local high-school robotics teams, alerts are broadcast in English, Spanish, and Bosnian, and all data publishes to an open dashboard. By month 24 we expect median neighborhood flood-alert lead time to rise from 38 to at least 90 minutes, measured against National Weather Service gauge records.',
   'nvidia/Llama-3_1-Nemotron-Ultra-253B-v1', 1387, 'done', now() - interval '2 hours', now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000032', '00000000-0000-4000-8000-000000000002', 2,
   'Statement of Need',
   E'## Statement of Need\n\nCedar Falls sits at the confluence of the Cedar River and Dry Run Creek, and the neighborhoods east of Main Street flood, on average, once every three years. FEMA''s National Risk Index rates Black Hawk County''s riverine-flood risk in the 92nd percentile nationally [1], yet county alerting depends on a single upstream gauge, giving low-lying blocks as little as 38 minutes of warning during flash events [3].\n\nThe burden is not evenly shared. Census tract 153.02, where 61% of residents are renters and 34% lack a vehicle, recorded 14 of the county''s 21 water-rescue calls in the 2024 flood season [3]. Renters are systematically excluded from property-level mitigation incentives.\n\nCommunity-operated sensing closes this gap: volunteer gauge networks have been shown to extend actionable lead time by 45–90 minutes — enough to move people, medications, and documents [2]. Riverbend''s trusted-neighbor messenger model, proven during the 2024 response, is the delivery mechanism those extra minutes require.',
   'nvidia/Llama-3_1-Nemotron-Ultra-253B-v1', 2043, 'done', now() - interval '2 hours', now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000033', '00000000-0000-4000-8000-000000000002', 3,
   'Project Design and Methodology',
   E'## Project Design and Methodology\n\n**Phase 1 (months 1–6) — Build.** Resident advisory board selects 40 sensor sites from county stormwater models; high-school robotics teams assemble open-hardware gauges (±2 cm accuracy) and install them with city public-works support. All readings stream to an open MQTT broker and public dashboard.\n\n**Phase 2 (months 4–14) — Train.** Sixty residents complete a 6-hour flood-warden curriculum (data literacy, door-to-door warning, shelter logistics) in English, Spanish, and Bosnian. Each block team runs two timed drills against live high-water events.\n\n**Phase 3 (months 10–24) — Institutionalize.** Riverbend and county emergency management co-author a data-driven evacuation playbook for the Route 955 corridor, exercising it in a full-scale tabletop with schools, the food bank, and the transit authority. Quarterly community data reviews keep the network resident-governed.',
   'nvidia/Llama-3_1-Nemotron-Ultra-253B-v1', 1926, 'done', now() - interval '2 hours', now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000034', '00000000-0000-4000-8000-000000000002', 4,
   'Evaluation Plan', '', null, 0, 'pending', now() - interval '2 hours', now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000035', '00000000-0000-4000-8000-000000000002', 5,
   'Budget and Budget Justification', '', null, 0, 'pending', now() - interval '2 hours', now() - interval '2 hours'),
  ('00000000-0000-4000-8000-000000000036', '00000000-0000-4000-8000-000000000002', 6,
   'Organizational Capacity', '', null, 0, 'pending', now() - interval '2 hours', now() - interval '2 hours')
on conflict (id) do nothing;

-- -----------------------------------------------------------------------------
-- Compliance issues (score = 100 − 1·10 − 2·3 = 84; the major issue is already
-- marked resolved — the revise loop fixed it — but the score reflects the audit)
-- -----------------------------------------------------------------------------
insert into public.compliance_issues (id, project_id, section_id, requirement_id, severity, description, suggested_fix, resolved, created_at) values
  ('00000000-0000-4000-8000-000000000041',
   '00000000-0000-4000-8000-000000000002',
   '00000000-0000-4000-8000-000000000034',
   '00000000-0000-4000-8000-000000000016',
   'major',
   'The draft contains no stand-alone Evaluation Plan; CRPG-2026 requires one (max 2 pages) defining measurable outcomes.',
   'Draft an Evaluation Plan section with a baseline, 12- and 24-month targets for alert lead time and warden coverage, data sources (NWS gauges, drill logs), and the UNI evaluation partner''s role; keep within 2 pages.',
   true, now() - interval '118 minutes'),
  ('00000000-0000-4000-8000-000000000042',
   '00000000-0000-4000-8000-000000000002',
   '00000000-0000-4000-8000-000000000032',
   '00000000-0000-4000-8000-000000000015',
   'minor',
   'Statement of Need runs long for the 3-page limit once citations render; the tract-level statistics block would read better as an appendix table.',
   'Tighten the Statement of Need to ≤ 750 words and move the tract statistics block to Appendices as a table.',
   false, now() - interval '118 minutes'),
  ('00000000-0000-4000-8000-000000000043',
   '00000000-0000-4000-8000-000000000002',
   null,
   '00000000-0000-4000-8000-000000000012',
   'minor',
   'Budget Justification does not state an indirect-cost rate; the program permits the 10% de minimis rate.',
   'Add one sentence to the Budget Justification stating that the 10% de minimis indirect rate is applied to modified total direct costs, keeping total costs under the $250,000 ceiling.',
   false, now() - interval '118 minutes')
on conflict (id) do nothing;

-- -----------------------------------------------------------------------------
-- Finished job + its event trace (what the Agent Run console replays)
-- -----------------------------------------------------------------------------
insert into public.jobs (
  id, project_id, kind, status, progress, current_step, runtime,
  started_at, finished_at, created_at, updated_at
) values (
  '00000000-0000-4000-8000-000000000051',
  '00000000-0000-4000-8000-000000000002',
  'full_pipeline', 'succeeded', 100, 'finalize', 'local',
  now() - interval '2 hours', now() - interval '117 minutes',
  now() - interval '2 hours', now() - interval '117 minutes'
) on conflict (id) do nothing;

insert into public.job_events (id, job_id, ts, level, step, message, model_used, tokens_in, tokens_out, latency_ms) values
  ('00000000-0000-4000-8000-000000000061', '00000000-0000-4000-8000-000000000051', now() - interval '120 minutes', 'info',  'extract_requirements', 'Parsed solicitation: 3 pages → 1 chunk (demo fixture)', null, null, null, null),
  ('00000000-0000-4000-8000-000000000062', '00000000-0000-4000-8000-000000000051', now() - interval '119 minutes', 'model', 'extract_requirements', 'Extracted 10 requirements (13 raw → 10 after dedupe)', 'nvidia/Llama-3_1-Nemotron-Nano-8B-v1', 6421, 912, 2431),
  ('00000000-0000-4000-8000-000000000063', '00000000-0000-4000-8000-000000000051', now() - interval '118 minutes', 'model', 'plan_research', 'Planned 3 research queries targeting Statement of Need + Evaluation Plan', 'nvidia/Llama-3_3-Nemotron-Super-49B-v1', 1204, 356, 1877),
  ('00000000-0000-4000-8000-000000000064', '00000000-0000-4000-8000-000000000051', now() - interval '117 minutes', 'tool',  'run_research', 'Tavily advanced search: 3 queries · 18 results · 3 findings kept (concurrency 4)', null, null, null, 6120),
  ('00000000-0000-4000-8000-000000000065', '00000000-0000-4000-8000-000000000051', now() - interval '116 minutes', 'model', 'outline', 'Outlined 6 sections; target 3,850 words derived from the 16-page limit', 'nvidia/Llama-3_3-Nemotron-Super-49B-v1', 2890, 604, 2210),
  ('00000000-0000-4000-8000-000000000066', '00000000-0000-4000-8000-000000000051', now() - interval '112 minutes', 'model', 'draft_sections', 'Drafted "Statement of Need" — 214 words, 3 inline citations', 'nvidia/Llama-3_1-Nemotron-Ultra-253B-v1', 3890, 1150, 21344),
  ('00000000-0000-4000-8000-000000000067', '00000000-0000-4000-8000-000000000051', now() - interval '118 minutes', 'model', 'compliance_audit', 'Audit: 0 blockers · 1 major · 2 minors → compliance score 94/100', 'nvidia/Llama-3_3-Nemotron-Super-49B-v1', 5602, 890, 4301),
  ('00000000-0000-4000-8000-000000000068', '00000000-0000-4000-8000-000000000051', now() - interval '117 minutes', 'info',  'finalize', 'Proposal finalized: 6 sections, 3 references, abstract 112 words', 'nvidia/Llama-3_1-Nemotron-Nano-8B-v1', 4120, 380, 1560)
on conflict (id) do nothing;

commit;
