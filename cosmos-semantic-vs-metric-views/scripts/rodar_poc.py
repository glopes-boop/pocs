"""Roda a POC: Cosmos de verdade (CLI) contra DuckDB, 3x por pergunta e por usuário, e compara
com o SQL equivalente às measures da Metric View (traduzido para SQL puro em DuckDB)."""
import json, os, shutil, subprocess, sys, hashlib, decimal
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
COSMOS = os.environ.get("COSMOS_BIN") or shutil.which("cosmos")
if not COSMOS:
    sys.exit("comando `cosmos` não encontrado: ative o venv ou defina COSMOS_BIN")
CDIR = ROOT / "cosmos"
RES = ROOT / "results"; RES.mkdir(exist_ok=True)
AUDIT = RES / "cosmos_audit.jsonl"
if AUDIT.exists(): AUDIT.unlink()
ENV = {**os.environ, "COSMOS_AUDIT_LOG": str(AUDIT), "COSMOS_DUCKDB_PATH": str(ROOT / "data/vendas.duckdb")}
AS_OF = "2026-10-31"

QUESTIONS = {
  "Q1_clientes_ativos": dict(metrics=["active_customers"], by=[], where=[]),
  "Q2_receitas_por_mes": dict(metrics=["gross_revenue","refunds_completed","net_revenue","average_order_value","refund_rate"],
                              by=["orders.ordered_at__month"], where=[]),
  "Q3_liquida_30_dias": dict(metrics=["net_revenue","gross_revenue"], by=[], where=["{orders.ordered_at} >= DATE '2026-10-02'"]),
  "Q4_ticket_por_regiao": dict(metrics=["average_order_value","refund_rate","paid_orders"], by=["customers.region"], where=[]),
  "Q5_liquida_por_dia_7d": dict(metrics=["gross_revenue","net_revenue"], by=["orders.ordered_at__day"], where=["{orders.ordered_at} >= DATE '2026-10-25'"]),
}
USERS = ["Varejo", "Middle", "Corporate"]

