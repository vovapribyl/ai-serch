import os
from uuid import uuid4

import psycopg
import pytest

from tests.support.nail_db import BASE, disposable_database, migrate

TABLES = (
    "search_representations",
    "representation_models",
    "catalog_photos",
    "nail_regions",
    "nail_embeddings",
    "search_active_representations",
)


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    if os.environ.get("CANDIDATE_I_SYNTHETIC_DB_TESTS") != "yes":
        pytest.skip("Explicit owned synthetic DB test runner required")
    with disposable_database(tmp_path_factory.mktemp("nail-db")) as (config, marker):
        result = migrate(config, marker, "upgrade", BASE)
        assert result.returncode == 0, result.stderr
        result = migrate(config, marker, "upgrade", "head")
        assert result.returncode == 0, result.stderr
        yield config, marker


@pytest.fixture
def conn(database):
    config, marker = database
    with psycopg.connect(**config) as connection:
        assert connection.execute("SELECT marker FROM synthetic_owner_marker").fetchone() == (
            marker,
        )
        yield connection
        connection.rollback()


def schema(conn):
    found = {
        row[0] for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    }
    assert set(TABLES) <= found


def seed(conn):
    schema(conn)
    corpus = conn.execute(
        "INSERT INTO corpus_versions(snapshot_name,is_active,operation_id) VALUES ('synthetic',false,'11111111111111111111111111111111') RETURNING id"
    ).fetchone()[0]
    product = conn.execute(
        "INSERT INTO product_records(corpus_version_id,product_id,source_row,category,image_path,image_sha256,image_format) VALUES (%s,'fake',1,'fake','private/fake','0000000000000000000000000000000000000000000000000000000000000000','PNG') RETURNING id",
        (corpus,),
    ).fetchone()[0]
    rep = uuid4()
    conn.execute(
        "INSERT INTO search_representations(id,corpus_version_id,fingerprint,status,profile,inventory_sha256,created_at,updated_at) VALUES (%s,%s,%s,'BUILDING','{}',%s,now(),now())",
        (rep, corpus, "a" * 64, "b" * 64),
    )
    return corpus, product, rep


def test_six_tables_have_no_implicit_nullable_ownership(conn):
    schema(conn)
    nullable = conn.execute(
        "SELECT table_name,column_name FROM information_schema.columns WHERE table_name=ANY(%s) AND is_nullable='YES'",
        (list(TABLES),),
    ).fetchall()
    assert nullable == [("catalog_photos", "error_code")]


@pytest.mark.parametrize(
    "column,value",
    [("fingerprint", None), ("inventory_sha256", None), ("profile", None), ("status", "BOGUS")],
)
def test_representation_mandatory_and_status_constraints(conn, column, value):
    _, _, rep = seed(conn)
    with pytest.raises(psycopg.Error), conn.transaction():
        conn.execute(f"UPDATE search_representations SET {column}=%s WHERE id=%s", (value, rep))


def test_catalog_photo_corpus_ownership(conn):
    _, product, rep = seed(conn)
    other = conn.execute(
        "INSERT INTO corpus_versions(snapshot_name,is_active,operation_id) VALUES ('other',false,'22222222222222222222222222222222') RETURNING id"
    ).fetchone()[0]
    conn.execute("UPDATE product_records SET corpus_version_id=%s WHERE id=%s", (other, product))
    with pytest.raises(psycopg.Error), conn.transaction():
        conn.execute(
            "INSERT INTO catalog_photos(id,representation_id,product_record_id,ordinal,input_sha256,source_locator,status) VALUES (%s,%s,%s,1,%s,'fake','PENDING')",
            (uuid4(), rep, product, "c" * 64),
        )


def test_empty_representation_cannot_be_ready_or_active(conn):
    _, _, rep = seed(conn)
    with pytest.raises(psycopg.Error), conn.transaction():
        conn.execute("UPDATE search_representations SET status='READY' WHERE id=%s", (rep,))
    with pytest.raises(psycopg.Error), conn.transaction():
        conn.execute(
            "INSERT INTO search_active_representations(mode,representation_id) VALUES ('nail-search-v1',%s)",
            (rep,),
        )


