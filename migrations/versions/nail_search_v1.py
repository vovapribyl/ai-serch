"""Add immutable nail representations and explicit evaluation score semantics."""

from alembic import op

revision = "0009_nail_search_v1"
down_revision = "0008_gate4_multiphoto_v3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE search_representations (
 id uuid PRIMARY KEY, corpus_version_id integer NOT NULL REFERENCES corpus_versions(id),
 fingerprint char(64) UNIQUE NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$'),
 status text NOT NULL CHECK(status IN ('BUILDING','READY','FAILED')),
 profile jsonb NOT NULL CHECK(jsonb_typeof(profile)='object'),
 inventory_sha256 char(64) NOT NULL CHECK(inventory_sha256 ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
);
CREATE TABLE representation_models (
 representation_id uuid NOT NULL REFERENCES search_representations(id),
 model_key text NOT NULL, revision text NOT NULL CHECK(revision<>''),
 manifest_sha256 char(64) NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
 dimension integer NOT NULL,
 PRIMARY KEY(representation_id,model_key), UNIQUE(representation_id,model_key,dimension),
 CHECK((model_key='openclip_b32' AND dimension=512) OR
       (model_key IN ('dinov2_b14','siglip2_b16_224') AND dimension=768))
);
CREATE TABLE catalog_photos (
 id uuid PRIMARY KEY, representation_id uuid NOT NULL REFERENCES search_representations(id),
 product_record_id integer NOT NULL REFERENCES product_records(id),
 ordinal integer NOT NULL CHECK(ordinal>0),
 input_sha256 char(64) NOT NULL CHECK(input_sha256 ~ '^[0-9a-f]{64}$'),
 source_locator text NOT NULL CHECK(source_locator<>''),
 status text NOT NULL CHECK(status IN ('PENDING','OK','NO_NAILS','ERROR')),
 error_code text,
 UNIQUE(representation_id,product_record_id,ordinal), UNIQUE(id,representation_id),
 CHECK((status IN ('PENDING','OK') AND error_code IS NULL) OR
       (status='NO_NAILS' AND error_code IS NOT NULL AND error_code='DETECTOR_NO_MATCH') OR
       (status='ERROR' AND error_code IS NOT NULL AND error_code<>''))
);
CREATE TABLE nail_regions (
 id uuid PRIMARY KEY, representation_id uuid NOT NULL,
 catalog_photo_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal>0),
 detector_box jsonb NOT NULL CHECK(jsonb_typeof(detector_box)='array' AND jsonb_array_length(detector_box)=4),
 crop_box jsonb NOT NULL CHECK(jsonb_typeof(crop_box)='array' AND jsonb_array_length(crop_box)=4),
 mask_locator text NOT NULL CHECK(mask_locator<>''), crop_locator text NOT NULL CHECK(crop_locator<>''),
 crop_sha256 char(64) NOT NULL CHECK(crop_sha256 ~ '^[0-9a-f]{64}$'),
 FOREIGN KEY(catalog_photo_id,representation_id) REFERENCES catalog_photos(id,representation_id),
 UNIQUE(catalog_photo_id,ordinal), UNIQUE(id,representation_id)
);
CREATE TABLE nail_embeddings (
 representation_id uuid NOT NULL, region_id uuid NOT NULL, model_key text NOT NULL,
 dimension integer NOT NULL CHECK(dimension>0), embedding vector NOT NULL,
 PRIMARY KEY(representation_id,region_id,model_key),
 FOREIGN KEY(region_id,representation_id) REFERENCES nail_regions(id,representation_id),
 FOREIGN KEY(representation_id,model_key,dimension) REFERENCES representation_models(representation_id,model_key,dimension),
 CHECK(vector_dims(embedding)=dimension)
);
CREATE TABLE search_active_representations (
 mode text PRIMARY KEY CHECK(mode='nail-search-v1'),
 representation_id uuid NOT NULL REFERENCES search_representations(id)
);
CREATE INDEX catalog_photos_product ON catalog_photos(representation_id,product_record_id,ordinal);
CREATE INDEX nail_regions_photo ON nail_regions(catalog_photo_id);
CREATE INDEX nail_embeddings_region ON nail_embeddings(region_id);
CREATE INDEX search_representations_corpus ON search_representations(corpus_version_id);

