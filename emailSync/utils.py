import hashlib
from datetime import datetime, timezone


def hash_str(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def normalize_to_utc(ts: str) -> str:
    dt = datetime.fromisoformat(ts)
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.isoformat().replace("+00:00", "Z")
