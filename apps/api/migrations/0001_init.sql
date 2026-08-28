-- ============================================================
-- 阶段 1 数据库初始化脚本（MySQL 8）
-- 两张表：
--   1) daily_bars       日线数据（阶段 2 ETL 从 hsjday 灌入）
--   2) indicator_cache  指标计算结果缓存（阶段 2 起用，避免重复计算）
-- 说明：阶段 1 API 直接从本地 hsjday 文件读，不依赖本表；建表是为
--       阶段 2 的数据通道预留 schema，先用纯 SQL 脚本，简单为准。
-- ============================================================

-- 用 utf8mb4 统一编码，避免中文/特殊字符乱码
CREATE DATABASE IF NOT EXISTS stock_platform
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE stock_platform;

-- ------------------------------------------------------------
-- 日线数据表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_bars (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol      VARCHAR(16)  NOT NULL COMMENT '6 位代码，如 600519',
    market      VARCHAR(4)   NOT NULL COMMENT '交易所：sh/sz/bj',
    trade_date  DATE         NOT NULL COMMENT '交易日',
    open        DECIMAL(12,3) NOT NULL COMMENT '开盘价（元）',
    high        DECIMAL(12,3) NOT NULL COMMENT '最高价（元）',
    low         DECIMAL(12,3) NOT NULL COMMENT '最低价（元）',
    close       DECIMAL(12,3) NOT NULL COMMENT '收盘价（元）',
    volume      BIGINT       NOT NULL COMMENT '成交量（手）',
    amount      DECIMAL(18,2) NOT NULL COMMENT '成交额（元）',
    adjust_mode VARCHAR(16)  NOT NULL DEFAULT 'none' COMMENT '复权：forward/backward/none',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_symbol_date (symbol, trade_date, adjust_mode),
    KEY idx_symbol (symbol)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '日线行情数据';

-- ------------------------------------------------------------
-- 指标计算缓存表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS indicator_cache (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    symbol        VARCHAR(16) NOT NULL COMMENT '6 位代码',
    trade_date    DATE        NOT NULL COMMENT '指标对应的交易日',
    indicator     VARCHAR(32) NOT NULL COMMENT '指标名，如 macd',
    params        VARCHAR(128) NOT NULL DEFAULT '' COMMENT '参数 JSON，如 {"fast":12}',
    value_json    JSON        NOT NULL COMMENT '指标数值 JSON，如 {"dif":1.2,"dea":0.9,"macd":0.6}',
    computed_at   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_symbol_indicator (symbol, trade_date, indicator, params)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '指标计算结果缓存';
