-- ============================================================
-- 阶段 3 数据库迁移：策略扫描结果落库
--
-- 新增表 strategy_scan_results，记录每个策略每天扫出的选股信号，
-- 支持按日期查询历史扫描结果（API: GET /strategies/{name}/signals）。
-- 该迁移在 0001_init.sql 之后按文件名顺序自动执行。
-- ============================================================

USE stock_platform;

-- ------------------------------------------------------------
-- 策略扫描结果表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS strategy_scan_results (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy      VARCHAR(32) NOT NULL COMMENT '策略名，如 b1b2b3 / macd_resonance',
    trade_date    DATE        NOT NULL COMMENT '扫描日（触发日）',
    symbol        VARCHAR(16) NOT NULL COMMENT '6 位代码，如 600519',
    signal_type   VARCHAR(32) NOT NULL COMMENT '信号子类型，如 b1 / b2 / pin30',
    score         DECIMAL(10,3) NOT NULL COMMENT '打分（用于排序）',
    metrics_json  JSON        NOT NULL COMMENT '指标明细（键值对）',
    created_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    -- 同一天同一策略同一标的同一信号只存一条（幂等，重跑扫描不产生重复）
    UNIQUE KEY uk_strategy_scan (strategy, trade_date, symbol, signal_type),
    KEY idx_strategy_date (strategy, trade_date)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '策略选股信号（按日历史）';