CREATE FUNCTION nail_build_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE state text; rep uuid;
BEGIN
 rep := CASE WHEN TG_OP='DELETE' THEN OLD.representation_id ELSE NEW.representation_id END;
 IF TG_OP='UPDATE' AND OLD.representation_id<>NEW.representation_id THEN
  RAISE EXCEPTION 'Representation ownership is immutable';
 END IF;
 SELECT status INTO state FROM search_representations WHERE id=rep FOR UPDATE;
 IF state IS NULL OR state<>'BUILDING' THEN RAISE EXCEPTION 'Representation is not mutable'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER models_build_guard BEFORE INSERT OR UPDATE OR DELETE ON representation_models FOR EACH ROW EXECUTE FUNCTION nail_build_guard();
CREATE TRIGGER photos_build_guard BEFORE INSERT OR UPDATE OR DELETE ON catalog_photos FOR EACH ROW EXECUTE FUNCTION nail_build_guard();
CREATE TRIGGER regions_build_guard BEFORE INSERT OR UPDATE OR DELETE ON nail_regions FOR EACH ROW EXECUTE FUNCTION nail_build_guard();
CREATE TRIGGER embeddings_build_guard BEFORE INSERT OR UPDATE OR DELETE ON nail_embeddings FOR EACH ROW EXECUTE FUNCTION nail_build_guard();

CREATE FUNCTION nail_photo_corpus_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE product_corpus integer; representation_corpus integer;
BEGIN
 SELECT corpus_version_id INTO product_corpus FROM product_records WHERE id=NEW.product_record_id FOR SHARE;
 SELECT corpus_version_id INTO representation_corpus FROM search_representations WHERE id=NEW.representation_id;
 IF product_corpus IS DISTINCT FROM representation_corpus THEN
  RAISE EXCEPTION 'Catalog photo corpus mismatch';
 END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER photo_corpus_guard AFTER INSERT OR UPDATE ON catalog_photos DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION nail_photo_corpus_guard();

CREATE FUNCTION nail_product_corpus_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.corpus_version_id IS DISTINCT FROM OLD.corpus_version_id AND EXISTS(SELECT 1 FROM catalog_photos WHERE product_record_id=OLD.id) THEN
  RAISE EXCEPTION 'Referenced product corpus is immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER product_nail_corpus_guard BEFORE UPDATE OF corpus_version_id ON product_records FOR EACH ROW EXECUTE FUNCTION nail_product_corpus_guard();

CREATE FUNCTION nail_representation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  IF OLD.status='READY' THEN RAISE EXCEPTION 'Ready representation retention is not authorized'; END IF;
  RETURN OLD;
 END IF;
 IF TG_OP='UPDATE' AND NEW.corpus_version_id IS DISTINCT FROM OLD.corpus_version_id THEN
  RAISE EXCEPTION 'Representation corpus is immutable';
 END IF;
 IF TG_OP='UPDATE' AND OLD.status='READY' AND NEW IS DISTINCT FROM OLD THEN
  RAISE EXCEPTION 'Ready representation is immutable';
 END IF;
 IF NEW.status='READY' AND (TG_OP='INSERT' OR OLD.status<>'READY') THEN
  IF (SELECT count(*) FROM representation_models WHERE representation_id=NEW.id)<>3
   OR EXISTS(SELECT 1 FROM catalog_photos c JOIN product_records p ON p.id=c.product_record_id WHERE c.representation_id=NEW.id AND p.corpus_version_id<>NEW.corpus_version_id)
   OR NOT EXISTS(SELECT 1 FROM catalog_photos WHERE representation_id=NEW.id AND status='OK')
   OR EXISTS(SELECT 1 FROM catalog_photos WHERE representation_id=NEW.id AND status IN ('PENDING','ERROR'))
   OR EXISTS(SELECT 1 FROM catalog_photos p WHERE p.representation_id=NEW.id AND
     ((p.status='OK' AND NOT EXISTS(SELECT 1 FROM nail_regions r WHERE r.catalog_photo_id=p.id)) OR
      (p.status='NO_NAILS' AND EXISTS(SELECT 1 FROM nail_regions r WHERE r.catalog_photo_id=p.id))))
   OR EXISTS(SELECT 1 FROM nail_regions r WHERE r.representation_id=NEW.id AND
     (SELECT count(*) FROM nail_embeddings e WHERE e.region_id=r.id AND e.representation_id=r.representation_id)<>3)
  THEN RAISE EXCEPTION 'Representation is incomplete'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER representation_guard BEFORE INSERT OR UPDATE OR DELETE ON search_representations FOR EACH ROW EXECUTE FUNCTION nail_representation_guard();

