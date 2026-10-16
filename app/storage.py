import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite_vec


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
 candidate_id TEXT PRIMARY KEY, name TEXT, city TEXT, years_experience REAL, degree TEXT,
 latest_document_id TEXT, latest_uploaded_at TEXT, profile_json TEXT);
CREATE TABLE IF NOT EXISTS source_documents (
 document_id TEXT PRIMARY KEY, candidate_id TEXT, filename TEXT, path TEXT, sha256 TEXT,
 size INTEGER, uploaded_at TEXT, status TEXT, stage TEXT, error TEXT, warnings_json TEXT DEFAULT '[]',
 content_fingerprint TEXT, version_no INTEGER DEFAULT 0, is_active INTEGER DEFAULT 0,
 duplicate_of_document_id TEXT, elapsed REAL DEFAULT 0, metrics_json TEXT DEFAULT '{}');
CREATE INDEX IF NOT EXISTS source_hash ON source_documents(sha256);
CREATE UNIQUE INDEX IF NOT EXISTS one_active ON source_documents(candidate_id) WHERE is_active=1;
CREATE TABLE IF NOT EXISTS candidate_contacts (candidate_id TEXT, type TEXT, value_hash TEXT,
 UNIQUE(candidate_id,type,value_hash));
CREATE TABLE IF NOT EXISTS processing_jobs (job_id INTEGER PRIMARY KEY, document_id TEXT, stage TEXT,
 status TEXT, created_at TEXT, error_json TEXT);
CREATE TABLE IF NOT EXISTS knowledge_documents (knowledge_id TEXT PRIMARY KEY, candidate_id TEXT,
 source_document_id TEXT, version_no INTEGER, clean_text TEXT, status TEXT, is_active INTEGER, artifact_path TEXT);
CREATE TABLE IF NOT EXISTS chunks (chunk_id INTEGER PRIMARY KEY, knowledge_id TEXT, candidate_id TEXT,
 section TEXT, text TEXT, is_active INTEGER, node_id TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, tokenize='unicode61');
CREATE TABLE IF NOT EXISTS knowledge_provenance (chunk_id INTEGER, source_document_id TEXT, evidence_ids TEXT);
CREATE TABLE IF NOT EXISTS evidence (evidence_id TEXT, document_id TEXT, page_no INTEGER, element_type TEXT,
 text TEXT, bbox TEXT, PRIMARY KEY(document_id,evidence_id));
CREATE TABLE IF NOT EXISTS assets (asset_id INTEGER PRIMARY KEY, document_id TEXT, type TEXT, data_json TEXT);
CREATE TABLE IF NOT EXISTS archive_records (document_id TEXT PRIMARY KEY, data_json TEXT);
CREATE TABLE IF NOT EXISTS retrieval_runs (run_id TEXT PRIMARY KEY, created_at TEXT, data_json TEXT);
CREATE TABLE IF NOT EXISTS index_metadata (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS education (candidate_id TEXT, document_id TEXT, data_json TEXT);
CREATE TABLE IF NOT EXISTS employment (candidate_id TEXT, document_id TEXT, data_json TEXT);
CREATE TABLE IF NOT EXISTS projects (candidate_id TEXT, document_id TEXT, data_json TEXT);
CREATE TABLE IF NOT EXISTS skills (candidate_id TEXT, document_id TEXT, data_json TEXT);
CREATE TABLE IF NOT EXISTS tables (table_id TEXT, document_id TEXT, data_json TEXT);
CREATE TABLE IF NOT EXISTS table_cells (table_id TEXT, document_id TEXT, row_no INTEGER, col_no INTEGER, data_json TEXT);
CREATE TABLE IF NOT EXISTS relationships (candidate_id TEXT, document_id TEXT, data_json TEXT);
"""


class Store:
    def __init__(self, settings, signature):
        self.path = settings.data_dir / 'sqlite' / 'hr.db'
        self.dim = settings.embedding_dim
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(embedding float[{self.dim}] distance_metric=cosine)")
            existing = db.execute("SELECT value FROM index_metadata WHERE key='embedding'").fetchone()
            if existing and existing[0] != signature:
                raise ValueError("Embedding 配置已变化。请使用新的 HR_DATA_DIR 导入建立新版本索引，旧库已保留。")
            db.execute("INSERT OR IGNORE INTO index_metadata VALUES ('embedding',?)", (signature,))
            # Interrupted jobs remain retryable after process restart.
            db.execute("UPDATE source_documents SET status='failed', error='服务中断，请重试' WHERE status='processing'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def stage(self, doc, stage, error=None, **fields):
        status = stage if stage in {'succeeded','partial_success','failed','quality_failed','rejected_duplicate'} else 'processing'
        with self.connect() as db:
            db.execute("UPDATE source_documents SET stage=?,status=?,error=? WHERE document_id=?", (stage,status,error,doc))
            for key, value in fields.items():
                if key not in {'elapsed','metrics_json','warnings_json'}:
                    raise ValueError('Invalid state field')
                db.execute(f"UPDATE source_documents SET {key}=? WHERE document_id=?", (value,doc))
            db.execute("INSERT INTO processing_jobs(document_id,stage,status,created_at,error_json) VALUES (?,?,?,?,?)", (doc,stage,status,now(),dumps({'message':error}) if error else None))
