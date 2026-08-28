-- ============================================================
-- 阶段 5 数据库迁移：调度器执行记录 + 分片状态 + 盘后 ETL
--
-- 新增三张表：
--   1. scheduler_runs   每次任务执行的记录（开始/结束/状态/耗时/摘要/错误/进度）
--   2. scheduler_shards 分片断点续跑状态（长任务中断后跳过已完成的分片）
--   3. sector_fund_flow / etf_fund_flow / st_snapshot  盘后 ETL 落库
--
-- 该迁移在 0003_backtest_runs.sql 之后按文件名顺序自动执行。
-- ============================================================

USE stock_platform;

-- ------------------------------------------------------------
-- 1. 调度器执行记录表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scheduler_runs (
    run_id           VARCHAR(36)  NOT NULL COMMENT '执行 id（UUID）',
    job_name         VARCHAR(64)  NOT NULL COMMENT '任务名',
    trigger_type     VARCHAR(16)  NOT NULL DEFAULT 'schedule' COMMENT '触发方式：schedule / manual',
    status           VARCHAR(16)  NOT NULL COMMENT '执行状态：success / failed / timeout / skipped',
    started_at       DATETIME     NOT NULL COMMENT '开始时间（Asia/Shanghai）',
    finished_at      DATETIME     NULL COMMENT '结束时间',
    duration_seconds FLOAT        NULL COMMENT '耗时（秒）',
    progress         FLOAT        NULL COMMENT '进度 0~1',
    summary          VARCHAR(512) NOT NULL DEFAULT '' COMMENT '输出摘要（截断）',
    error            VARCHAR(2048) NOT NULL DEFAULT '' COMMENT '错误堆栈（截断）',
    attempt          INT          NOT NULL DEFAULT 0 COMMENT '第几次尝试（0 起）',
    PRIMARY KEY (run_id),
    KEY idx_job_started (job_name, started_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '调度器任务执行记录';

-- ------------------------------------------------------------
-- 2. 分片断点续跑状态表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scheduler_shards (
    job_name  VARCHAR(64) NOT NULL COMMENT '任务名',
    batch_key VARCHAR(32) NOT NULL COMMENT '批次标识（通常为交易日 YYYY-MM-DD）',
    shard_id  INT         NOT NULL COMMENT '分片序号（0 起）',
    created_at TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_name, batch_key, shard_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '分片断点续跑状态（已完成的分片）';

-- ------------------------------------------------------------
-- 3a. 板块资金流（东方财富行业资金流排名）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sector_fund_flow (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    trade_date       DATE        NOT NULL COMMENT '交易日',
    name             VARCHAR(64) NOT NULL COMMENT '板块名',
    change_pct       FLOAT       NULL COMMENT '当日涨跌幅（%）',
    main_net_inflow  FLOAT       NULL COMMENT '主力净流入-净额（元）',
    main_net_ratio   FLOAT       NULL COMMENT '主力净流入-净占比（%）',
    super_net_inflow FLOAT       NULL COMMENT '超大单净流入（元）',
    large_net_inflow FLOAT       NULL COMMENT '大单净流入（元）',
    medium_net_inflow FLOAT      NULL COMMENT '中单净流入（元）',
    small_net_inflow FLOAT       NULL COMMENT '小单净流入（元）',
    leading_stock    VARCHAR(64) NOT NULL DEFAULT '' COMMENT '主力净流入最大股',
    created_at       TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_sector_date (trade_date, name),
    KEY idx_sector_date (trade_date)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '板块资金流（盘后 ETL）';

-- ------------------------------------------------------------
-- 3b. ETF 资金流（场内 ETF 主力净流入）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etf_fund_flow (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    trade_date       DATE        NOT NULL COMMENT '交易日',
    code             VARCHAR(16) NOT NULL COMMENT 'ETF 代码',
    name             VARCHAR(64) NOT NULL COMMENT 'ETF 名称',
    amount           FLOAT       NULL COMMENT '成交额（元）',
    main_net_inflow  FLOAT       NULL COMMENT '主力净流入-净额（元）',
    main_net_ratio   FLOAT       NULL COMMENT '主力净流入-净占比（%）',
    change_pct       FLOAT       NULL COMMENT '当日涨跌幅（%）',
    created_at       TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_etf_date (trade_date, code),
    KEY idx_etf_date (trade_date)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = 'ETF 资金流（盘后 ETL，etf_accumulation 连续净流入数据源）';

-- ------------------------------------------------------------
-- 3c. ST 名单快照
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS st_snapshot (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    trade_date  DATE        NOT NULL COMMENT '快照日',
    code        VARCHAR(16) NOT NULL COMMENT '股票代码',
    name        VARCHAR(64) NOT NULL COMMENT '股票名称（ST / *ST）',
    created_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_st_date (trade_date, code),
    KEY idx_st_date (trade_date)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = 'ST 名单快照（供 strategies.filters 的 ST 过滤）';
