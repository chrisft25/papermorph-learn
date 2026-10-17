"""Multi-user support for the hosted tutor: users, login sessions, per-user storage and per-user secrets.

Everything lives in data/app.db (SQLite) and data/secret.key (random, chmod 600, created on first use; or set
TUTOR_SECRET). Passwords: scrypt. Sessions: HMAC-signed cookie. Per-user API keys: Fernet-encrypted at rest.
"""
import base64, hashlib, hmac, json, os, re, secrets, sqlite3, threading, time
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

DATA = Path(os.environ.get("TUTOR_DATA_DIR") or Path(__file__).parent / "data")
DATA.mkdir(exist_ok=True)
_lock = threading.Lock()
_db = None
USER_RE = re.compile(r"^[A-Za-z0-9_.-]{2,32}$")
KEY_RE = re.compile(r"^[\w:\-./]{1,120}$")
SESSION_DAYS = 30


def secret() -> bytes:
    if os.environ.get("TUTOR_SECRET"):
        return os.environ["TUTOR_SECRET"].encode()
    f = DATA / "secret.key"
    if not f.exists():
        f.write_bytes(base64.urlsafe_b64encode(secrets.token_bytes(32)))
        f.chmod(0o600)
    return f.read_bytes().strip()


def backup_db(keep: int = 14) -> Path | None:
    """Consistent copy of app.db into data/backups/ (SQLite online-backup API). Called on every server start and by the CLI."""
    src = DATA / "app.db"
    if not src.exists() or src.stat().st_size == 0:
        return None
    out = DATA / "backups"
    out.mkdir(exist_ok=True)
    dst = out / time.strftime("app-%Y%m%d-%H%M%S.db")
    a, b = sqlite3.connect(src), sqlite3.connect(dst)
    with b:
        a.backup(b)
    a.close(); b.close()
    dst.chmod(0o600)
    for old in sorted(out.glob("app-*.db"))[:-keep]:
        old.unlink()
    return dst


def db() -> sqlite3.Connection:
    global _db
    if _db is None:
        backup_db()   # never touch existing data without a fresh backup
        _db = sqlite3.connect(DATA / "app.db", check_same_thread=False)
        _db.executescript("""
        create table if not exists users(name text primary key, display text, pw text not null, created integer, perms text default '');
        create table if not exists kv(user text, key text, value text, updated integer, primary key(user, key));
        create table if not exists settings(user text primary key, blob text);
        """)
        if "perms" not in [r[1] for r in _db.execute("pragma table_info(users)")]:   # additive migration only
            _db.execute("alter table users add column perms text default ''")
            _db.commit()
        (DATA / "app.db").chmod(0o600)
    return _db


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret()).digest()))


# ---- users / passwords ----
def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def check_pw(pw: str, stored: str) -> bool:
    try:
        _, s, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(got, base64.b64decode(h))
    except Exception:
        return False


PERMS = ("run",)   # run = Python code cells (executed on the server). Add more names here for your own features.


def _check_pw_policy(name: str, pw: str) -> None:
    if not USER_RE.match(name):
        raise ValueError("username: 2-32 chars of letters, digits, _ . -")
    if len(pw) < 8:
        raise ValueError("password: at least 8 characters")


def add_user(name: str, pw: str, display: str = "", perms=()) -> None:
    _check_pw_policy(name, pw)
    with _lock:
        if db().execute("select 1 from users where name=?", (name.lower(),)).fetchone():
            raise ValueError(f"user '{name}' already exists (use passwd / perms to change it)")
        db().execute("insert into users(name, display, pw, created, perms) values(?,?,?,?,?)", (name.lower(), display or name, hash_pw(pw), int(time.time()), ",".join(p for p in PERMS if p in perms)))
        db().commit()


def set_password(name: str, pw: str) -> None:
    _check_pw_policy(name, pw)
    with _lock:
        if not db().execute("update users set pw=? where name=?", (hash_pw(pw), name.lower())).rowcount:
            raise ValueError(f"no such user '{name}'")
        db().commit()


def set_perms(name: str, perms) -> None:
    with _lock:
        if not db().execute("update users set perms=? where name=?", (",".join(p for p in PERMS if p in perms), name.lower())).rowcount:
            raise ValueError(f"no such user '{name}'")
        db().commit()


def get_perms(name: str) -> set:
    r = db().execute("select perms from users where name=?", (name,)).fetchone()
    return set(filter(None, (r[0] or "").split(","))) if r else set()


