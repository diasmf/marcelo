-- Radar CABA: private-by-RLS source-availability evidence.
-- Populated only by the authenticated radar-github-ingest Edge Function.
-- No browser/anon clients may query or update this table.
CREATE TABLE IF NOT EXISTS public.radar_caba_source_health (
  url text PRIMARY KEY,
  missing_consecutive integer NOT NULL DEFAULT 0
    CHECK (missing_consecutive >= 0 AND missing_consecutive <= 20),
  first_missing_at timestamptz,
  last_missing_at timestamptz,
  last_checked_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz,
  last_http_status integer
);
ALTER TABLE public.radar_caba_source_health ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.radar_caba_source_health FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.radar_caba_source_health TO service_role;
