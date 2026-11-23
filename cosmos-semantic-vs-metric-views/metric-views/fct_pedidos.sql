-- Tabela gold de pedidos (grão: 1 linha por pedido), fonte da Metric View.
-- Em produção seria um modelo dbt materializado em Delta (ex.: demo_poc.gold.fct_pedidos),
-- com a carteira desnormalizada para o row filter/ABAC do UC agir direto no fato.
SELECT o.order_id, o.customer_id, o.ordered_at, o.status,
       c.carteira, c.region,
       COALESCE(i.item_total, 0)       AS item_total,
       COALESCE(r.refund_completed, 0) AS refund_completed
FROM poc.orders o
JOIN poc.customers c ON c.customer_id = o.customer_id
LEFT JOIN (SELECT order_id, SUM(quantity * unit_price) AS item_total FROM poc.order_items GROUP BY 1) i
       ON i.order_id = o.order_id
LEFT JOIN (SELECT order_id, SUM(amount) FILTER (WHERE status = 'completed') AS refund_completed
           FROM poc.refunds GROUP BY 1) r
       ON r.order_id = o.order_id