def remove_user(name: str, purge: bool = False) -> None:
    """Removes the login. The user's progress, notes, chats and settings are KEPT unless purge=True (and a backup is made first)."""
    backup_db()
    with _lock:
        db().execute("delete from users where name=?", (name.lower(),))
        if purge:
            db().execute("delete from kv where user=?", (name.lower(),))
            db().execute("delete from settings where user=?", (name.lower(),))
        db().commit()


def list_users():
    return db().execute("select name, display, created, perms from users order by name").fetchall()


def login(name: str, pw: str):
    row = db().execute("select name, display, pw from users where name=?", (name.lower(),)).fetchone()
    # always run a hash check so unknown users and wrong passwords take the same time
    ok = check_pw(pw, row[2] if row else "scrypt$AAAAAAAAAAAAAAAAAAAAAA==$" + base64.b64encode(b"x" * 32).decode())
    return (row[0], row[1]) if row and ok else None


def display(name: str) -> str:
    r = db().execute("select display from users where name=?", (name,)).fetchone()
    return r[0] if r else name


# ---- sessions (signed cookie) ----
def _sig(payload: str) -> str:
    return base64.urlsafe_b64encode(hmac.new(secret(), payload.encode(), hashlib.sha256).digest()).decode().rstrip("=")


def make_token(user: str) -> str:
    payload = f"{user}|{int(time.time()) + SESSION_DAYS * 86400}"
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + _sig(payload)


def verify(token: str | None):
    try:
        p64, sig = (token or "").split(".")
        payload = base64.urlsafe_b64decode(p64 + "=" * (-len(p64) % 4)).decode()
        if not hmac.compare_digest(sig, _sig(payload)):
            return None
        user, exp = payload.rsplit("|", 1)
        if int(exp) < time.time():
            return None
        return user if db().execute("select 1 from users where name=?", (user,)).fetchone() else None
    except Exception:
        return None


# ---- login throttling (per client IP) ----
_fails: dict[str, list[float]] = {}


def throttled(ip: str) -> bool:
    now = time.time()
    _fails[ip] = [t for t in _fails.get(ip, []) if now - t < 600]
    return len(_fails[ip]) >= 8


def note_fail(ip: str) -> None:
    _fails.setdefault(ip, []).append(time.time())


# ---- per-user key/value storage (progress, notes, chat history, preferences) ----
def kv_all(user: str) -> dict:
    return {k: v for k, v in db().execute("select key, value from kv where user=?", (user,))}


def kv_put(user: str, items: dict) -> int:
    n = 0
    with _lock:
        for k, v in items.items():
            if not KEY_RE.match(k):
                continue
            if v is None:
                db().execute("delete from kv where user=? and key=?", (user, k))
            elif isinstance(v, str) and len(v) <= 3_000_000:
                db().execute("insert or replace into kv(user, key, value, updated) values(?,?,?,?)", (user, k, v, int(time.time())))
            else:
                continue
            n += 1
        db().commit()
    return n


# ---- per-user settings (API keys encrypted) ----
SECRET_FIELDS = ("claude_key",)
PLAIN_FIELDS = ("claude_url", "model_fast", "model_normal", "model_deep")


def get_settings(user: str) -> dict:
    r = db().execute("select blob from settings where user=?", (user,)).fetchone()
    if not r:
        return {}
    try:
        return json.loads(_fernet().decrypt(r[0].encode()))
    except (InvalidToken, ValueError):
        return {}


def put_settings(user: str, upd: dict) -> None:
    cur = get_settings(user)
    for f in PLAIN_FIELDS:
        if f in upd:
            cur[f] = str(upd[f]).strip()
    for f in SECRET_FIELDS:
        if upd.get(f):
            cur[f] = str(upd[f]).strip()
    for f in upd.get("clear", []):
        cur.pop(f, None)
    with _lock:
        db().execute("insert or replace into settings(user, blob) values(?,?)", (user, _fernet().encrypt(json.dumps(cur).encode()).decode()))
        db().commit()


def public_settings(user: str) -> dict:
    s = get_settings(user)
    return {"claude_url": s.get("claude_url", ""), "claude_key_set": bool(s.get("claude_key")),
            "model_fast": s.get("model_fast", ""), "model_normal": s.get("model_normal", ""), "model_deep": s.get("model_deep", "")}