CREATE FUNCTION nail_active_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE state text;
BEGIN
 SELECT status INTO state FROM search_representations WHERE id=NEW.representation_id FOR UPDATE;
 IF state IS DISTINCT FROM 'READY' THEN RAISE EXCEPTION 'Active representation must be READY'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER active_guard BEFORE INSERT OR UPDATE ON search_active_representations FOR EACH ROW EXECUTE FUNCTION nail_active_guard();

ALTER TABLE evaluation_candidates ADD COLUMN search_score double precision;
ALTER TABLE evaluation_candidates ADD COLUMN score_kind text;
UPDATE evaluation_candidates SET search_score=rrf_score,score_kind='rrf_v1';
ALTER TABLE evaluation_candidates ALTER COLUMN search_score SET NOT NULL;
ALTER TABLE evaluation_candidates ALTER COLUMN score_kind SET NOT NULL;
ALTER TABLE evaluation_candidates ALTER COLUMN rrf_score DROP NOT NULL;
ALTER TABLE evaluation_candidates ADD CONSTRAINT nail_candidate_score CHECK(
 (score_kind='rrf_v1' AND rrf_score IS NOT NULL) OR
 (score_kind='nail_assignment_mean_v1' AND rrf_score IS NULL AND search_score>=0 AND search_score<=1 AND per_model_ranks::jsonb='{}'::jsonb));
ALTER TABLE evaluation_examples ADD COLUMN search_mode text;
ALTER TABLE evaluation_examples ADD COLUMN representation_id uuid REFERENCES search_representations(id);
UPDATE evaluation_examples SET search_mode='whole-image';
ALTER TABLE evaluation_examples ADD CONSTRAINT nail_example_mode CHECK(
 search_mode IS NOT NULL AND ((search_mode='whole-image' AND representation_id IS NULL) OR
 (search_mode='nail-search-v1' AND representation_id IS NOT NULL)));
ALTER TABLE evaluation_run_snapshots ADD COLUMN search_mode text;
ALTER TABLE evaluation_run_snapshots ADD COLUMN representation_id uuid REFERENCES search_representations(id);
ALTER TABLE evaluation_run_snapshots ADD COLUMN score_kind text;
ALTER TABLE evaluation_run_snapshots ADD COLUMN search_payload jsonb;
ALTER TABLE evaluation_run_snapshots ADD CONSTRAINT nail_snapshot_mode CHECK(
 (search_mode IS NULL AND representation_id IS NULL AND score_kind IS NULL AND search_payload IS NULL) OR
 (search_mode IS NOT NULL AND score_kind IS NOT NULL AND
  ((search_mode='whole-image' AND representation_id IS NULL AND score_kind='rrf_v1' AND search_payload IS NULL) OR
   (search_mode='nail-search-v1' AND representation_id IS NOT NULL AND score_kind='nail_assignment_mean_v1' AND
    search_payload IS NOT NULL AND jsonb_typeof(search_payload)='object' AND
    search_payload->'schema_version' IS NOT NULL AND search_payload->'schema_version'='1'::jsonb))));

