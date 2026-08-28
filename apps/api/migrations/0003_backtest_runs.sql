-- ============================================================
-- 阶段 4 数据库迁移：回测任务与结果落库
--
-- 新增表 backtest_runs，记录每次回测的参数与结果（JSON），
-- 支持 POST /api/v1/backtest/runs 发起、GET /api/v1/backtest/runs/{id} 查询。
-- 该迁移在 0002_strategy_scans.sql 之后按文件名顺序自动执行。
-- ============================================================

USE stock_platform;

-- ------------------------------------------------------------
-- 回测任务表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS backtest_runs (
    id           VARCHAR(36)  NOT NULL COMMENT '回测任务 id（UUID）',
    strategy     VARCHAR(32)  NULL COMMENT '策略名，NULL=全部策略',
    start_date   DATE         NOT NULL COMMENT '回测起始日',
    end_date     DATE         NOT NULL COMMENT '回测结束日',
    mode         VARCHAR(16)  NOT NULL DEFAULT 'verify' COMMENT '回测模式：verify / portfolio',
    hold_days    VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '持有期列表，逗号分隔，如 1,3,5,10,20',
    result_json  JSON         NOT NULL COMMENT '回测报告（验证/组合/衰减）完整 JSON',
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_strategy (strategy),
    KEY idx_created_at (created_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '回测任务与结果';
