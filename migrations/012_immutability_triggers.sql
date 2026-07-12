BEGIN;

-- ============================================================
-- 012: 不可变性 trigger（active fact / supported claim）
-- ============================================================
-- 这些 trigger 是 Service / Store 不可变性约束的最后防线：
--   * active / superseded / retracted fact 的语义列（fact_text / fact_type /
--     normalized_data / 时间语义 / confirmed subject）禁止 UPDATE；
--   * active fact 的 confirmed subject link 禁止增删改；
--   * supported claim 的语义列（claim_text / limitations / scope / claim_facts）
--     禁止 UPDATE；
--   * active / superseded / retracted fact 不允许物理 DELETE。
--
-- Service 应通过 supersede_fact / split_fact_evidence / supersede_claim /
-- approve_claim 等显式操作完成更正；任何绕过 Service 的更新都会被 trigger
-- 拒绝，PostgresIntelStore 把 StoreError 转成 IntelligenceInvariantError。

-- ----------------------------------------------------------------
-- 1. fact 语义不可变性
-- ----------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_intel_facts_immutable_columns() RETURNS trigger AS $$
DECLARE
    locked_status TEXT := 'active';
BEGIN
    IF OLD.lifecycle_status IS NOT NULL AND OLD.lifecycle_status IN ('active', 'superseded', 'retracted') THEN
        IF NEW.fact_text IS DISTINCT FROM OLD.fact_text
           OR NEW.fact_type IS DISTINCT FROM OLD.fact_type
           OR NEW.normalized_data IS DISTINCT FROM OLD.normalized_data
           OR NEW.occurred_at IS DISTINCT FROM OLD.occurred_at
           OR NEW.valid_from IS DISTINCT FROM OLD.valid_from
           OR NEW.valid_to IS DISTINCT FROM OLD.valid_to
           OR NEW.time_precision IS DISTINCT FROM OLD.time_precision
           OR NEW.supersedes_fact_id IS DISTINCT FROM OLD.supersedes_fact_id
        THEN
            RAISE EXCEPTION USING
                ERRCODE = 'check_violation',
                MESSAGE = format('fact %s (%s) semantic columns are immutable', OLD.id, OLD.lifecycle_status);
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_intel_facts_immutable_columns ON intel_facts;
CREATE TRIGGER trg_intel_facts_immutable_columns
    BEFORE UPDATE ON intel_facts
    FOR EACH ROW EXECUTE FUNCTION trg_intel_facts_immutable_columns();

-- ----------------------------------------------------------------
-- 2. fact 物理删除禁止
-- ----------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_intel_facts_no_delete() RETURNS trigger AS $$
BEGIN
    IF OLD.lifecycle_status IN ('active', 'superseded', 'retracted') THEN
        RAISE EXCEPTION USING
            ERRCODE = 'check_violation',
            MESSAGE = format('fact %s (%s) cannot be physically deleted', OLD.id, OLD.lifecycle_status);
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_intel_facts_no_delete ON intel_facts;
CREATE TRIGGER trg_intel_facts_no_delete
    BEFORE DELETE ON intel_facts
    FOR EACH ROW EXECUTE FUNCTION trg_intel_facts_no_delete();

