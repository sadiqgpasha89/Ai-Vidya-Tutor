"""Ordered, append-only schema migrations. Never edit an applied migration; add a new one."""

BASELINE = """
CREATE TABLE IF NOT EXISTS students (
  id TEXT PRIMARY KEY, name TEXT, grade INTEGER, language TEXT, level TEXT, board TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS progress (
  student_id TEXT, subtopic_id TEXT, status TEXT, mastery REAL DEFAULT 0, last_studied REAL,
  PRIMARY KEY (student_id, subtopic_id)
);
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, subtopic_id TEXT, kind TEXT, note TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS revision (
  student_id TEXT, subtopic_id TEXT, box INTEGER DEFAULT 0, due_at REAL,
  PRIMARY KEY (student_id, subtopic_id)
);
CREATE TABLE IF NOT EXISTS activity (student_id TEXT, day TEXT, PRIMARY KEY (student_id, day));
"""

ACCOUNTS = """
CREATE TABLE users (
  id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, role TEXT NOT NULL,
  password_hash TEXT, recovery_hash TEXT, birth_year INTEGER, consent TEXT NOT NULL DEFAULT 'na',
  school_id TEXT, disabled INTEGER NOT NULL DEFAULT 0, created_at REAL, last_login REAL
);
CREATE TABLE sessions (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at REAL, expires_at REAL, user_agent TEXT
);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE TABLE consents (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, parent_id TEXT, notice_version TEXT,
  action TEXT NOT NULL, method TEXT, created_at REAL
);
CREATE TABLE parent_links (parent_id TEXT NOT NULL, student_id TEXT NOT NULL, created_at REAL, PRIMARY KEY (parent_id, student_id));
CREATE TABLE link_codes (code TEXT PRIMARY KEY, student_id TEXT NOT NULL, expires_at REAL);
CREATE TABLE schools (id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT UNIQUE NOT NULL, created_at REAL);
CREATE TABLE classes (
  id TEXT PRIMARY KEY, school_id TEXT, teacher_id TEXT NOT NULL, name TEXT NOT NULL, grade INTEGER,
  join_code TEXT UNIQUE NOT NULL, created_at REAL
);
CREATE TABLE class_members (
  class_id TEXT NOT NULL, student_id TEXT NOT NULL, nickname TEXT, share_leaderboard INTEGER NOT NULL DEFAULT 0,
  joined_at REAL, PRIMARY KEY (class_id, student_id)
);
CREATE TABLE assignments (
  id TEXT PRIMARY KEY, class_id TEXT NOT NULL, kind TEXT NOT NULL, subtopic_id TEXT, title TEXT NOT NULL,
  note TEXT, due_at REAL, created_by TEXT, created_at REAL
);
CREATE TABLE assignment_status (
  assignment_id TEXT NOT NULL, student_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'todo', score REAL, completed_at REAL,
  PRIMARY KEY (assignment_id, student_id)
);
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, actor_id TEXT, action TEXT NOT NULL, target TEXT, detail TEXT, ip TEXT
);
CREATE INDEX idx_audit_ts ON audit_log(ts);
CREATE TABLE usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, kind TEXT, provider TEXT, model TEXT,
  input_tokens INTEGER, output_tokens INTEGER, latency_ms INTEGER, ok INTEGER
);
CREATE INDEX idx_usage_ts ON usage(ts);
CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, kind TEXT, subtopic_id TEXT, meta TEXT);
CREATE INDEX idx_events_ts ON events(ts);
CREATE TABLE notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, kind TEXT, title TEXT, body TEXT, link TEXT,
  created_at REAL, read_at REAL, emailed INTEGER DEFAULT 0, pushed INTEGER DEFAULT 0, whatsapp INTEGER DEFAULT 0
);
CREATE INDEX idx_notif_user ON notifications(user_id, read_at);
CREATE TABLE push_subs (user_id TEXT NOT NULL, endpoint TEXT PRIMARY KEY, subscription TEXT NOT NULL);
CREATE TABLE contacts (user_id TEXT PRIMARY KEY, email TEXT, phone TEXT, notify_email INTEGER DEFAULT 0, notify_whatsapp INTEGER DEFAULT 0);
"""

