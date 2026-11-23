"""Dados sintéticos determinísticos (seed 42) para a POC Cosmos vs Metric Views.
Modelo: clientes empresariais (B2B) com carteira (filtro de linha), pedidos, itens e reembolsos."""
import datetime as dt, random, sys
from pathlib import Path
import duckdb

SEED = 42
END = dt.date(2026, 10, 31)
START = dt.date(2025, 11, 1)
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "data/vendas.duckdb")

rng = random.Random(SEED)
CARTEIRAS = [("Varejo", 0.55), ("Middle", 0.30), ("Corporate", 0.15)]
REGIOES = ["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"]
STATUS = [("paid", 0.70), ("refunded", 0.08), ("pending", 0.10), ("canceled", 0.12)]

def pick(pairs):
    r, acc = rng.random(), 0.0
    for v, w in pairs:
        acc += w
        if r < acc:
            return v
    return pairs[-1][0]

customers = []
for cid in range(1, 601):
    cart = pick(CARTEIRAS)
    created = START - dt.timedelta(days=rng.randint(0, 900))
    # CNPJ fictício: dígitos aleatórios, sem dígito verificador válido; não corresponde a empresa real
    cnpj = f"{rng.randint(10,99)}.{rng.randint(100,999)}.{rng.randint(100,999)}/0001-{rng.randint(10,99)}"
    customers.append((cid, f"Empresa {cid:04d}", cart, rng.choice(REGIOES), cnpj, created))

days = (END - START).days
orders, items, refunds = [], [], []
iid = rid = 0
scale = {"Varejo": 1.0, "Middle": 3.0, "Corporate": 8.0}
for oid in range(1, 6001):
    c = customers[rng.randint(0, 599)]
    od = START + dt.timedelta(days=rng.randint(0, days))
    st = pick(STATUS)
    orders.append((oid, c[0], od, st))
    total = 0.0
    for _ in range(rng.randint(1, 4)):
        iid += 1
        q = rng.randint(1, 5)
        price = round(rng.uniform(50, 900) * scale[c[2]], 2)
        items.append((iid, oid, q, price))
        total += q * price
    if st == "refunded":                      # reembolso efetivado (às vezes no mês seguinte)
        rid += 1
        amt = round(total * rng.choice([1.0, 0.5, 0.3]), 2)
        rd = min(od + dt.timedelta(days=rng.randint(1, 40)), END)
        refunds.append((rid, oid, amt, "completed", rd))
    elif st == "paid" and rng.random() < 0.06:  # pedido de reembolso não efetivado: não conta
        rid += 1
        rd = min(od + dt.timedelta(days=rng.randint(1, 20)), END)
        refunds.append((rid, oid, round(total * 0.2, 2), rng.choice(["requested", "rejected"]), rd))

OUT.parent.mkdir(parents=True, exist_ok=True)
if OUT.exists():
    OUT.unlink()
con = duckdb.connect(str(OUT))
con.execute("CREATE SCHEMA poc")
con.execute("CREATE TABLE poc.customers(customer_id INT PRIMARY KEY, name VARCHAR, carteira VARCHAR, region VARCHAR, cnpj VARCHAR, created_at DATE)")
con.execute("CREATE TABLE poc.orders(order_id INT PRIMARY KEY, customer_id INT, ordered_at DATE, status VARCHAR)")
con.execute("CREATE TABLE poc.order_items(order_item_id INT PRIMARY KEY, order_id INT, quantity INT, unit_price DECIMAL(12,2))")
con.execute("CREATE TABLE poc.refunds(refund_id INT PRIMARY KEY, order_id INT, amount DECIMAL(12,2), status VARCHAR, refunded_at DATE)")
con.executemany("INSERT INTO poc.customers VALUES (?,?,?,?,?,?)", customers)
con.executemany("INSERT INTO poc.orders VALUES (?,?,?,?)", orders)
con.executemany("INSERT INTO poc.order_items VALUES (?,?,?,?)", items)
con.executemany("INSERT INTO poc.refunds VALUES (?,?,?,?,?)", refunds)
for t in ["customers", "orders", "order_items", "refunds"]:
    print(t, con.execute(f"SELECT count(*) FROM poc.{t}").fetchone()[0])
print(con.execute("SELECT status, count(*) FROM poc.refunds GROUP BY 1 ORDER BY 1").fetchall())
