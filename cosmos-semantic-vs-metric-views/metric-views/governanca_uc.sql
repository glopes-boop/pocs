-- Governança no UC para a Metric View. SÓ NO PAPEL. Marcações:
--   [DOC] conferido hoje na doc oficial; [INF] inferência/conhecimento prévio, não reconferido hoje.

-- 1) Permissão: consumidores só recebem SELECT na metric view, não nas tabelas gold. [DOC: manage]
GRANT SELECT ON VIEW demo_poc.semantica.mv_pedidos TO `agentes-analiticos-leitores`;

-- 2) Row filter por carteira na TABELA GOLD (não dá para pôr ABAC na metric view). [DOC: filters-and-masks;
--    abac/requirements diz "You can't apply ABAC policies to metric views"]
--    O filtro roda no contexto de quem consulta (current_user / is_account_group_member). [INF: doc de terceiros
--    e blog Genie One citam isso; confirmar em workspace com dois usuários]
CREATE OR REPLACE FUNCTION demo_poc.seguranca.rf_carteira(carteira STRING)
RETURN is_account_group_member('carteira_' || lower(carteira))
    OR is_account_group_member('carteira_todas');
ALTER TABLE demo_poc.gold.fct_pedidos SET ROW FILTER demo_poc.seguranca.rf_carteira ON (carteira);

-- 2b) Alternativa recomendada em escala: ABAC por governed tag na tabela gold (CREATE POLICY ... ON SCHEMA,
--     com has_tag_value). [DOC: abac-vs-rls-cm, sintaxe completa não reconferida → INF]

-- 3) Máscara LGPD do CNPJ (se o CNPJ for exposto em alguma tabela/field). [DOC: filters-and-masks]
CREATE OR REPLACE FUNCTION demo_poc.seguranca.mask_cnpj(cnpj STRING)
RETURN CASE WHEN is_account_group_member('lgpd_cnpj_leitura') THEN cnpj ELSE '**.***.***/****-**' END;
-- ALTER TABLE demo_poc.gold.dim_clientes ALTER COLUMN cnpj SET MASK demo_poc.seguranca.mask_cnpj;

-- 4) Por que o filtro fica no FATO e não na dim de clientes: a metric view faz LEFT OUTER JOIN da fonte com
--    a dimensão [DOC: yaml-reference, star schema]; um filtro só na dimensão viraria carteira NULL, não
--    removeria os pedidos. Daí a carteira desnormalizada em fct_pedidos. [INF, derivado da doc]

-- 5) Auditoria (system tables). [INF: não reconferido hoje]
-- Quem consultou a metric view, com qual SQL e identidade:
SELECT executed_by, statement_text, start_time, statement_id
FROM system.query.history
WHERE statement_text ILIKE '%mv_pedidos%' AND start_time >= current_date() - INTERVAL 1 DAY;
-- Eventos de acesso do UC (getTable, etc.):
SELECT event_time, user_identity.email, action_name, request_params
FROM system.access.audit
WHERE service_name = 'unityCatalog' AND request_params['full_name_arg'] = 'demo_poc.semantica.mv_pedidos';