def test_model_dimension_identity(conn):
    _, _, rep = seed(conn)
    with pytest.raises(psycopg.Error), conn.transaction():
        conn.execute(
            "INSERT INTO representation_models VALUES (%s,'openclip_b32','r',%s,768)",
            (rep, "d" * 64),
        )


def test_empty_upgrade_downgrade_upgrade(database):
    config, marker = database
    result = migrate(config, marker, "downgrade", BASE)
    assert result.returncode == 0, result.stderr
    with psycopg.connect(**config) as connection:
        assert (
            connection.execute("SELECT to_regclass('public.search_representations')").fetchone()[0]
            is None
        )
    result = migrate(config, marker, "upgrade", "head")
    assert result.returncode == 0, result.stderr


def test_populated_downgrade_refuses_and_keeps_representation(database):
    config, marker = database
    with psycopg.connect(**config) as connection:
        _, _, rep = seed(connection)
    try:
        result = migrate(config, marker, "downgrade", BASE)
        assert result.returncode != 0
        with psycopg.connect(**config) as connection:
            assert connection.execute(
                "SELECT id FROM search_representations WHERE id=%s", (rep,)
            ).fetchone() == (rep,)
    finally:
        with psycopg.connect(**config) as connection:
            connection.execute("DELETE FROM search_representations WHERE id=%s", (rep,))
            connection.execute("DELETE FROM product_records WHERE product_id='fake'")
            connection.execute("DELETE FROM corpus_versions WHERE snapshot_name='synthetic'")


def ready_seed(conn):
    corpus, product, rep = seed(conn)
    photo, region = uuid4(), uuid4()
    conn.execute(
        "INSERT INTO catalog_photos(id,representation_id,product_record_id,ordinal,input_sha256,source_locator,status) VALUES (%s,%s,%s,1,%s,'fake','OK')",
        (photo, rep, product, "c" * 64),
    )
    conn.execute(
        "INSERT INTO nail_regions VALUES (%s,%s,%s,1,'[0,0,1,1]','[0,0,1,1]','mask','crop',%s)",
        (region, rep, photo, "d" * 64),
    )
    for key, dimension in [("openclip_b32", 512), ("dinov2_b14", 768), ("siglip2_b16_224", 768)]:
        conn.execute(
            "INSERT INTO representation_models VALUES (%s,%s,%s,%s,%s)",
            (rep, key, "r", "e" * 64, dimension),
        )
        vector = "[" + ",".join(["1"] + ["0"] * (dimension - 1)) + "]"
        conn.execute(
            "INSERT INTO nail_embeddings VALUES (%s,%s,%s,%s,%s::vector)",
            (rep, region, key, dimension, vector),
        )
    conn.execute("UPDATE search_representations SET status='READY' WHERE id=%s", (rep,))
    return corpus, product, rep, photo, region


def example_seed(conn, corpus, rep):
    example = uuid4()
    conn.execute(
        "INSERT INTO evaluation_examples(id,query_path,query_sha256,created_at,expires_at,corpus_version_id,model_keys,search_duration_ms,label_state,search_mode,representation_id) VALUES (%s,'fake',%s,now(),now()+interval '1 day',%s,'[]',1,'PENDING','nail-search-v1',%s)",
        (example, "a" * 64, corpus, rep),
    )
    return example


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE search_representations SET profile='{}'::jsonb || '{\"changed\":true}'::jsonb WHERE id=%s",
        "UPDATE representation_models SET revision='changed' WHERE representation_id=%s",
        "UPDATE catalog_photos SET ordinal=2 WHERE representation_id=%s",
        "DELETE FROM nail_regions WHERE representation_id=%s",
        "DELETE FROM nail_embeddings WHERE representation_id=%s",
        "DELETE FROM search_representations WHERE id=%s",
    ],
)
def test_ready_content_cannot_mutate_or_delete(conn, statement):
    _, _, rep, _, _ = ready_seed(conn)
    with pytest.raises(psycopg.Error), conn.transaction():
        conn.execute(statement, (rep,))


