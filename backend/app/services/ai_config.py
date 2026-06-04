import json
from datetime import datetime, timezone

from cryptography.fernet import Fernet

from app.config import ENCRYPTION_KEY, LLM_DEFAULT_API_KEY, LLM_DEFAULT_BASE_URL, LLM_DEFAULT_MODEL, LLM_DEFAULT_PROVIDER
from app.database import get_connection
from app.models.ai_config import AIModelConfigCreate, AIModelConfigResponse, AIModelConfigUpdate


class EncryptionKeyNotSetError(Exception):
    pass


def _get_fernet() -> Fernet:
    if not ENCRYPTION_KEY:
        raise EncryptionKeyNotSetError("请在 .env 中设置 ENCRYPTION_KEY")
    return Fernet(ENCRYPTION_KEY.encode())


def encrypt_api_key(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


def mask_api_key(key: str) -> str:
    if len(key) <= 4:
        return "****"
    return f"****{key[-4:]}"


def _row_to_response(row) -> AIModelConfigResponse:
    d = dict(row)
    d["api_key_masked"] = mask_api_key(decrypt_api_key(d.pop("api_key_enc")))
    d["extra"] = json.loads(d.get("extra", "{}"))
    d["is_default"] = bool(d["is_default"])
    d["is_enabled"] = bool(d["is_enabled"])
    return AIModelConfigResponse(**d)


def list_configs() -> list[AIModelConfigResponse]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM ai_model_config ORDER BY is_default DESC, updated_at DESC").fetchall()
    conn.close()
    return [_row_to_response(r) for r in rows]


def get_config(config_id: int) -> AIModelConfigResponse | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM ai_model_config WHERE id = ?", (config_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_response(row)


def get_default_config() -> AIModelConfigResponse | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM ai_model_config WHERE is_default = 1 AND is_enabled = 1").fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_response(row)


def get_decrypted_config(config_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM ai_model_config WHERE id = ? AND is_enabled = 1", (config_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["api_key"] = decrypt_api_key(d.pop("api_key_enc"))
    d["extra"] = json.loads(d.get("extra", "{}"))
    d["is_default"] = bool(d["is_default"])
    d["is_enabled"] = bool(d["is_enabled"])
    return d


def get_decrypted_default() -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM ai_model_config WHERE is_default = 1 AND is_enabled = 1").fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["api_key"] = decrypt_api_key(d.pop("api_key_enc"))
    d["extra"] = json.loads(d.get("extra", "{}"))
    d["is_default"] = bool(d["is_default"])
    d["is_enabled"] = bool(d["is_enabled"])
    return d


def create_config(data: AIModelConfigCreate) -> AIModelConfigResponse:
    now = datetime.now(timezone.utc).isoformat()
    encrypted_key = encrypt_api_key(data.api_key)
    conn = get_connection()
    if data.is_default:
        conn.execute("UPDATE ai_model_config SET is_default = 0 WHERE is_default = 1")
    conn.execute(
        """INSERT INTO ai_model_config
           (name, provider, model, base_url, api_key_enc, temperature, max_tokens, is_default, is_enabled, extra, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.name, data.provider, data.model, data.base_url,
            encrypted_key, data.temperature, data.max_tokens,
            int(data.is_default), 1,
            json.dumps(data.extra), now, now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM ai_model_config WHERE id = last_insert_rowid()").fetchone()
    conn.close()
    return _row_to_response(row)


def update_config(config_id: int, data: AIModelConfigUpdate) -> AIModelConfigResponse | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM ai_model_config WHERE id = ?", (config_id,)).fetchone()
    if not row:
        conn.close()
        return None

    updates = []
    values = []
    existing = dict(row)

    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "api_key" and value:
            updates.append("api_key_enc = ?")
            values.append(encrypt_api_key(value))
        elif field == "api_key":
            continue
        elif field in ("is_default", "is_enabled"):
            updates.append(f"{field} = ?")
            values.append(int(value))
        elif field == "extra":
            updates.append("extra = ?")
            values.append(json.dumps(value))
        else:
            updates.append(f"{field} = ?")
            values.append(value)

    if not updates:
        conn.close()
        return _row_to_response(row)

    if data.is_default:
        conn.execute("UPDATE ai_model_config SET is_default = 0 WHERE is_default = 1")

    now = datetime.now(timezone.utc).isoformat()
    updates.append("updated_at = ?")
    values.append(now)
    values.append(config_id)
    conn.execute(f"UPDATE ai_model_config SET {', '.join(updates)} WHERE id = ?", values)
    conn.commit()
    row = conn.execute("SELECT * FROM ai_model_config WHERE id = ?", (config_id,)).fetchone()
    conn.close()
    return _row_to_response(row)


def delete_config(config_id: int) -> bool:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM ai_model_config WHERE id = ?", (config_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def seed_from_env():
    if not all([LLM_DEFAULT_PROVIDER, LLM_DEFAULT_MODEL, LLM_DEFAULT_API_KEY]):
        return
    if not ENCRYPTION_KEY:
        return
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM ai_model_config").fetchone()[0]
    conn.close()
    if count > 0:
        return
    create_config(AIModelConfigCreate(
        name=f"{LLM_DEFAULT_PROVIDER}/{LLM_DEFAULT_MODEL}",
        provider=LLM_DEFAULT_PROVIDER,
        model=LLM_DEFAULT_MODEL,
        base_url=LLM_DEFAULT_BASE_URL,
        api_key=LLM_DEFAULT_API_KEY,
        is_default=True,
    ))