LEARNING = """
ALTER TABLE progress ADD COLUMN last_section INTEGER DEFAULT 0;
ALTER TABLE progress ADD COLUMN p_known REAL;
ALTER TABLE progress ADD COLUMN stability REAL DEFAULT 1.0;
ALTER TABLE progress ADD COLUMN last_evidence REAL;
ALTER TABLE students ADD COLUMN stream TEXT DEFAULT '';
ALTER TABLE students ADD COLUMN track TEXT DEFAULT '';
ALTER TABLE students ADD COLUMN goal TEXT DEFAULT 'boards';
ALTER TABLE students ADD COLUMN exam_date TEXT DEFAULT '';
ALTER TABLE students ADD COLUMN daily_minutes INTEGER DEFAULT 30;
CREATE TABLE chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, subtopic_id TEXT NOT NULL, role TEXT NOT NULL,
  content TEXT NOT NULL, created_at REAL
);
CREATE INDEX idx_chat ON chat_messages(student_id, subtopic_id, id);
CREATE TABLE boards (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, subtopic_id TEXT NOT NULL, title TEXT, markdown TEXT, svg TEXT, created_at REAL
);
CREATE INDEX idx_boards ON boards(student_id, subtopic_id);
CREATE TABLE notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, subtopic_id TEXT, title TEXT, body TEXT, created_at REAL, updated_at REAL
);
CREATE INDEX idx_notes ON notes(student_id, subtopic_id);
CREATE TABLE highlights (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, subtopic_id TEXT NOT NULL, section_index INTEGER, text TEXT, color TEXT, created_at REAL
);
CREATE INDEX idx_highlights ON highlights(student_id, subtopic_id);
CREATE TABLE bookmarks (student_id TEXT NOT NULL, subtopic_id TEXT NOT NULL, created_at REAL, PRIMARY KEY (student_id, subtopic_id));
CREATE TABLE mistakes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, subtopic_id TEXT NOT NULL, source TEXT,
  question TEXT, options TEXT, chosen TEXT, correct TEXT, explanation TEXT, concept TEXT,
  times_wrong INTEGER DEFAULT 1, created_at REAL, resolved_at REAL
);
CREATE INDEX idx_mistakes ON mistakes(student_id, resolved_at);
CREATE TABLE flashcards (
  id INTEGER PRIMARY KEY AUTOINCREMENT, subtopic_id TEXT NOT NULL, language TEXT NOT NULL, front TEXT, back TEXT, kind TEXT, created_at REAL
);
CREATE INDEX idx_cards ON flashcards(subtopic_id, language);
CREATE TABLE card_state (
  student_id TEXT NOT NULL, card_id INTEGER NOT NULL, ease REAL DEFAULT 2.5, interval_days REAL DEFAULT 0,
  due_at REAL, reps INTEGER DEFAULT 0, lapses INTEGER DEFAULT 0, PRIMARY KEY (student_id, card_id)
);
CREATE TABLE xp_events (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, kind TEXT, points INTEGER, created_at REAL);
CREATE INDEX idx_xp ON xp_events(student_id, created_at);
CREATE TABLE badges (student_id TEXT NOT NULL, badge TEXT NOT NULL, earned_at REAL, PRIMARY KEY (student_id, badge));
CREATE TABLE feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, subtopic_id TEXT NOT NULL, section_index INTEGER,
  rating INTEGER, tag TEXT, created_at REAL
);
CREATE TABLE reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, kind TEXT, subtopic_id TEXT, ref TEXT, message TEXT,
  status TEXT DEFAULT 'open', resolution TEXT, created_at REAL, resolved_by TEXT, resolved_at REAL
);
CREATE TABLE student_memory (student_id TEXT PRIMARY KEY, summary TEXT, msgs_since INTEGER DEFAULT 0, updated_at REAL);
CREATE TABLE practice_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, subtopic_id TEXT NOT NULL, item TEXT NOT NULL,
  difficulty INTEGER, created_at REAL, attempts INTEGER DEFAULT 0, solved INTEGER DEFAULT 0
);
CREATE TABLE viva_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, subtopic_id TEXT NOT NULL, turns TEXT, status TEXT,
  score REAL, summary TEXT, created_at REAL
);
CREATE TABLE tests (
  id TEXT PRIMARY KEY, student_id TEXT NOT NULL, title TEXT, paper TEXT NOT NULL, duration_min INTEGER, started_at REAL,
  submitted_at REAL, answers TEXT, result TEXT, assignment_id TEXT, created_at REAL
);
CREATE TABLE question_bank (
  id INTEGER PRIMARY KEY AUTOINCREMENT, subtopic_id TEXT, kind TEXT, marks INTEGER, question TEXT NOT NULL, options TEXT,
  answer TEXT, solution TEXT, difficulty INTEGER, source TEXT, board TEXT, year TEXT, created_by TEXT, approved INTEGER DEFAULT 1, created_at REAL
);
CREATE INDEX idx_qb ON question_bank(subtopic_id, kind);
"""