def cosmos(args, user=None, agent=False):
    cmd = [COSMOS, "query", *args, "-m", "semantic", "-c", "connections.yml", "--as-of", AS_OF, "--json"]
    if user: cmd += ["-u", f"carteira={user}"]
    if agent: cmd += ["--agent"]
    p = subprocess.run(cmd, cwd=CDIR, env=ENV, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

def args_for(q):
    a = list(q["metrics"])
    for b in q["by"]: a += ["--by", b]
    for w in q["where"]: a += ["--where", w]
    return a

out = {"as_of": AS_OF, "runs": {}, "denials": {}, "replay": None}
for qn, q in QUESTIONS.items():
    for u in USERS:
        runs = []
        for i in range(3):
            rc, so, se = cosmos(args_for(q), u)
            assert rc == 0, (qn, u, se)
            d = json.loads(so); e = d["evidence"]
            runs.append({"query_id": e["query_id"], "sql_hash": e["sql"]["hash"], "result_hash": e["result"]["hash"],
                         "model_hash": e["model_hash"], "rows": d["rows"]})
        key = f"{qn}|{u}"
        out["runs"][key] = {
            "stable": len({(r["sql_hash"], r["result_hash"], r["model_hash"]) for r in runs}) == 1,
            "sql_hash": runs[0]["sql_hash"], "result_hash": runs[0]["result_hash"], "model_hash": runs[0]["model_hash"],
            "query_ids": [r["query_id"] for r in runs], "rows": runs[0]["rows"]}
        if qn == "Q2_receitas_por_mes" and u == "Varejo":
            (RES / "cosmos_evidencia_Q2_Varejo.json").write_text(json.dumps(e, indent=2, ensure_ascii=False, default=str))
            (RES / "cosmos_sql_Q2.sql").write_text(e["sql"]["text"])
        if qn == "Q1_clientes_ativos" and u == "Corporate":
            (RES / "cosmos_evidencia_Q1_Corporate.json").write_text(json.dumps(e, indent=2, ensure_ascii=False, default=str))

# Negações
rc, so, se = cosmos(["net_revenue"])
out["denials"]["sem_claim"] = {"rc": rc, "msg": (se or so).strip()[-300:]}
rc, so, se = cosmos(["paid_orders", "--by", "customers.cnpj"], "Varejo", agent=True)
out["denials"]["agente_cnpj"] = {"rc": rc, "msg": (se or so).strip()[-300:]}
rc, so, se = cosmos(["paid_orders", "--by", "customers.cnpj", "--limit", "3"], "Varejo", agent=False)
out["denials"]["humano_cli_cnpj"] = {"rc": rc, "note": "mesma consulta fora do canal de agente", "ok": rc == 0}

# Replay de uma consulta auditada
qid = out["runs"]["Q2_receitas_por_mes|Varejo"]["query_ids"][0]
p = subprocess.run([COSMOS, "replay", qid, "-m", "semantic", "-c", "connections.yml", "--audit", str(AUDIT)],
                   cwd=CDIR, env=ENV, capture_output=True, text=True)
out["replay"] = {"query_id": qid, "rc": p.returncode, "stdout": p.stdout.strip()[-1500:], "stderr": p.stderr.strip()[-500:]}

# Replay depois de alterar os dados: cópia da base com 1 reembolso completed a mais (Varejo, out/2026)
alt = RES / "vendas_alterado.duckdb"
shutil.copy(ROOT / "data/vendas.duckdb", alt)
c2 = duckdb.connect(str(alt))
c2.execute("""INSERT INTO poc.refunds SELECT 99999, o.order_id, 1000, 'completed', DATE '2026-10-30'
  FROM poc.orders o JOIN poc.customers cu USING (customer_id)
  WHERE cu.carteira = 'Varejo' AND o.status = 'refunded' AND o.ordered_at >= DATE '2026-10-01'
  ORDER BY o.order_id LIMIT 1""")
c2.close()
p = subprocess.run([COSMOS, "replay", qid, "-m", "semantic", "-c", "connections.yml", "--audit", str(AUDIT)],
                   cwd=CDIR, env={**ENV, "COSMOS_DUCKDB_PATH": str(alt)}, capture_output=True, text=True)
out["replay_dados_alterados"] = {"query_id": qid, "rc": p.returncode, "stdout": p.stdout.strip()[-1500:]}
alt.unlink()

# ---------- Lado Metric Views traduzido para SQL puro ----------
con = duckdb.connect(str(ROOT / "data/vendas.duckdb"), read_only=True)
GOLD = (ROOT / "metric-views/fct_pedidos.sql").read_text()
con.execute(f"CREATE TEMP VIEW fct_pedidos AS {GOLD}")
MV = {
 "Q1_clientes_ativos": """SELECT COUNT(DISTINCT customer_id) FILTER (WHERE status IN ('paid','refunded')
        AND ordered_at > DATE '{as_of}' - INTERVAL 90 DAY) AS active_customers FROM fct_pedidos WHERE carteira = ?""",
 "Q2_receitas_por_mes": """SELECT DATE_TRUNC('month', ordered_at) AS m,
        SUM(item_total) FILTER (WHERE status IN ('paid','refunded')) AS gross_revenue,
        SUM(refund_completed) AS refunds_completed,
        SUM(item_total) FILTER (WHERE status IN ('paid','refunded')) - SUM(refund_completed) AS net_revenue,
        SUM(item_total) FILTER (WHERE status IN ('paid','refunded')) / COUNT(*) FILTER (WHERE status IN ('paid','refunded')) AS average_order_value,
        SUM(refund_completed) / SUM(item_total) FILTER (WHERE status IN ('paid','refunded')) AS refund_rate
        FROM fct_pedidos WHERE carteira = ? GROUP BY ALL""",
 "Q3_liquida_30_dias": """SELECT SUM(item_total) FILTER (WHERE status IN ('paid','refunded')) - SUM(refund_completed) AS net_revenue,
        SUM(item_total) FILTER (WHERE status IN ('paid','refunded')) AS gross_revenue
        FROM fct_pedidos WHERE carteira = ? AND ordered_at >= DATE '2026-10-02'""",
 "Q4_ticket_por_regiao": """SELECT region,
        SUM(item_total) FILTER (WHERE status IN ('paid','refunded')) / COUNT(*) FILTER (WHERE status IN ('paid','refunded')) AS average_order_value,
        SUM(refund_completed) / SUM(item_total) FILTER (WHERE status IN ('paid','refunded')) AS refund_rate,
        COUNT(*) FILTER (WHERE status IN ('paid','refunded')) AS paid_orders
        FROM fct_pedidos WHERE carteira = ? GROUP BY ALL""",
 "Q5_liquida_por_dia_7d": """SELECT ordered_at AS d,
        SUM(item_total) FILTER (WHERE status IN ('paid','refunded')) AS gross_revenue,
        SUM(item_total) FILTER (WHERE status IN ('paid','refunded')) - SUM(refund_completed) AS net_revenue
        FROM fct_pedidos WHERE carteira = ? AND ordered_at >= DATE '2026-10-25' GROUP BY ALL""",
}
def num(v):
    if v is None: return None
    return float(v)
def norm_rows(rows):
    res = []
    for r in rows:
        vals = [num(v) if isinstance(v, (int, float, decimal.Decimal)) else (str(v)[:10] if v is not None else None) for v in r]
        res.append(vals)
    return sorted(res, key=lambda x: json.dumps(x, default=str))
cmp = {}
for qn, sql in MV.items():
    for u in USERS:
        mv_rows = con.execute(sql.format(as_of=AS_OF), [u]).fetchall()
        crow = out["runs"][f"{qn}|{u}"]["rows"]
        cos_rows = [list(r.values()) for r in crow]
        a, b = norm_rows(cos_rows), norm_rows([list(r) for r in mv_rows])
        ok = len(a) == len(b) and all(
            len(x) == len(y) and all((p == q) if not isinstance(p, float) or not isinstance(q, float)
                                     else abs(p - q) <= 1e-6 * max(1.0, abs(q)) for p, q in zip(x, y))
            for x, y in zip(a, b))
        cmp[f"{qn}|{u}"] = {"match": ok, "rows": len(b), "mv_first": b[:2], "cosmos_first": a[:2]}
out["equivalencia"] = cmp
(RES / "resultado_poc.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
print("estaveis:", sum(v["stable"] for v in out["runs"].values()), "/", len(out["runs"]))
print("bateram:", sum(v["match"] for v in cmp.values()), "/", len(cmp))
print("negacoes:", json.dumps(out["denials"], ensure_ascii=False)[:800])
print("replay rc:", out["replay"]["rc"], out["replay"]["stdout"][:600], out["replay"]["stderr"][:300])
print("replay com dados alterados:", out["replay_dados_alterados"]["stdout"][:600])
print("model_hash:", out["runs"]["Q1_clientes_ativos|Varejo"]["model_hash"])
for k, v in out["runs"].items():
    r = v["rows"]
    print(f"{k:32s} estavel={v['stable']} sql={v['sql_hash'][:12]} result={v['result_hash'][:12]} "
          f"bate_mv={out['equivalencia'][k]['match']} {json.dumps(r[0], ensure_ascii=False) if len(r) == 1 else str(len(r)) + ' linhas'}")
for k, v in cmp.items():
    if not v["match"]: print("DIVERGE", k, v)