CREATE FUNCTION nail_evidence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE example evaluation_examples%ROWTYPE; rep search_representations%ROWTYPE;
BEGIN
 IF TG_TABLE_NAME='evaluation_run_snapshots' THEN
  IF NEW.search_mode IS NULL THEN
   IF TG_OP='INSERT' THEN RAISE EXCEPTION 'New snapshot mode is required'; END IF;
   IF OLD.search_mode IS NOT NULL THEN RAISE EXCEPTION 'Cannot impersonate historical snapshot'; END IF;
  END IF;
 END IF;
 IF TG_TABLE_NAME='evaluation_examples' THEN example:=NEW;
 ELSE SELECT * INTO example FROM evaluation_examples WHERE id=NEW.evaluation_example_id; END IF;
 IF example.search_mode='nail-search-v1' THEN
  SELECT * INTO rep FROM search_representations WHERE id=example.representation_id FOR UPDATE;
  IF rep.status IS DISTINCT FROM 'READY' OR rep.corpus_version_id<>example.corpus_version_id THEN RAISE EXCEPTION 'Evidence representation mismatch'; END IF;
 END IF;
 IF TG_TABLE_NAME='evaluation_candidates' THEN
  IF NEW.score_kind IS DISTINCT FROM (CASE WHEN example.search_mode='nail-search-v1' THEN 'nail_assignment_mean_v1' ELSE 'rrf_v1' END) THEN RAISE EXCEPTION 'Candidate mode mismatch'; END IF;
 ELSIF TG_TABLE_NAME='evaluation_run_snapshots' AND NEW.search_mode IS NOT NULL THEN
  IF NEW.search_mode IS DISTINCT FROM example.search_mode OR NEW.representation_id IS DISTINCT FROM example.representation_id THEN RAISE EXCEPTION 'Snapshot mode mismatch'; END IF;
 END IF;
 IF TG_TABLE_NAME='evaluation_examples' AND TG_OP='UPDATE' THEN
  IF EXISTS(SELECT 1 FROM evaluation_candidates c WHERE c.evaluation_example_id=NEW.id AND c.score_kind IS DISTINCT FROM (CASE WHEN NEW.search_mode='nail-search-v1' THEN 'nail_assignment_mean_v1' ELSE 'rrf_v1' END))
   OR EXISTS(SELECT 1 FROM evaluation_run_snapshots s WHERE s.evaluation_example_id=NEW.id AND s.search_mode IS NOT NULL AND (s.search_mode IS DISTINCT FROM NEW.search_mode OR s.representation_id IS DISTINCT FROM NEW.representation_id))
  THEN RAISE EXCEPTION 'Referenced evidence mismatch'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER example_evidence_guard AFTER INSERT OR UPDATE ON evaluation_examples DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION nail_evidence_guard();
CREATE CONSTRAINT TRIGGER candidate_evidence_guard AFTER INSERT OR UPDATE ON evaluation_candidates DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION nail_evidence_guard();
CREATE CONSTRAINT TRIGGER snapshot_evidence_guard AFTER INSERT OR UPDATE ON evaluation_run_snapshots DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION nail_evidence_guard();
""")


def downgrade():
    op.execute("""
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM search_representations) OR EXISTS(SELECT 1 FROM search_active_representations)
 OR EXISTS(SELECT 1 FROM evaluation_examples WHERE search_mode='nail-search-v1')
 OR EXISTS(SELECT 1 FROM evaluation_candidates WHERE score_kind='nail_assignment_mean_v1')
 OR EXISTS(SELECT 1 FROM evaluation_run_snapshots WHERE search_mode='nail-search-v1')
 THEN RAISE EXCEPTION 'Cannot downgrade nail schema with representations or evidence'; END IF;
END $$;
DROP TRIGGER example_evidence_guard ON evaluation_examples;
DROP TRIGGER candidate_evidence_guard ON evaluation_candidates;
DROP TRIGGER snapshot_evidence_guard ON evaluation_run_snapshots;
DROP FUNCTION nail_evidence_guard();
ALTER TABLE evaluation_run_snapshots DROP CONSTRAINT nail_snapshot_mode;
ALTER TABLE evaluation_run_snapshots DROP COLUMN search_mode, DROP COLUMN representation_id, DROP COLUMN score_kind, DROP COLUMN search_payload;
ALTER TABLE evaluation_examples DROP CONSTRAINT nail_example_mode;
ALTER TABLE evaluation_examples DROP COLUMN search_mode, DROP COLUMN representation_id;
ALTER TABLE evaluation_candidates DROP CONSTRAINT nail_candidate_score;
ALTER TABLE evaluation_candidates DROP COLUMN search_score, DROP COLUMN score_kind;
ALTER TABLE evaluation_candidates ALTER COLUMN rrf_score SET NOT NULL;
DROP TABLE search_active_representations;
DROP TABLE nail_embeddings;
DROP TABLE nail_regions;
DROP TABLE catalog_photos;
DROP TABLE representation_models;
DROP TABLE search_representations;
DROP FUNCTION nail_active_guard();
DROP FUNCTION nail_representation_guard();
DROP FUNCTION nail_photo_corpus_guard();
DROP TRIGGER product_nail_corpus_guard ON product_records;
DROP FUNCTION nail_product_corpus_guard();
DROP FUNCTION nail_build_guard();
""")