CONTENT = """
CREATE TABLE lesson_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, subtopic_id TEXT NOT NULL, variant TEXT NOT NULL, version INTEGER NOT NULL,
  model TEXT, source TEXT NOT NULL DEFAULT 'ai', status TEXT NOT NULL DEFAULT 'draft', sections TEXT NOT NULL,
  factcheck TEXT, reviewer_id TEXT, review_note TEXT, reviewed_at REAL, is_active INTEGER NOT NULL DEFAULT 0, created_at REAL
);
CREATE INDEX idx_lv ON lesson_versions(subtopic_id, variant, is_active);
CREATE TABLE extras (
  subtopic_id TEXT NOT NULL, variant TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL, model TEXT, created_at REAL,
  PRIMARY KEY (subtopic_id, variant, kind)
);
CREATE TABLE media (
  id INTEGER PRIMARY KEY AUTOINCREMENT, subtopic_id TEXT NOT NULL, kind TEXT NOT NULL, url TEXT NOT NULL, title TEXT, added_by TEXT, created_at REAL
);
CREATE TABLE library_docs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, owner_id TEXT, title TEXT, filename TEXT, subject TEXT,
  grade INTEGER, pages INTEGER, chunks INTEGER, created_at REAL
);
CREATE TABLE library_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER NOT NULL, ord INTEGER, page INTEGER, text TEXT NOT NULL, embedding BLOB
);
CREATE INDEX idx_chunks_doc ON library_chunks(doc_id);
CREATE TABLE topic_embeddings (subtopic_id TEXT NOT NULL, model TEXT NOT NULL, vec BLOB NOT NULL, PRIMARY KEY (subtopic_id, model));
"""

LANGUAGES_20 = """
UPDATE students SET language='en' WHERE language NOT IN ('en','hi','bn','mr','te','ta','gu','ur','kn','or','ml','zh','es','fr','ar','pt','ru','id','de','ja');
"""

CUSTOM_TOPICS = """
CREATE TABLE custom_topics (
  id TEXT PRIMARY KEY, student_id TEXT NOT NULL, subject TEXT NOT NULL, title TEXT NOT NULL, details TEXT NOT NULL DEFAULT '',
  grade INTEGER NOT NULL, created_at REAL NOT NULL
);
CREATE INDEX idx_custom_student ON custom_topics(student_id);
"""

IDLE_SESSIONS = """
ALTER TABLE sessions ADD COLUMN last_seen REAL;
UPDATE sessions SET last_seen = created_at;
"""

REMEMBER_DEVICE = """
ALTER TABLE sessions ADD COLUMN remember INTEGER NOT NULL DEFAULT 0;
"""

STUDY_NOTES = """
CREATE TABLE study_notes (
  student_id TEXT NOT NULL, subtopic_id TEXT NOT NULL, variant TEXT NOT NULL, version_id INTEGER, title TEXT NOT NULL, body TEXT NOT NULL,
  model TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY (student_id, subtopic_id, variant)
);
CREATE INDEX idx_study_notes_topic ON study_notes(subtopic_id);
"""

EMAIL_OTP = """
ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX idx_users_email ON users(lower(email)) WHERE email IS NOT NULL;
CREATE TABLE email_otps (
  id TEXT PRIMARY KEY, purpose TEXT NOT NULL, email TEXT NOT NULL, user_id TEXT, code_hash TEXT NOT NULL, salt TEXT NOT NULL, payload TEXT,
  attempts INTEGER NOT NULL DEFAULT 0, sends INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, last_sent REAL NOT NULL, expires_at REAL NOT NULL
);
CREATE INDEX idx_email_otps_email ON email_otps(email, purpose);
CREATE INDEX idx_email_otps_user ON email_otps(user_id, purpose);
"""

