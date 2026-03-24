from sqlalchemy import text

from db.session import SessionLocal, set_tenant_context
from core.config import INPUT_TOKEN_PRICE_PER_1K, OUTPUT_TOKEN_PRICE_PER_1K, HARD_LIMIT_USD_PER_MONTH
from models.tenant import Tenant


def log_llm_usage(
    tenant_id: int,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    conversation_id: int = None,
) -> None:
    """
    Persist LLM token usage for analytics/billing by tenant.
    """
    db = SessionLocal()
    try:
        set_tenant_context(db, tenant_id)

        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS llm_usage_logs (
                    id SERIAL PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    conversation_id INTEGER NULL,
                    model_name VARCHAR(120) NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        db.execute(
            text(
                """
                ALTER TABLE llm_usage_logs
                ADD COLUMN IF NOT EXISTS estimated_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0
                """
            )
        )

        estimated_cost_usd = (
            (prompt_tokens / 1000.0) * INPUT_TOKEN_PRICE_PER_1K
            + (completion_tokens / 1000.0) * OUTPUT_TOKEN_PRICE_PER_1K
        )

        db.execute(
            text(
                """
                INSERT INTO llm_usage_logs (
                    tenant_id,
                    conversation_id,
                    model_name,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    estimated_cost_usd
                ) VALUES (
                    :tenant_id,
                    :conversation_id,
                    :model_name,
                    :prompt_tokens,
                    :completion_tokens,
                    :total_tokens,
                    :estimated_cost_usd
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "conversation_id": conversation_id,
                "model_name": model_name,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "estimated_cost_usd": estimated_cost_usd,
            },
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"⚠️ Failed to log LLM usage: {e}")
    finally:
        db.close()


def get_monthly_tenant_spend(tenant_id: int) -> float:
    """Return current month LLM spend (USD) for a tenant."""
    db = SessionLocal()
    try:
        set_tenant_context(db, tenant_id)
        row = db.execute(
            text(
                """
                SELECT COALESCE(SUM(estimated_cost_usd), 0) AS monthly_spend
                FROM llm_usage_logs
                WHERE tenant_id = :tenant_id
                  AND created_at >= date_trunc('month', NOW())
                  AND created_at < date_trunc('month', NOW()) + INTERVAL '1 month'
                """
            ),
            {"tenant_id": tenant_id},
        ).fetchone()
        return float(row[0] or 0.0)
    except Exception as e:
        print(f"⚠️ Failed to read monthly spend: {e}")
        return 0.0
    finally:
        db.close()


def enforce_monthly_hard_limit(tenant_id: int, hard_limit_usd: float = HARD_LIMIT_USD_PER_MONTH):
    """
    Check tenant monthly spend and auto-deactivate tenant when exceeding hard limit.
    Returns (is_allowed, info).
    """
    db = SessionLocal()
    try:
        set_tenant_context(db, tenant_id)

        # Ensure table exists before reading aggregate.
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS llm_usage_logs (
                    id SERIAL PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    conversation_id INTEGER NULL,
                    model_name VARCHAR(120) NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        db.execute(
            text(
                """
                ALTER TABLE llm_usage_logs
                ADD COLUMN IF NOT EXISTS estimated_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0
                """
            )
        )
        db.commit()

        spend_row = db.execute(
            text(
                """
                SELECT COALESCE(SUM(estimated_cost_usd), 0) AS monthly_spend
                FROM llm_usage_logs
                WHERE tenant_id = :tenant_id
                  AND created_at >= date_trunc('month', NOW())
                  AND created_at < date_trunc('month', NOW()) + INTERVAL '1 month'
                """
            ),
            {"tenant_id": tenant_id},
        ).fetchone()
        monthly_spend = float(spend_row[0] or 0.0)

        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return False, {"reason": "tenant_not_found"}

        if monthly_spend >= hard_limit_usd:
            if tenant.is_active:
                tenant.is_active = False
                db.commit()
            return False, {
                "reason": "hard_limit_exceeded",
                "monthly_spend_usd": round(monthly_spend, 4),
                "hard_limit_usd": hard_limit_usd,
            }

        return True, {
            "monthly_spend_usd": round(monthly_spend, 4),
            "hard_limit_usd": hard_limit_usd,
            "remaining_usd": round(max(0.0, hard_limit_usd - monthly_spend), 4),
        }
    except Exception as e:
        db.rollback()
        print(f"⚠️ Hard limit check failed: {e}")
        # Fail-open to avoid blocking all traffic on transient DB issues.
        return True, {"error": str(e)}
    finally:
        db.close()

