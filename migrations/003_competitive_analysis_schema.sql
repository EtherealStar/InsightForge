-- 003: InsightForge 竞品分析 Schema 扩展
-- 在 document-first 基础上，新增竞品管理、情报关联与分析报告能力。

BEGIN;

-- ============================================================
-- 1. 竞品公司表
-- ============================================================
CREATE TABLE IF NOT EXISTS competitors (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    aliases         JSONB DEFAULT '[]'::jsonb,
    website         TEXT DEFAULT '',
    industry        TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    logo_url        TEXT DEFAULT '',
    tags            JSONB DEFAULT '[]'::jsonb,
    status          TEXT DEFAULT 'active',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE  competitors IS '竞品公司档案';
COMMENT ON COLUMN competitors.aliases IS '别名/简称 JSON 数组，用于自动关联';
COMMENT ON COLUMN competitors.status IS 'active=监控中, archived=已归档';

-- ============================================================
-- 2. 竞品产品线表
-- ============================================================
CREATE TABLE IF NOT EXISTS competitor_products (
    id              SERIAL PRIMARY KEY,
    competitor_id   INT NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    category        TEXT DEFAULT '',
    url             TEXT DEFAULT '',
    pricing_info    TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE  competitor_products IS '竞品产品线';
COMMENT ON COLUMN competitor_products.category IS '产品类别（如 IDE插件、独立IDE）';
COMMENT ON COLUMN competitor_products.pricing_info IS '定价信息摘要';

-- ============================================================
-- 3. source_documents 表新增竞品情报字段
-- ============================================================
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS intel_type          TEXT DEFAULT 'general';
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS source_reliability  FLOAT DEFAULT 0.0;
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS analysis_notes      TEXT DEFAULT '';

COMMENT ON COLUMN source_documents.intel_type IS '情报类型: pricing/feature/strategy/partnership/hiring/funding/market/review/general';
COMMENT ON COLUMN source_documents.source_reliability IS '来源可信度 0.0~1.0';
COMMENT ON COLUMN source_documents.analysis_notes IS 'AI 分析批注';

-- ============================================================
-- 4. 情报-竞品关联表 (多对多)
-- ============================================================
CREATE TABLE IF NOT EXISTS intel_competitors (
    document_id     UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    competitor_id   INT NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, competitor_id)
);

COMMENT ON TABLE intel_competitors IS '情报与竞品的多对多关联';

-- ============================================================
-- 5. 情报-产品关联表 (多对多)
-- ============================================================
CREATE TABLE IF NOT EXISTS intel_products (
    document_id     UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    product_id      INT NOT NULL REFERENCES competitor_products(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, product_id)
);

COMMENT ON TABLE intel_products IS '情报与竞品产品的多对多关联';

-- ============================================================
-- 6. 分析报告表
-- ============================================================
CREATE TABLE IF NOT EXISTS analysis_reports (
    id              SERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    report_type     TEXT NOT NULL DEFAULT 'overview',
    competitor_ids  JSONB DEFAULT '[]'::jsonb,
    content         TEXT DEFAULT '',
    source_refs     JSONB DEFAULT '[]'::jsonb,
    audit_trail     JSONB DEFAULT '[]'::jsonb,
    status          TEXT DEFAULT 'draft',
    session_id      TEXT,
    report_filename TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE  analysis_reports IS '竞品分析报告';
COMMENT ON COLUMN analysis_reports.report_type IS 'overview/comparison/briefing/deep_research';
COMMENT ON COLUMN analysis_reports.source_refs IS '溯源引用列表 JSON 数组';
COMMENT ON COLUMN analysis_reports.audit_trail IS '生成链路审计 JSON 数组';
COMMENT ON COLUMN analysis_reports.session_id IS '生成此报告的 Agent 会话 ID';

-- ============================================================
-- 7. 分析审计日志表（溯源与可观测性）
-- ============================================================
CREATE TABLE IF NOT EXISTS analysis_audit_log (
    id              SERIAL PRIMARY KEY,
    report_id       INT REFERENCES analysis_reports(id) ON DELETE SET NULL,
    session_id      TEXT,
    action          TEXT NOT NULL,
    detail          JSONB DEFAULT '{}'::jsonb,
    source_refs     JSONB DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE  analysis_audit_log IS '分析审计日志（溯源与可观测性）';
COMMENT ON COLUMN analysis_audit_log.action IS 'intel_collected/tool_called/conclusion_drawn/report_generated';

-- ============================================================
-- 8. 索引
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_source_documents_intel_type ON source_documents(intel_type);
CREATE INDEX IF NOT EXISTS idx_intel_competitors_competitor ON intel_competitors(competitor_id);
CREATE INDEX IF NOT EXISTS idx_intel_products_product ON intel_products(product_id);
CREATE INDEX IF NOT EXISTS idx_competitors_status ON competitors(status);
CREATE INDEX IF NOT EXISTS idx_analysis_reports_type ON analysis_reports(report_type);
CREATE INDEX IF NOT EXISTS idx_analysis_reports_status ON analysis_reports(status);
CREATE INDEX IF NOT EXISTS idx_analysis_audit_log_report ON analysis_audit_log(report_id);
CREATE INDEX IF NOT EXISTS idx_analysis_audit_log_session ON analysis_audit_log(session_id);

COMMIT;