# The product is called AIVidya: text the app itself wrote earlier (tutor replies, lessons, notices) is brought in line. The marker character keeps "AIVidya" from becoming "AIAIVidya".
RENAME_BRAND = """
UPDATE chat_messages SET content = replace(replace(replace(content, 'AIVidya', ''), 'Vidya', 'AIVidya'), '', 'AIVidya') WHERE content LIKE '%Vidya%';
UPDATE notifications SET title = replace(replace(replace(title, 'AIVidya', ''), 'Vidya', 'AIVidya'), '', 'AIVidya') WHERE title LIKE '%Vidya%';
UPDATE notifications SET body = replace(replace(replace(body, 'AIVidya', ''), 'Vidya', 'AIVidya'), '', 'AIVidya') WHERE body LIKE '%Vidya%';
UPDATE extras SET body = replace(replace(replace(body, 'AIVidya', ''), 'Vidya', 'AIVidya'), '', 'AIVidya') WHERE body LIKE '%Vidya%';
UPDATE lesson_versions SET sections = replace(replace(replace(sections, 'AIVidya', ''), 'Vidya', 'AIVidya'), '', 'AIVidya') WHERE sections LIKE '%Vidya%';
UPDATE study_notes SET title = replace(replace(replace(title, 'AIVidya', ''), 'Vidya', 'AIVidya'), '', 'AIVidya') WHERE title LIKE '%Vidya%';
UPDATE study_notes SET body = replace(replace(replace(body, 'AIVidya', ''), 'Vidya', 'AIVidya'), '', 'AIVidya') WHERE body LIKE '%Vidya%';
UPDATE boards SET markdown = replace(replace(replace(markdown, 'AIVidya', ''), 'Vidya', 'AIVidya'), '', 'AIVidya') WHERE markdown LIKE '%Vidya%';
UPDATE student_memory SET summary = replace(replace(replace(summary, 'AIVidya', ''), 'Vidya', 'AIVidya'), '', 'AIVidya') WHERE summary LIKE '%Vidya%';
"""

STUDY_FEATURES = """
CREATE TABLE daily_sets (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, day TEXT NOT NULL, questions TEXT NOT NULL, answers TEXT NOT NULL DEFAULT '{}',
  score INTEGER, created_at REAL NOT NULL, completed_at REAL, UNIQUE (student_id, day)
);
CREATE TABLE answer_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, subtopic_id TEXT NOT NULL, marks INTEGER NOT NULL, question TEXT NOT NULL,
  model_answer TEXT NOT NULL DEFAULT '', scheme TEXT NOT NULL DEFAULT '', own_question INTEGER NOT NULL DEFAULT 0,
  answer TEXT, awarded REAL, result TEXT, created_at REAL NOT NULL, submitted_at REAL
);
CREATE INDEX idx_attempts_student ON answer_attempts(student_id, created_at);
CREATE TABLE doubts (
  id TEXT PRIMARY KEY, student_id TEXT NOT NULL, class_id TEXT NOT NULL, subtopic_id TEXT, question TEXT NOT NULL, ai_answer TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open', created_at REAL NOT NULL, updated_at REAL NOT NULL, student_seen REAL NOT NULL DEFAULT 0, teacher_seen REAL NOT NULL DEFAULT 0
);
CREATE INDEX idx_doubts_class ON doubts(class_id, status, updated_at);
CREATE INDEX idx_doubts_student ON doubts(student_id, updated_at);
CREATE TABLE doubt_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, doubt_id TEXT NOT NULL, author_id TEXT, role TEXT NOT NULL, body TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE INDEX idx_doubt_messages ON doubt_messages(doubt_id, id);
CREATE TABLE worksheets (
  id TEXT PRIMARY KEY, created_by TEXT NOT NULL, title TEXT NOT NULL, paper TEXT NOT NULL, settings TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL
);
CREATE INDEX idx_worksheets_owner ON worksheets(created_by, created_at);
"""

MIGRATIONS = [(1, BASELINE), (2, ACCOUNTS), (3, LEARNING), (4, CONTENT), (5, LANGUAGES_20), (6, CUSTOM_TOPICS), (7, IDLE_SESSIONS), (8, STUDY_NOTES), (9, EMAIL_OTP), (10, RENAME_BRAND), (11, REMEMBER_DEVICE), (12, STUDY_FEATURES)]
