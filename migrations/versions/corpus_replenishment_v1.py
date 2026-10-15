"""Durable progress and immutable catalog revisions; legacy semantics stay separate."""

from alembic import op

revision = "0010_corpus_replenishment_v1"
down_revision = "0009_nail_search_v1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE replenishment_owner (
 singleton_key text PRIMARY KEY CHECK(singleton_key='local'),
 epoch bigint NOT NULL CHECK(epoch>=0), owner_token uuid,
 mode text NOT NULL CHECK(mode IN ('SEARCH','DRAINING','BUILD','RECOVERY_REQUIRED')),
 version bigint NOT NULL CHECK(version>=0), updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO replenishment_owner VALUES ('local',0,NULL,'RECOVERY_REQUIRED',0,now());
CREATE TABLE replenishment_runs (
 id uuid PRIMARY KEY, package_sha char(64) NOT NULL CHECK(package_sha ~ '^[0-9a-f]{64}$'),
 owner_token uuid NOT NULL, epoch bigint NOT NULL CHECK(epoch>0),
 status text NOT NULL CHECK(status IN ('RUNNING','STOPPED','EXPIRED','INTERRUPTED','COMPLETED','FAILED')),
 inventory_bound boolean NOT NULL DEFAULT false,
 selected_photo_ids uuid[] NOT NULL DEFAULT '{}', revision_ids uuid[] NOT NULL DEFAULT '{}',
 CHECK(cardinality(selected_photo_ids)<=5),
 reason text, started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 UNIQUE(id,epoch)
);
CREATE TABLE processing_profiles (
 semantic_profile_sha char(64) PRIMARY KEY CHECK(semantic_profile_sha ~ '^[0-9a-f]{64}$'),
 schema_version integer NOT NULL CHECK(schema_version=1),
 canonical_payload jsonb NOT NULL CHECK(jsonb_typeof(canonical_payload)='object')
);
CREATE TABLE product_revisions (
 id uuid PRIMARY KEY, corpus_version_id integer NOT NULL REFERENCES corpus_versions(id),
 product_record_id integer NOT NULL REFERENCES product_records(id),
 input_set_sha char(64) NOT NULL CHECK(input_set_sha ~ '^[0-9a-f]{64}$'),
 semantic_profile_sha char(64) NOT NULL REFERENCES processing_profiles(semantic_profile_sha),
 version bigint NOT NULL CHECK(version>0),
 state text NOT NULL CHECK(state IN ('OPEN','PREPARED','READY','NOT_PUBLISHABLE')),
 UNIQUE(id,corpus_version_id,product_record_id), UNIQUE(id,product_record_id)
);
CREATE TABLE replenishment_product_heads (
 corpus_version_id integer NOT NULL REFERENCES corpus_versions(id),
 product_record_id integer NOT NULL REFERENCES product_records(id),
 current_revision_id uuid, version bigint NOT NULL CHECK(version>=0),
 PRIMARY KEY(corpus_version_id,product_record_id),
 FOREIGN KEY(current_revision_id,corpus_version_id,product_record_id)
  REFERENCES product_revisions(id,corpus_version_id,product_record_id)
);
CREATE TABLE revision_photos (
 id uuid PRIMARY KEY, revision_id uuid NOT NULL REFERENCES product_revisions(id),
 ordinal integer NOT NULL CHECK(ordinal>0), source_ref text NOT NULL CHECK(source_ref<>''),
 input_sha char(64) NOT NULL CHECK(input_sha ~ '^[0-9a-f]{64}$'),
 source_bytes bigint NOT NULL CHECK(source_bytes>0),
 outcome text NOT NULL CHECK(outcome IN ('PENDING','RUNNING','OK','NO_NAILS','ERROR')),
 error_code text, reused_from uuid REFERENCES revision_photos(id),
 UNIQUE(revision_id,ordinal), UNIQUE(id,revision_id),
 CHECK((outcome='ERROR' AND error_code IS NOT NULL AND error_code<>'') OR
       (outcome<>'ERROR' AND error_code IS NULL))
);
CREATE TABLE stage_attempts (
 id uuid PRIMARY KEY, photo_id uuid NOT NULL REFERENCES revision_photos(id),
 stage_key text NOT NULL, model_key text NOT NULL,
 run_id uuid NOT NULL, epoch bigint NOT NULL,
 state text NOT NULL CHECK(state IN ('PENDING','RUNNING','COMPLETE','ERROR','INTERRUPTED')),
 attempt_no integer NOT NULL CHECK(attempt_no>0), version bigint NOT NULL CHECK(version>0),
 identity_sha char(64) NOT NULL CHECK(identity_sha ~ '^[0-9a-f]{64}$'),
 UNIQUE(photo_id,stage_key,model_key,attempt_no),
 FOREIGN KEY(run_id,epoch) REFERENCES replenishment_runs(id,epoch),
 CHECK((stage_key='localization' AND model_key='') OR
       (stage_key='embedding' AND model_key IN ('openclip_b32','dinov2_b14','siglip2_b16_224')))
);
CREATE UNIQUE INDEX stage_complete_once ON stage_attempts(photo_id,stage_key,model_key) WHERE state='COMPLETE';
CREATE TABLE stage_checkpoints (
 attempt_id uuid PRIMARY KEY REFERENCES stage_attempts(id),
 identity_sha char(64) NOT NULL CHECK(identity_sha ~ '^[0-9a-f]{64}$'),
 manifest_ref text NOT NULL CHECK(manifest_ref<>''),
 manifest_sha char(64) NOT NULL CHECK(manifest_sha ~ '^[0-9a-f]{64}$'),
 profile_sha char(64) NOT NULL REFERENCES processing_profiles(semantic_profile_sha),
 region_count integer NOT NULL CHECK(region_count>=0), completed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE revision_regions (
 revision_photo_id uuid NOT NULL REFERENCES revision_photos(id),
 region_ordinal integer NOT NULL CHECK(region_ordinal>0),
 mask_ref text NOT NULL CHECK(mask_ref<>''), crop_ref text NOT NULL CHECK(crop_ref<>''),
 crop_sha char(64) NOT NULL CHECK(crop_sha ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(revision_photo_id,region_ordinal)
);
CREATE TABLE revision_vectors (
 revision_photo_id uuid NOT NULL, region_ordinal integer NOT NULL, model_key text NOT NULL,
 vector vector NOT NULL, PRIMARY KEY(revision_photo_id,region_ordinal,model_key),
 FOREIGN KEY(revision_photo_id,region_ordinal) REFERENCES revision_regions(revision_photo_id,region_ordinal),
 CHECK((model_key='openclip_b32' AND vector_dims(vector)=512) OR
       (model_key IN ('dinov2_b14','siglip2_b16_224') AND vector_dims(vector)=768))
);
CREATE TABLE catalog_snapshots (
 id uuid PRIMARY KEY, semantic_profile_sha char(64) NOT NULL REFERENCES processing_profiles(semantic_profile_sha),
 content_sha char(64) NOT NULL CHECK(content_sha ~ '^[0-9a-f]{64}$'),
 state text NOT NULL CHECK(state IN ('PREPARED','READY'))
);
CREATE TABLE catalog_snapshot_members (
 snapshot_id uuid NOT NULL REFERENCES catalog_snapshots(id),
 product_record_id integer NOT NULL, revision_id uuid NOT NULL,
 PRIMARY KEY(snapshot_id,product_record_id),
 FOREIGN KEY(revision_id,product_record_id) REFERENCES product_revisions(id,product_record_id)
);
CREATE TABLE active_catalog_snapshots (
 mode_key text PRIMARY KEY CHECK(mode_key='nail-search-v1'),
 snapshot_id uuid NOT NULL REFERENCES catalog_snapshots(id), version bigint NOT NULL CHECK(version>0)
);
CREATE TABLE publication_attempts (
 id uuid PRIMARY KEY, revision_id uuid NOT NULL REFERENCES product_revisions(id),
 run_id uuid NOT NULL, epoch bigint NOT NULL, expected_active uuid REFERENCES catalog_snapshots(id),
 state text NOT NULL CHECK(state IN ('RUNNING','SUCCEEDED','FAILED','UNKNOWN')),
 error_code text, receipt_id uuid, FOREIGN KEY(run_id,epoch) REFERENCES replenishment_runs(id,epoch)
);
CREATE TABLE revision_publications (
 revision_id uuid PRIMARY KEY REFERENCES product_revisions(id),
 snapshot_id uuid NOT NULL REFERENCES catalog_snapshots(id),
 run_id uuid NOT NULL REFERENCES replenishment_runs(id), published_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX replenishment_photo_queue ON revision_photos(revision_id,outcome,ordinal);
CREATE INDEX replenishment_attempt_photo ON stage_attempts(photo_id,stage_key,model_key);
CREATE INDEX replenishment_publication_revision ON publication_attempts(revision_id);

CREATE FUNCTION replenishment_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME IN ('processing_profiles','stage_checkpoints','revision_publications') THEN
  RAISE EXCEPTION 'IMMUTABLE_RESULT' USING ERRCODE='23514';
 ELSIF TG_TABLE_NAME IN ('product_revisions','catalog_snapshots') THEN
  IF OLD.state='READY' THEN RAISE EXCEPTION 'IMMUTABLE_RESULT' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='stage_attempts' THEN
  IF OLD.state='COMPLETE' THEN RAISE EXCEPTION 'IMMUTABLE_RESULT' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_profiles BEFORE UPDATE OR DELETE ON processing_profiles FOR EACH ROW EXECUTE FUNCTION replenishment_immutable();
CREATE TRIGGER immutable_revisions BEFORE UPDATE OR DELETE ON product_revisions FOR EACH ROW EXECUTE FUNCTION replenishment_immutable();
CREATE TRIGGER immutable_snapshots BEFORE UPDATE OR DELETE ON catalog_snapshots FOR EACH ROW EXECUTE FUNCTION replenishment_immutable();
CREATE TRIGGER immutable_attempts BEFORE UPDATE OR DELETE ON stage_attempts FOR EACH ROW EXECUTE FUNCTION replenishment_immutable();
CREATE TRIGGER immutable_checkpoints BEFORE UPDATE OR DELETE ON stage_checkpoints FOR EACH ROW EXECUTE FUNCTION replenishment_immutable();
CREATE TRIGGER immutable_publications BEFORE UPDATE OR DELETE ON revision_publications FOR EACH ROW EXECUTE FUNCTION replenishment_immutable();

CREATE FUNCTION replenishment_run_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.id,NEW.package_sha,NEW.owner_token,NEW.epoch,NEW.started_at)
    IS DISTINCT FROM (OLD.id,OLD.package_sha,OLD.owner_token,OLD.epoch,OLD.started_at) THEN
  RAISE EXCEPTION 'RUN_PACKAGE_IMMUTABLE' USING ERRCODE='23514';
 END IF;
 IF OLD.inventory_bound AND (NEW.inventory_bound,NEW.selected_photo_ids,NEW.revision_ids)
    IS DISTINCT FROM (OLD.inventory_bound,OLD.selected_photo_ids,OLD.revision_ids) THEN
  RAISE EXCEPTION 'RUN_SELECTION_IMMUTABLE' USING ERRCODE='23514';
 END IF;
 IF OLD.status<>'RUNNING' AND NEW.status<>OLD.status THEN
  RAISE EXCEPTION 'RUN_TERMINAL' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_run BEFORE UPDATE ON replenishment_runs FOR EACH ROW EXECUTE FUNCTION replenishment_run_guard();

CREATE FUNCTION replenishment_attempt_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' THEN
  IF (NEW.id,NEW.photo_id,NEW.stage_key,NEW.model_key,NEW.run_id,NEW.epoch,NEW.attempt_no,NEW.identity_sha)
     IS DISTINCT FROM (OLD.id,OLD.photo_id,OLD.stage_key,OLD.model_key,OLD.run_id,OLD.epoch,OLD.attempt_no,OLD.identity_sha) THEN
   RAISE EXCEPTION 'ATTEMPT_IDENTITY_IMMUTABLE' USING ERRCODE='23514';
  END IF;
  IF NEW.version<>OLD.version+1 OR NOT (
      (OLD.state='PENDING' AND NEW.state='RUNNING') OR
      (OLD.state='RUNNING' AND NEW.state IN ('COMPLETE','ERROR','INTERRUPTED'))) THEN
   RAISE EXCEPTION 'INVALID_STAGE_TRANSITION' USING ERRCODE='23514';
  END IF;
 END IF;
 IF NEW.state='COMPLETE' AND NOT EXISTS(
    SELECT 1 FROM stage_checkpoints c JOIN revision_photos p ON p.id=NEW.photo_id
    JOIN product_revisions r ON r.id=p.revision_id
    WHERE c.attempt_id=NEW.id AND c.identity_sha=NEW.identity_sha AND c.profile_sha=r.semantic_profile_sha) THEN
  RAISE EXCEPTION 'CHECKPOINT_REQUIRED' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER attempt_transition BEFORE INSERT OR UPDATE ON stage_attempts FOR EACH ROW EXECUTE FUNCTION replenishment_attempt_guard();

CREATE FUNCTION replenishment_revision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM product_records WHERE id=NEW.product_record_id AND corpus_version_id=NEW.corpus_version_id) THEN
  RAISE EXCEPTION 'PRODUCT_CORPUS_MISMATCH' USING ERRCODE='23503';
 END IF;
 IF TG_OP='UPDATE' AND (NEW.id,NEW.corpus_version_id,NEW.product_record_id,NEW.input_set_sha,NEW.semantic_profile_sha)
   IS DISTINCT FROM (OLD.id,OLD.corpus_version_id,OLD.product_record_id,OLD.input_set_sha,OLD.semantic_profile_sha) THEN
  RAISE EXCEPTION 'REVISION_IDENTITY_IMMUTABLE' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER revision_identity BEFORE INSERT OR UPDATE ON product_revisions FOR EACH ROW EXECUTE FUNCTION replenishment_revision_guard();

CREATE FUNCTION replenishment_child_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE data jsonb; photo uuid; ref uuid; parent_state text;
BEGIN
 IF TG_OP='DELETE' THEN data=to_jsonb(OLD); ELSE data=to_jsonb(NEW); END IF;
 IF TG_TABLE_NAME='catalog_snapshot_members' THEN
  SELECT state INTO parent_state FROM catalog_snapshots WHERE id=(data->>'snapshot_id')::uuid;
 ELSE
  IF TG_TABLE_NAME='revision_photos' THEN ref=(data->>'revision_id')::uuid;
  ELSIF TG_TABLE_NAME='stage_checkpoints' THEN
   SELECT photo_id INTO photo FROM stage_attempts WHERE id=(data->>'attempt_id')::uuid;
  ELSIF TG_TABLE_NAME='stage_attempts' THEN photo=(data->>'photo_id')::uuid;
  ELSE photo=(data->>'revision_photo_id')::uuid;
  END IF;
  IF ref IS NULL THEN SELECT revision_id INTO ref FROM revision_photos WHERE id=photo; END IF;
  SELECT state INTO parent_state FROM product_revisions WHERE id=ref;
 END IF;
 IF parent_state='READY' THEN RAISE EXCEPTION 'IMMUTABLE_RESULT' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='revision_photos' THEN
  IF TG_OP='UPDATE' THEN
   IF (NEW.id,NEW.revision_id,NEW.ordinal,NEW.source_ref,NEW.input_sha,NEW.source_bytes,NEW.reused_from)
      IS DISTINCT FROM (OLD.id,OLD.revision_id,OLD.ordinal,OLD.source_ref,OLD.input_sha,OLD.source_bytes,OLD.reused_from) THEN
    RAISE EXCEPTION 'PHOTO_IDENTITY_IMMUTABLE' USING ERRCODE='23514';
   END IF;
  END IF;
  IF TG_OP<>'DELETE' AND NEW.reused_from IS NOT NULL THEN
   IF NOT EXISTS (
     SELECT 1 FROM revision_photos p JOIN product_revisions r ON r.id=p.revision_id
     JOIN product_revisions n ON n.id=NEW.revision_id
     WHERE p.id=NEW.reused_from AND p.reused_from IS NULL
     AND p.outcome IN ('OK','NO_NAILS','ERROR') AND p.outcome=NEW.outcome
     AND (p.ordinal,p.source_ref,p.input_sha,p.source_bytes)=(NEW.ordinal,NEW.source_ref,NEW.input_sha,NEW.source_bytes)
     AND (r.corpus_version_id,r.product_record_id,r.semantic_profile_sha)=(n.corpus_version_id,n.product_record_id,n.semantic_profile_sha)
   ) THEN RAISE EXCEPTION 'REUSE_IDENTITY_CONFLICT' USING ERRCODE='23514'; END IF;
  END IF;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER revision_photo_guard BEFORE INSERT OR UPDATE OR DELETE ON revision_photos FOR EACH ROW EXECUTE FUNCTION replenishment_child_guard();
CREATE TRIGGER revision_attempt_guard BEFORE INSERT OR UPDATE OR DELETE ON stage_attempts FOR EACH ROW EXECUTE FUNCTION replenishment_child_guard();
CREATE TRIGGER revision_checkpoint_guard BEFORE INSERT OR UPDATE OR DELETE ON stage_checkpoints FOR EACH ROW EXECUTE FUNCTION replenishment_child_guard();
CREATE TRIGGER revision_region_guard BEFORE INSERT OR UPDATE OR DELETE ON revision_regions FOR EACH ROW EXECUTE FUNCTION replenishment_child_guard();
CREATE TRIGGER revision_vector_guard BEFORE INSERT OR UPDATE OR DELETE ON revision_vectors FOR EACH ROW EXECUTE FUNCTION replenishment_child_guard();
CREATE TRIGGER snapshot_member_guard BEFORE INSERT OR UPDATE OR DELETE ON catalog_snapshot_members FOR EACH ROW EXECUTE FUNCTION replenishment_child_guard();
""")


def downgrade():
    op.execute("""
DROP TABLE revision_publications,publication_attempts,active_catalog_snapshots,catalog_snapshot_members,
 catalog_snapshots,revision_vectors,revision_regions,stage_checkpoints,stage_attempts,revision_photos,
 replenishment_product_heads,product_revisions,processing_profiles,replenishment_runs,replenishment_owner;
DROP FUNCTION replenishment_child_guard(),replenishment_revision_guard(),replenishment_immutable(),replenishment_run_guard(),replenishment_attempt_guard();
""")
