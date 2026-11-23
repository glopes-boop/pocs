-- Consultas MEASURE() equivalentes às perguntas Q1–Q4 da POC. SÓ NO PAPEL.
-- Doc conferida: todas as measures via MEASURE(); metric view com parâmetros é chamada como
-- table-valued function com argumento nomeado. O row filter do UC (governanca_uc.sql) decide a carteira:
-- a consulta NÃO tem WHERE carteira; cada usuário recebe só a sua.

-- Q1: clientes ativos (90 dias até 31/10/2026)
SELECT MEASURE(active_customers) AS active_customers
FROM demo_poc.semantica.mv_pedidos(as_of => DATE'2026-10-31');

-- Q2: receitas por mês
SELECT order_month,
       MEASURE(gross_revenue), MEASURE(refunds_completed), MEASURE(net_revenue),
       MEASURE(average_order_value), MEASURE(refund_rate)
FROM demo_poc.semantica.mv_pedidos(as_of => DATE'2026-10-31')
GROUP BY ALL ORDER BY order_month;

-- Q3: receita líquida dos últimos 30 dias
SELECT MEASURE(net_revenue), MEASURE(gross_revenue)
FROM demo_poc.semantica.mv_pedidos(as_of => DATE'2026-10-31')
WHERE ordered_at >= DATE'2026-10-02';

-- Q4: ticket médio e taxa de reembolso por região
SELECT region, MEASURE(average_order_value), MEASURE(refund_rate), MEASURE(paid_orders)
FROM demo_poc.semantica.mv_pedidos(as_of => DATE'2026-10-31')
GROUP BY ALL;

-- Definição publicada (para o recibo: hash do YAML que respondeu)
DESCRIBE TABLE EXTENDED demo_poc.semantica.mv_pedidos AS JSON;
