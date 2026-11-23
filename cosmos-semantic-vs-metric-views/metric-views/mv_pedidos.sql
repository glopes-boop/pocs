-- =====================================================================================
-- Metric View equivalente ao modelo Cosmos. SÓ NO PAPEL: não foi executado no Databricks.
-- Sintaxe conferida em 23/11/2026 nas páginas oficiais (links no relatorio.md):
--   CREATE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$ ; version 1.1; source; parameters;
--   fields (sinônimo de dimensions); measures com FILTER (WHERE ...); MEASURE() de measure anterior;
--   comment / display_name / synonyms (spec 1.1).
-- Requisitos (doc): parâmetros exigem Databricks Runtime 18.2+ para consultar; SQL warehouse ok.
-- Inferência: try_divide para evitar erro de divisão por zero no modo ANSI.
-- =====================================================================================
CREATE OR REPLACE VIEW demo_poc.semantica.mv_pedidos
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Pedidos B2B: receita bruta, líquida, ticket médio, taxa de reembolso e clientes ativos. Dono: controladoria."
source: demo_poc.gold.fct_pedidos        # grão de pedido; carteira desnormalizada (ver fct_pedidos.sql)
parameters:
  - name: as_of                         # sem default: todo consumidor fixa a data de referência
    data_type: date
filter: ordered_at <= as_of             # nada depois da data de referência
fields:
  - name: ordered_at
    expr: ordered_at
    display_name: "Data do pedido"
  - name: order_month
    expr: DATE_TRUNC('MONTH', ordered_at)
    display_name: "Mês do pedido"
  - name: status
    expr: status
    comment: "paid, refunded, pending ou canceled"
  - name: carteira
    expr: carteira
    display_name: "Carteira"
    synonyms: ["segmento", "segmento comercial"]
  - name: region
    expr: region
    display_name: "Região"
measures:
  - name: gross_revenue
    expr: SUM(item_total) FILTER (WHERE status IN ('paid', 'refunded'))
    display_name: "Receita bruta"
    synonyms: ["faturamento bruto", "vendas"]
    comment: "Itens de pedidos pagos (paid ou refunded), na data do pedido"
  - name: refunds_completed
    expr: SUM(refund_completed)
    display_name: "Reembolsos efetivados"
    comment: "Só reembolsos completed, atribuídos à data do pedido original"
  - name: net_revenue
    expr: MEASURE(gross_revenue) - MEASURE(refunds_completed)
    display_name: "Receita líquida"
    synonyms: ["faturamento líquido", "faturamento", "receita"]
  - name: paid_orders
    expr: COUNT(1) FILTER (WHERE status IN ('paid', 'refunded'))
    display_name: "Pedidos pagos"
  - name: average_order_value
    expr: try_divide(MEASURE(gross_revenue), MEASURE(paid_orders))
    display_name: "Ticket médio"
    synonyms: ["valor médio do pedido", "AOV"]
  - name: refund_rate
    expr: try_divide(MEASURE(refunds_completed), MEASURE(gross_revenue))
    display_name: "Taxa de reembolso"
  - name: active_customers
    expr: COUNT(DISTINCT customer_id) FILTER (WHERE status IN ('paid', 'refunded') AND ordered_at > as_of - INTERVAL 90 DAYS)
    display_name: "Clientes ativos (90 dias)"
    synonyms: ["clientes ativos", "base ativa"]
$$;