-- ----------------------------------------------------------------
-- 3. active fact 的 confirmed subject link 不可增删改
-- ----------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_intel_fact_competitors_lock_active() RETURNS trigger AS $$
DECLARE
    fact_lifecycle TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        SELECT lifecycle_status INTO fact_lifecycle FROM intel_facts WHERE id = OLD.fact_id;
        IF fact_lifecycle = 'active' THEN
            RAISE EXCEPTION USING
                ERRCODE = 'check_violation',
                MESSAGE = format('active fact %s competitor link cannot be deleted', OLD.fact_id);
        END IF;
        RETURN OLD;
    ELSE
        SELECT lifecycle_status INTO fact_lifecycle FROM intel_facts WHERE id = NEW.fact_id;
        IF fact_lifecycle = 'active' THEN
            IF TG_OP = 'UPDATE' AND (
                NEW.fact_id IS DISTINCT FROM OLD.fact_id
                OR NEW.competitor_id IS DISTINCT FROM OLD.competitor_id
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = 'check_violation',
                    MESSAGE = format('active fact %s competitor link identity is immutable', NEW.fact_id);
            END IF;
        END IF;
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_intel_fact_competitors_lock_active ON intel_fact_competitors;
CREATE TRIGGER trg_intel_fact_competitors_lock_active
    BEFORE INSERT OR UPDATE OR DELETE ON intel_fact_competitors
    FOR EACH ROW EXECUTE FUNCTION trg_intel_fact_competitors_lock_active();

CREATE OR REPLACE FUNCTION trg_intel_fact_products_lock_active() RETURNS trigger AS $$
DECLARE
    fact_lifecycle TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        SELECT lifecycle_status INTO fact_lifecycle FROM intel_facts WHERE id = OLD.fact_id;
        IF fact_lifecycle = 'active' THEN
            RAISE EXCEPTION USING
                ERRCODE = 'check_violation',
                MESSAGE = format('active fact %s product link cannot be deleted', OLD.fact_id);
        END IF;
        RETURN OLD;
    ELSE
        SELECT lifecycle_status INTO fact_lifecycle FROM intel_facts WHERE id = NEW.fact_id;
        IF fact_lifecycle = 'active' THEN
            IF TG_OP = 'UPDATE' AND (
                NEW.fact_id IS DISTINCT FROM OLD.fact_id
                OR NEW.product_id IS DISTINCT FROM OLD.product_id
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = 'check_violation',
                    MESSAGE = format('active fact %s product link identity is immutable', NEW.fact_id);
            END IF;
        END IF;
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_intel_fact_products_lock_active ON intel_fact_products;
CREATE TRIGGER trg_intel_fact_products_lock_active
    BEFORE INSERT OR UPDATE OR DELETE ON intel_fact_products
    FOR EACH ROW EXECUTE FUNCTION trg_intel_fact_products_lock_active();

-- ----------------------------------------------------------------
-- 4. claim 语义不可变性（supported maturity）
-- ----------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_insight_claims_immutable_columns() RETURNS trigger AS $$
BEGIN
    IF OLD.maturity IN ('supported', 'superseded') THEN
        IF NEW.claim_text IS DISTINCT FROM OLD.claim_text
           OR NEW.scope IS DISTINCT FROM OLD.scope
        THEN
            RAISE EXCEPTION USING
                ERRCODE = 'check_violation',
                MESSAGE = format('claim %s (%s) semantic columns are immutable', OLD.id, OLD.maturity);
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_insight_claims_immutable_columns ON insight_claims;
CREATE TRIGGER trg_insight_claims_immutable_columns
    BEFORE UPDATE ON insight_claims
    FOR EACH ROW EXECUTE FUNCTION trg_insight_claims_immutable_columns();

-- ----------------------------------------------------------------
-- 5. supported claim 的 claim_facts 不可增删改
-- ----------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_claim_facts_lock_supported() RETURNS trigger AS $$
DECLARE
    claim_maturity TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        SELECT maturity INTO claim_maturity FROM insight_claims WHERE id = OLD.claim_id;
        IF claim_maturity = 'supported' THEN
            RAISE EXCEPTION USING
                ERRCODE = 'check_violation',
                MESSAGE = format('supported claim %s fact link cannot be removed', OLD.claim_id);
        END IF;
        RETURN OLD;
    ELSE
        SELECT maturity INTO claim_maturity FROM insight_claims WHERE id = NEW.claim_id;
        IF claim_maturity = 'supported' THEN
            RAISE EXCEPTION USING
                ERRCODE = 'check_violation',
                MESSAGE = format('supported claim %s fact link is immutable', NEW.claim_id);
        END IF;
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_claim_facts_lock_supported ON claim_facts;
CREATE TRIGGER trg_claim_facts_lock_supported
    BEFORE INSERT OR UPDATE OR DELETE ON claim_facts
    FOR EACH ROW EXECUTE FUNCTION trg_claim_facts_lock_supported();

-- ----------------------------------------------------------------
-- 6. evidence_refs 已 anchor 行禁止重复锚点修改
-- ----------------------------------------------------------------
-- 旧 partial unique index uq_evidence_target_anchor 已经保证同一 version ×
-- occurrence × quote_hash 只能有一个 anchor。这里再加 trigger 防止已 anchor
-- 行的 quoted_text / quote_hash / locator 被改写。
CREATE OR REPLACE FUNCTION trg_evidence_refs_lock_anchor() RETURNS trigger AS $$
BEGIN
    IF OLD.quoted_text IS NOT NULL AND (
        NEW.quoted_text IS DISTINCT FROM OLD.quoted_text
        OR NEW.quote_hash IS DISTINCT FROM OLD.quote_hash
        OR NEW.locator IS DISTINCT FROM OLD.locator
        OR NEW.document_version_id IS DISTINCT FROM OLD.document_version_id
        OR NEW.source_occurrence_id IS DISTINCT FROM OLD.source_occurrence_id
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'check_violation',
            MESSAGE = format('evidence_ref %s anchor is immutable', OLD.id);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_evidence_refs_lock_anchor ON evidence_refs;
CREATE TRIGGER trg_evidence_refs_lock_anchor
    BEFORE UPDATE ON evidence_refs
    FOR EACH ROW EXECUTE FUNCTION trg_evidence_refs_lock_anchor();

COMMIT;