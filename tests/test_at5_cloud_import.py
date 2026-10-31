"""[AT-5] 云端取数：网络预检认出云端、直连被拦时指向 WebFetch，导入的快照和抓取的一样能用。

技能端到端那一段（WebFetch → 导入 → 报告页发布）是半自动验收，由你看报告页确认；
这里自动检查它依赖的程序部分。测试在断网下跑（pytest-socket），所以所有来源都连不上。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from stockdesk.cli.main import main

from conftest import CASES, ROOT, CliResult, run_cli

CLOUD = {"CLAUDE_CODE_REMOTE": "true"}
INTC = CASES / "intc-q3-2026" / "snapshots" / "INTC"
SNAPSHOT_KEYS = {"ticker", "field", "period", "value", "unit", "source_url", "as_of", "fetched_at", "via",
                 "gap_ack", "note"}


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    """一个干净的工作目录：只有 config/，data/ 是空的。"""
    shutil.copytree(ROOT / "config", tmp_path / "config")
    return tmp_path


@pytest.fixture
def sd(ws, monkeypatch, capsys):
    """在本进程里跑 sd（这样断网设置对它生效），工作目录是 ws。"""

    def run(*args: str, env: dict[str, str] | None = None) -> CliResult:
        monkeypatch.chdir(ws)
        monkeypatch.delenv("STOCKDESK_DATA", raising=False)
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
        code = main(list(args))
        out = capsys.readouterr()
        return CliResult(code, out.out, out.err)

    return run


def snapshot_files(ws: Path, ticker: str) -> list[Path]:
    folder = ws / "data" / "snapshots" / ticker
    return sorted(folder.rglob("*.json")) if folder.exists() else []


# ---------- 网络预检与直连 ----------

def test_doctor_recognises_cloud_and_points_to_webfetch(sd, ws):
    res = sd("doctor", "--json", env=CLOUD)
    assert res.code == 0, res.stderr
    prof = res.json()
    assert prof["environment"] == "cloud"
    assert prof["can_fetch"] is False
    assert {"yahoo", "sec", "hkex", "fred", "stockanalysis"} <= set(prof["sources"])
    assert not any(s["reachable"] for s in prof["sources"].values())
    assert "WebFetch" in prof["advice"] and "sd import" in prof["advice"]
    saved = json.loads((ws / "data" / "network-profile.json").read_text(encoding="utf-8"))
    assert saved["environment"] == "cloud"


def test_doctor_never_prints_the_sec_contact(sd):
    res = sd("doctor", "--json", env={**CLOUD, "STOCKDESK_SEC_CONTACT": "Test Person test-contact@example.com"})
    assert "test-contact@example.com" not in res.stdout + res.stderr
    assert res.json()["sec_contact"] == "set"


def test_fetch_in_cloud_is_blocked_with_next_step(sd, ws):
    res = sd("fetch", "INTC", "--json", env=CLOUD)
    assert res.code == 1
    err = res.json()["error"]
    assert err["code"] == "SOURCE_BLOCKED"
    assert "WebFetch" in err["next_step"] and "sd import" in err["next_step"]
    assert set(err["details"]["blocked"]) >= {"yahoo", "sec", "stockanalysis"}
    assert snapshot_files(ws, "INTC") == [], "什么都没取到时不写快照"


def test_human_output_of_blocked_fetch_says_what_to_do(sd):
    res = sd("fetch", "0992.HK", env=CLOUD)
    assert res.code == 1
    assert "SOURCE_BLOCKED" in res.stderr and "WebFetch" in res.stderr


# ---------- 导入 ----------

def import_case(sd, files: list[Path]) -> list[dict]:
    refs = []
    for f in files:
        res = sd("import", "INTC", str(f), "--json")
        assert res.code == 0, res.stdout + res.stderr
        refs.append(res.json())
    return refs


def test_imported_snapshot_has_the_same_format_as_fetch(sd, ws):
    refs = import_case(sd, [INTC / "2026-10-29-press-release.json"])
    path = Path(refs[0]["path"])
    assert path.is_relative_to(ws / "data" / "snapshots" / "INTC")
    records = json.loads(path.read_text(encoding="utf-8"))
    assert records and all(set(r) == SNAPSHOT_KEYS for r in records)
    assert all(r["via"] == "import" for r in records)
    assert refs[0]["facts"] == len(records)


def test_import_then_pack_and_zones_match_replay(sd, ws):
    import_case(sd, sorted(INTC.glob("*.json")))
    replay = run_cli("pack", "INTC", "--quarter", "2026Q3", "--replay", "intc-q3-2026", "--json").json()
    res = sd("pack", "INTC", "--quarter", "2026Q3", "--as-of", "2026-10-29", "--json")
    assert res.code == 0, res.stdout + res.stderr
    assert res.json()["pack_hash"] == replay["pack_hash"]

    want = run_cli("zones", "INTC", "--replay", "intc-q3-2026", "--eps", "1.75", "--pe", "38-45", "--json").json()
    res = sd("zones", "INTC", "--as-of", "2026-10-29", "--eps", "1.75", "--pe", "38-45",
             "--earnings-date", "2026-10-29", "--json")
    assert res.code == 0, res.stdout + res.stderr
    got = res.json()
    assert [(t["low"], t["high"]) for t in got["tiers"]] == [(t["low"], t["high"]) for t in want["tiers"]]


def test_import_is_append_only(sd, ws):
    first = import_case(sd, [INTC / "2026-10-29-press-release.json"])[0]
    before = Path(first["path"]).read_bytes()
    second = import_case(sd, [INTC / "2026-10-29-press-release.json"])[0]
    assert first["path"] != second["path"]
    assert Path(first["path"]).read_bytes() == before


def test_recent_bars_extend_older_bars(sd, ws, tmp_path):
    """云端只抓得到最近几天的日线：导入后要和早先的日线拼起来，每天的来源各自保留。"""
    bars = json.loads((INTC / "2026-10-29-bars.json").read_text(encoding="utf-8"))
    older = {**bars, "as_of": "2026-10-28", "rows": [r for r in bars["rows"] if r[0] <= "2026-10-28"]}
    recent = {**bars, "as_of": "2026-10-29", "rows": [r for r in bars["rows"] if r[0] >= "2026-10-27"],
              "source_url": "https://stockanalysis.com/stocks/intc/history/", "via": "import"}
    for name, body in (("older.json", older), ("recent.json", recent)):
        (tmp_path / name).write_text(json.dumps(body), encoding="utf-8")
        res = sd("import", "INTC", str(tmp_path / name), "--json")
        assert res.code == 0, res.stdout + res.stderr
    for f in ("2026-10-29-price.json", "2026-10-29-after-hours.json", "2026-10-30-pe-history.json",
              "2026-10-30-peers.json"):
        assert sd("import", "INTC", str(INTC / f), "--json").code == 0
    res = sd("zones", "INTC", "--as-of", "2026-10-29", "--eps", "1.75", "--pe", "38-45",
             "--earnings-date", "2026-10-29", "--json")
    assert res.code == 0, res.stdout + res.stderr
    tech = res.json()["tech"]
    assert tech["last_close"]["date"] == "2026-10-29"
    ranges = tech["source"]["ranges"]
    assert ranges[-1] == {"url": "https://stockanalysis.com/stocks/intc/history/", "from": "2026-10-27",
                          "to": "2026-10-29"}
    assert ranges[0]["url"] == bars["source_url"] and ranges[0]["to"] == "2026-10-26"


def test_gap_ack_registers_a_missing_field(sd, ws):
    import_case(sd, [f for f in sorted(INTC.glob("*.json")) if "peers" not in f.name])
    args = ("zones", "INTC", "--as-of", "2026-10-29", "--eps", "1.75", "--pe", "38-45", "--earnings-date",
            "2026-10-29", "--json")
    res = sd(*args)
    assert res.json()["error"]["code"] == "DATA_INCOMPLETE"
    assert [g["field"] for g in res.json()["error"]["details"]["gaps"]] == ["peer_pe"]

    res = sd("import", "INTC", "--gap-ack", "peer_pe=同行 PE 这次没取到", "--as-of", "2026-10-29", "--json")
    assert res.code == 0, res.stdout + res.stderr
    res = sd(*args)
    assert res.code == 0, res.stdout + res.stderr
    assert res.json()["valuation"]["peers"]["missing"] is True


# ---------- 导入时的校验：错了就整份拒绝，什么都不写 ----------

GOOD = {
    "ticker": "INTC", "field": "revenue", "period": "2026Q3", "value": 16_500_000_000, "unit": "USD",
    "source_url": "https://www.sec.gov/Archives/edgar/data/50863/000005086326000046/q3-26pressrelease.htm",
    "as_of": "2026-09-27", "fetched_at": "2026-10-30T08:00:00Z",
}

BAD = [
    ("abbreviated_amount", {"value": "16.5B"}, "16500000000"),
    ("amount_in_billions", {"value": 16.5}, "不缩写"),
    ("percent_not_decimal", {"field": "gross_margin_gaap", "unit": "ratio", "value": 44.1}, "小数"),
    ("no_source", {"source_url": ""}, "source_url"),
    ("bad_date", {"as_of": "2026/09/27"}, "as_of"),
    ("future_date", {"as_of": "2099-01-01"}, "as_of"),
    ("unknown_unit", {"unit": "billions"}, "unit"),
    ("null_without_ack", {"value": None}, "gap_ack"),
    ("bad_period", {"period": "Q3 2026"}, "period"),
    ("wrong_ticker", {"ticker": "AMD"}, "ticker"),
]


@pytest.mark.parametrize(("name", "change", "hint"), BAD, ids=[b[0] for b in BAD])
def test_import_rejects_bad_rows(sd, ws, tmp_path, name, change, hint):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps([GOOD, {**GOOD, "field": "eps_gaap", "unit": "USD/share", "value": 0.6},
                                {**GOOD, **change}]), encoding="utf-8")
    res = sd("import", "INTC", str(path), "--json")
    assert res.code == 1
    err = res.json()["error"]
    assert err["code"] == "BAD_INPUT"
    problem = err["details"]["problems"][0]
    assert problem["row"] == 2
    assert hint in problem["message"]
    assert snapshot_files(ws, "INTC") == [], "有一行错就整份不写"


def test_good_rows_pass_validation(sd, ws, tmp_path):
    path = tmp_path / "good.json"
    path.write_text(json.dumps([GOOD, {**GOOD, "field": "gross_margin_gaap", "unit": "ratio", "value": 0.375},
                                {**GOOD, "field": "revenue_yoy", "unit": "ratio", "value": 1.76}]),
                    encoding="utf-8")
    res = sd("import", "INTC", str(path), "--json")
    assert res.code == 0, res.stdout
    assert res.json()["facts"] == 3


def test_data_dir_can_be_shared_between_sessions(sd, ws, tmp_path):
    shared = tmp_path / "shared-data"
    res = sd("import", "INTC", str(INTC / "2026-10-29-press-release.json"), "--json",
             env={"STOCKDESK_DATA": str(shared)})
    assert res.code == 0, res.stdout + res.stderr
    assert Path(res.json()["path"]).is_relative_to(shared / "snapshots" / "INTC")