@pytest.mark.parametrize("payload", [None, '{"schema_version":"1"}', '{"schema_version":2}', "[]"])
def test_nail_snapshot_version_is_required_numeric_one(conn, payload):
    corpus, _, rep, _, _ = ready_seed(conn)
    example = example_seed(conn, corpus, rep)
    with pytest.raises(psycopg.Error), conn.transaction():
        conn.execute(
            "INSERT INTO evaluation_run_snapshots(evaluation_example_id,run_ordinal,model_revisions,photo_model_results,search_mode,representation_id,score_kind,search_payload) VALUES (%s,1,'{}','{}','nail-search-v1',%s,'nail_assignment_mean_v1',%s::jsonb)",
            (example, rep, payload),
        )


def test_new_snapshot_cannot_impersonate_historical_null_mode(conn):
    corpus, _, rep, _, _ = ready_seed(conn)
    example = example_seed(conn, corpus, rep)
    with pytest.raises(psycopg.Error), conn.transaction():
        conn.execute(
            "INSERT INTO evaluation_run_snapshots(evaluation_example_id,run_ordinal,model_revisions,photo_model_results) VALUES (%s,1,'{}','{}')",
            (example,),
        )


def test_snapshot_consistency_and_parent_update_preserve_evidence(conn):
    corpus, _, rep, _, _ = ready_seed(conn)
    example = example_seed(conn, corpus, rep)
    conn.execute(
        "INSERT INTO evaluation_run_snapshots(evaluation_example_id,run_ordinal,model_revisions,photo_model_results,search_mode,representation_id,score_kind,search_payload) VALUES (%s,1,'{}','{}','nail-search-v1',%s,'nail_assignment_mean_v1','{\"schema_version\":1}')",
        (example, rep),
    )
    with pytest.raises(psycopg.Error), conn.transaction():
        conn.execute(
            "UPDATE evaluation_examples SET search_mode='whole-image',representation_id=NULL WHERE id=%s",
            (example,),
        )
    with pytest.raises(psycopg.Error), conn.transaction():
        conn.execute(
            "UPDATE evaluation_run_snapshots SET search_mode=NULL,representation_id=NULL,score_kind=NULL,search_payload=NULL WHERE evaluation_example_id=%s",
            (example,),
        )


def test_nail_candidate_has_no_fake_legacy_ranks(conn):
    corpus, product, rep, _, _ = ready_seed(conn)
    example = example_seed(conn, corpus, rep)
    with pytest.raises(psycopg.Error), conn.transaction():
        conn.execute(
            "INSERT INTO evaluation_candidates(evaluation_example_id,product_record_id,fused_rank,rrf_score,per_model_ranks,per_model_raw_scores,search_score,score_kind) VALUES (%s,%s,1,NULL,'{\"openclip_b32\":1}','{}',.8,'nail_assignment_mean_v1')",
            (example, product),
        )


def test_valid_nail_evidence_writes_explicit_score_without_rrf(conn):
    corpus, product, rep, _, _ = ready_seed(conn)
    example = example_seed(conn, corpus, rep)
    conn.execute(
        "INSERT INTO evaluation_candidates(evaluation_example_id,product_record_id,fused_rank,rrf_score,per_model_ranks,per_model_raw_scores,search_score,score_kind) VALUES (%s,%s,1,NULL,'{}','{}',.8,'nail_assignment_mean_v1')",
        (example, product),
    )
    assert conn.execute(
        "SELECT rrf_score,search_score,score_kind FROM evaluation_candidates WHERE evaluation_example_id=%s",
        (example,),
    ).fetchone() == (None, 0.8, "nail_assignment_mean_v1")


