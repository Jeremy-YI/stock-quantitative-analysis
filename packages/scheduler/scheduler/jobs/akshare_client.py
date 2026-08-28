"""AKShare 数据客户端（盘后 ETL 专用）。

严格遵守架构决策：**AKShare 只在盘后 ETL 用，策略层永远只读本地库**。策略层
不 import 本模块；本模块把外部数据拉下来、规范化、落 MySQL，策略层后续从库读。

``AkshareClient`` 是协议，``AkshareLiveClient`` 是真实实现（延迟 import akshare，
避免无网络/未安装时 import 报错）。单测注入 Fake，绝不真打外部网络。
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class AkshareClient(Protocol):
    """AKShare 数据源接口（可被 Fake 替换）。"""

    def fetch_sector_flow(self) -> pd.DataFrame:
        """拉取当日行业板块资金流排名（东方财富口径）。

        返回规范化的 DataFrame，列：name / change_pct / main_net_inflow /
        main_net_ratio / super_net_inflow / large_net_inflow / medium_net_inflow /
        small_net_inflow / leading_stock。
        """
        ...

    def fetch_etf_flow(self) -> pd.DataFrame:
        """拉取当日场内 ETF 行情 + 主力资金流（东方财富口径）。

        返回规范化的 DataFrame，列：code / name / amount / main_net_inflow /
        main_net_ratio / change_pct。
        """
        ...

    def fetch_st_list(self) -> pd.DataFrame:
        """拉取 A股 ST / *ST 名单快照。

        返回规范化 DataFrame，列：code / name。
        """
        ...


def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


class AkshareLiveClient:
    """真实 AKShare 客户端（延迟 import）。"""

    def __init__(self) -> None:
        self._ak = None

    def _get_ak(self):
        if self._ak is None:
            try:
                import akshare as ak  # 延迟导入，避免未安装时报错
            except ImportError as exc:
                raise RuntimeError(
                    "akshare 未安装：pip install akshare（仅盘后 ETL 需要，策略层不依赖）"
                ) from exc
            self._ak = ak
        return self._ak

    def fetch_sector_flow(self) -> pd.DataFrame:  # pragma: no cover - 真实网络
        ak = self._get_ak()
        raw = ak.stock_sector_fund_flow_rank(
            indicator="今日", sector_type="行业资金流"
        )
        return _normalize_sector_flow(raw)

    def fetch_etf_flow(self) -> pd.DataFrame:  # pragma: no cover - 真实网络
        ak = self._get_ak()
        raw = ak.fund_etf_spot_em()
        return _normalize_etf_flow(raw)

    def fetch_st_list(self) -> pd.DataFrame:  # pragma: no cover - 真实网络
        ak = self._get_ak()
        # 优先用官方 ST 名单；该接口（push2.eastmoney）在某些网络下被拒，
        # 退回到全 A股名单按名称过滤 ST。
        try:
            raw = ak.stock_zh_a_st_em()
            if raw is not None and not raw.empty:
                return pd.DataFrame(
                    {"code": raw["代码"].astype(str), "name": raw["名称"].astype(str)}
                )
        except Exception:  # noqa: BLE001 — 降级到备用接口
            pass

        raw = ak.stock_info_a_code_name()
        st = raw[raw["name"].str.contains("ST", na=False)].copy()
        return pd.DataFrame(
            {"code": st["code"].astype(str), "name": st["name"].astype(str)}
        )


def _normalize_sector_flow(raw: pd.DataFrame) -> pd.DataFrame:
    """把 AKShare 行业资金流原始列名规范成统一列（金额单位：元）。"""
    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=[
                "name", "change_pct", "main_net_inflow", "main_net_ratio",
                "super_net_inflow", "large_net_inflow", "medium_net_inflow",
                "small_net_inflow", "leading_stock",
            ]
        )
    df = raw.copy()
    name = "名称" if "名称" in df.columns else df.columns[1]
    change = _pick(df, ["今日涨跌幅", "涨跌幅"])
    main_net = _pick(df, ["今日主力净流入-净额", "主力净流入-净额"])
    main_ratio = _pick(df, ["今日主力净流入-净占比", "主力净流入-净占比"])
    super_net = _pick(df, ["今日超大单净流入-净额", "超大单净流入-净额"])
    large_net = _pick(df, ["今日大单净流入-净额", "大单净流入-净额"])
    medium_net = _pick(df, ["今日中单净流入-净额", "中单净流入-净额"])
    small_net = _pick(df, ["今日小单净流入-净额", "小单净流入-净额"])
    leading = _pick(df, ["今日主力净流入最大股", "主力净流入最大股"])

    out = pd.DataFrame({"name": df[name].astype(str)})
    out["change_pct"] = _to_float(df[change]) if change else float("nan")
    out["main_net_inflow"] = _to_float(df[main_net]) if main_net else float("nan")
    out["main_net_ratio"] = _to_float(df[main_ratio]) if main_ratio else float("nan")
    out["super_net_inflow"] = _to_float(df[super_net]) if super_net else float("nan")
    out["large_net_inflow"] = _to_float(df[large_net]) if large_net else float("nan")
    out["medium_net_inflow"] = _to_float(df[medium_net]) if medium_net else float("nan")
    out["small_net_inflow"] = _to_float(df[small_net]) if small_net else float("nan")
    out["leading_stock"] = df[leading].astype(str) if leading else ""
    return out


def _normalize_etf_flow(raw: pd.DataFrame) -> pd.DataFrame:
    """把 AKShare ETF 实时行情原始列名规范成统一列（金额单位：元）。"""
    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=[
                "code", "name", "amount", "main_net_inflow",
                "main_net_ratio", "change_pct",
            ]
        )
    df = raw.copy()
    code = "代码" if "代码" in df.columns else df.columns[0]
    name = "名称" if "名称" in df.columns else df.columns[1]
    amount = _pick(df, ["成交额"])
    main_net = _pick(df, ["主力净流入-净额"])
    main_ratio = _pick(df, ["主力净流入-净占比"])
    change = _pick(df, ["涨跌幅"])

    out = pd.DataFrame(
        {"code": df[code].astype(str), "name": df[name].astype(str)}
    )
    out["amount"] = _to_float(df[amount]) if amount else float("nan")
    out["main_net_inflow"] = _to_float(df[main_net]) if main_net else float("nan")
    out["main_net_ratio"] = _to_float(df[main_ratio]) if main_ratio else float("nan")
    out["change_pct"] = _to_float(df[change]) if change else float("nan")
    return out


def _pick(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """返回第一个存在的列名（原始列名在不同版本间可能不同）。"""
    for c in candidates:
        if c in df.columns:
            return c
    return None