def test_legacy_rrf_backfill_keeps_historical_snapshot(database):
    config, marker = database
    assert migrate(config, marker, "downgrade", BASE).returncode == 0
    example = uuid4()
    with psycopg.connect(**config) as connection:
        corpus = connection.execute(
            "INSERT INTO corpus_versions(snapshot_name,is_active,operation_id) VALUES ('legacy-fake',false,'33333333333333333333333333333333') RETURNING id"
        ).fetchone()[0]
        product = connection.execute(
            "INSERT INTO product_records(corpus_version_id,product_id,source_row,category,image_path,image_sha256,image_format) VALUES (%s,'legacy-fake',1,'fake','private/fake',%s,'PNG') RETURNING id",
            (corpus, "0" * 64),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO evaluation_examples(id,query_path,query_sha256,created_at,expires_at,corpus_version_id,model_keys,search_duration_ms,label_state) VALUES (%s,'fake',%s,now(),now()+interval '1 day',%s,'[]',1,'PENDING')",
            (example, "a" * 64, corpus),
        )
        connection.execute(
            "INSERT INTO evaluation_candidates(evaluation_example_id,product_record_id,fused_rank,rrf_score,per_model_ranks,per_model_raw_scores) VALUES (%s,%s,1,.123,'{}','{}')",
            (example, product),
        )
        connection.execute(
            "INSERT INTO evaluation_run_snapshots(evaluation_example_id,run_ordinal,model_revisions,photo_model_results) VALUES (%s,1,'{}','{}')",
            (example,),
        )
    result = migrate(config, marker, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    with psycopg.connect(**config) as connection:
        assert connection.execute(
            "SELECT rrf_score,search_score,score_kind FROM evaluation_candidates WHERE evaluation_example_id=%s",
            (example,),
        ).fetchone() == (0.123, 0.123, "rrf_v1")
        assert connection.execute(
            "SELECT search_mode,representation_id FROM evaluation_examples WHERE id=%s", (example,)
        ).fetchone() == ("whole-image", None)
        assert connection.execute(
            "SELECT search_mode,score_kind,search_payload FROM evaluation_run_snapshots WHERE evaluation_example_id=%s",
            (example,),
        ).fetchone() == (None, None, None)
        connection.execute("DELETE FROM evaluation_examples WHERE id=%s", (example,))
        connection.execute("DELETE FROM product_records WHERE id=%s", (product,))
        connection.execute("DELETE FROM corpus_versions WHERE id=%s", (corpus,))


@pytest.mark.parametrize(
    "parent,ready", [("product", False), ("representation", False), ("product", True)]
)
def test_referenced_corpus_parent_cannot_change(parent, ready, conn):
    if ready:
        _, product, rep, _, _ = ready_seed(conn)
    else:
        _, product, rep = seed(conn)
        conn.execute(
            "INSERT INTO catalog_photos(id,representation_id,product_record_id,ordinal,input_sha256,source_locator,status) VALUES (%s,%s,%s,1,%s,'fake','PENDING')",
            (uuid4(), rep, product, "c" * 64),
        )
    other = conn.execute(
        "INSERT INTO corpus_versions(snapshot_name,is_active,operation_id) VALUES ('parent-change',false,%s) RETURNING id",
        (uuid4().hex,),
    ).fetchone()[0]
    with pytest.raises(psycopg.Error), conn.transaction():
        if parent == "product":
            conn.execute(
                "UPDATE product_records SET corpus_version_id=%s WHERE id=%s", (other, product)
            )
        else:
            conn.execute(
                "UPDATE search_representations SET corpus_version_id=%s WHERE id=%s", (other, rep)
            )
    assert (
        conn.execute(
            "SELECT p.corpus_version_id=r.corpus_version_id FROM product_records p JOIN catalog_photos c ON c.product_record_id=p.id JOIN search_representations r ON r.id=c.representation_id WHERE r.id=%s",
            (rep,),
        ).fetchone()[0]
        is True
    )
