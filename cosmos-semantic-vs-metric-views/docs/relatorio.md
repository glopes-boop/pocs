# POC: Cosmos Semantic x Databricks Metric Views para um gateway de métricas para agentes

*23/11/2026, 11h10 (horário de Brasília). O Cosmos foi executado de verdade (v0.5.0, commit `12e458f`) contra DuckDB. O lado das Metric Views ficou **só no papel**: nada foi criado nem executado no Databricks.*

**Contexto (genérico):** uma empresa regulada que expõe métricas analíticas a agentes de IA por um gateway com PEP (API gateway que valida o JWT), PDP stateless que decide e falha fechado, recibo SHA-256 por resposta gravado em tabela append-only e direitos de acesso num catálogo governado (Unity Catalog). Os agentes só leem e não escrevem. A pergunta é qual camada semântica usar atrás desse gateway para que a mesma pergunta sempre vire a mesma métrica, com evidência auditável.

Legenda das marcações: **[DOC]** conferido hoje na documentação oficial da Databricks · **[RODADO]** executado nesta POC · **[INF]** inferência ou conhecimento prévio não reconferido hoje · **[NÃO TESTADO]**.

## 1. Veredito

- **Fonte da verdade das métricas: Metric Views.** As métricas ficam no Unity Catalog, e a consulta roda no warehouse com a identidade de quem pergunta. Na Metric View, os row filters e o ABAC ficam na tabela de origem, e a consulta é feita por OBO [DOC/INF]. No Cosmos, a consulta chega à base de dados com um token de serviço único, e o filtro de linha é um SQL que o próprio Cosmos injeta [RODADO, código lido].
- **Do Cosmos, copiar o envelope de evidência e o replay, montados no PDP.** É o que as Metric Views não têm: `sql_hash`, `result_hash` independente da ordem, `model_hash`, regras com dono, versão e testes, filtros de linha com os valores do usuário, `as_of` fixado e um `replay` que diz se mudou o modelo, o SQL ou os dados [RODADO].
- **A POC prova equivalência semântica, não o Databricks.** Nas 15 combinações de pergunta e carteira, o Cosmos deu o mesmo número que o SQL traduzido das measures da Metric View, e os hashes ficaram estáveis nas 3 execuções de cada combinação [RODADO].
- **Achado prático:** o Cosmos, com o modelo escrito do jeito óbvio (`{gross_revenue} - {refunds_completed}`), devolve `net_revenue` **NULL** nos dias sem reembolso efetivado. Corrigi com `COALESCE` (seção 4). Esse tipo de diferença é o que uma POC lado a lado serve para pegar.
- **Recomendação:** Metric View (YAML em Git, publicada por CI) como definição única. O PDP escolhe a métrica pelo catálogo, sem LLM; consulta via `MEASURE()` com o token OBO do usuário; e monta um envelope estilo Cosmos que vai para o recibo SHA-256 encadeado em Delta. O Cosmos fica como referência de desenho e como harness local de testes de equivalência, não em produção.

## 2. O que foi montado

```
cosmos-semantic-vs-metric-views/
  scripts/gerar_dados.py          dados sintéticos determinísticos (seed 42) -> data/vendas.duckdb
  scripts/rodar_poc.py            roda o Cosmos 3x por pergunta e usuário, negações, replay e equivalência com o SQL das measures
  cosmos/semantic/modelo.yml      modelo Cosmos (4 modelos, 7 métricas, row filter por carteira, CNPJ como dado pessoal)
  cosmos/semantic/ontologia.yml   glossário pt/en e 3 regras de negócio versionadas, com testes
  metric-views/mv_pedidos.sql     CREATE VIEW ... WITH METRICS LANGUAGE YAML (spec 1.1), só no papel
  metric-views/fct_pedidos.sql    tabela gold de origem (grão de pedido, carteira desnormalizada)
  metric-views/consultas_measure.sql  consultas MEASURE() equivalentes a Q1–Q4
  metric-views/governanca_uc.sql  GRANT, row filter, máscara de CNPJ e consultas às system tables, com marcações DOC/INF
  results/                        resultado_poc.json, evidências, SQL gerado, audit JSONL, replay
  docs/diagrama.{png,excalidraw}  gerado por scripts/diagrama_cosmos_vs_mv.py
```

**Dados** (seed 42, de 01/11/2025 a 31/10/2026): 600 clientes empresariais (B2B) com carteira (Varejo 55%, Middle 30%, Corporate 15%), região e CNPJ; 6.000 pedidos (paid 70%, refunded 8%, pending 10%, canceled 12%); 14.984 itens; 735 reembolsos (507 completed, 116 requested, 112 rejected). Os reembolsos completed às vezes caem no mês seguinte ao do pedido, para testar a atribuição à data original.

**Métricas** (iguais nos dois lados):

| Métrica | Definição |
|---|---|
| `gross_revenue` | Soma de `quantity * unit_price` dos itens de pedidos `paid` ou `refunded`, na data do pedido |
| `refunds_completed` | Soma dos reembolsos `completed`, atribuída à data do pedido original |
| `net_revenue` | `gross_revenue - refunds_completed` (reembolso ausente conta como 0) |
| `paid_orders` | Quantidade de pedidos `paid` ou `refunded` |
| `average_order_value` | `gross_revenue / paid_orders` (ticket médio) |
| `refund_rate` | `refunds_completed / gross_revenue` (a razão pedida) |
| `active_customers` | Clientes distintos com pedido pago nos 90 dias até `as_of` (inclusive) |

As regras de status são as regras de negócio `paid_order`, `refund_completed` e `active_window` no Cosmos. Na Metric View, viram `FILTER (WHERE ...)` nas measures. As dimensões são tempo (dia e mês do pedido), carteira e região.

## 3. Resultados do Cosmos [RODADO]

`as_of = 2026-10-31`, `model_hash = 9481eb99fa17…`. Rodei cada pergunta 3 vezes por usuário (claim `carteira`):

| Pergunta | Carteira | Hashes iguais nas 3? | sql_hash | result_hash | Igual ao SQL das measures? | Resultado |
|---|---|---|---|---|---|---|
| Q1 clientes ativos | Varejo | sim | `a02245200ffb` | `811c2c8d8a94` | sim | 286 |
| Q1 clientes ativos | Middle | sim | `b211ead9a7d7` | `e2c484f41e9c` | sim | 162 |
| Q1 clientes ativos | Corporate | sim | `455cc2aba2fb` | `03f30fbdb2a7` | sim | 79 |
| Q2 receitas por mês | Varejo | sim | `8e722ed5edba` | `eb086f1bbce6` | sim | 12 linhas |
| Q2 receitas por mês | Middle | sim | `e6b32a7972ad` | `e83dee7a7cf2` | sim | 12 linhas |
| Q2 receitas por mês | Corporate | sim | `377cd9efe90f` | `8ef7e7d1aae7` | sim | 12 linhas |
| Q3 líquida dos últimos 30 dias | Varejo | sim | `1e398849f1f9` | `d20bc309d5f8` | sim | líquida 752.750,99 · bruta 790.066,34 |
| Q3 líquida dos últimos 30 dias | Middle | sim | `200d1174627a` | `fc2181399e8a` | sim | líquida 1.207.589,31 · bruta 1.249.008,77 |
| Q3 líquida dos últimos 30 dias | Corporate | sim | `2909662590c4` | `08e3ba14c587` | sim | líquida 2.028.140,90 · bruta 2.259.217,15 |
| Q4 ticket e reembolso por região | Varejo | sim | `d280737a5a4d` | `cb32da76a842` | sim | 5 linhas |
| Q4 ticket e reembolso por região | Middle | sim | `f5b4835bb52a` | `5e2021c3478f` | sim | 5 linhas |
| Q4 ticket e reembolso por região | Corporate | sim | `7b78a1144c2f` | `ec80dcb7ffe3` | sim | 5 linhas |
| Q5 líquida por dia (7 dias) | Varejo | sim | `3b1ec180b986` | `5764634a1796` | sim | 7 linhas |
| Q5 líquida por dia (7 dias) | Middle | sim | `a4c9e2e42803` | `b448b9ed6db1` | sim | 7 linhas |
| Q5 líquida por dia (7 dias) | Corporate | sim | `4b2572bd35de` | `89c8eafe4593` | sim | 7 linhas |

O total é **15 de 15 estáveis e 15 de 15 iguais** ao SQL das measures (tolerância relativa de 1e-6).

**Testes de política:**
- **Sem claim `carteira`:** a consulta é negada com `query denied: the user context has no carteira, which a row filter requires`. É fail closed.
- **Dois usuários diferentes:** Varejo e Corporate recebem números diferentes para a mesma pergunta. A evidência traz `policies.row_filters` com `user_fields: {carteira: ...}` e as CTEs onde o filtro entrou (`results/cosmos_evidencia_Q2_Varejo.json`).
- **Agente pedindo o CNPJ:** com `--agent`, agrupar por `customers.cnpj` é negado (`personal data (LGPD) and never reaches AI agents`). A mesma consulta fora do canal de agente **passa**, porque o bloqueio depende do canal (`channel == "mcp"`).
- **Replay sem mudança:** `identical: Same model, same SQL and same result`.
- **Replay depois de mudar os dados:** inseri 1 reembolso numa cópia da base. O resultado foi `data_changed: Same model and SQL; the source data changed`: `result_hash` passou de `eb086f1bbce6…` para `cd5f534378d0…` (`results/replay_dados_alterados.txt`).
- **Auditoria:** 48 linhas JSONL em `results/cosmos_audit.jsonl`, uma por consulta, com quem, pedido, SQL, hashes, regras e resultado ou erro. Não há encadeamento nem assinatura.

**Observações do SQL gerado** (`results/cosmos_sql_Q2.sql`):
- Cada fato vira uma CTE agregada (itens, reembolsos, pedidos). Elas são unidas pela dimensão com `IS NOT DISTINCT FROM`, o que evita fan-out.
- O reembolso é atribuído ao mês do pedido pelo join `refunds -> orders`.
- O filtro de carteira aparece repetido no WHERE (uma vez por modelo com row filter). É redundante, mas inofensivo.
- O `sql_hash` muda por usuário, porque o valor do claim entra como literal no SQL. "Mesma pergunta, mesmo SQL" vale para o mesmo contexto de usuário.
- Sem `--order`, as linhas saem sem ordem. O `result_hash` não depende da ordem.

## 4. Achado: `net_revenue` NULL nos dias sem reembolso [RODADO]

Com `expr: "{gross_revenue} - {refunds_completed}"`, o SQL do Cosmos faz `item_total - refund_value`. Num dia sem reembolso efetivado, `refund_value` é NULL, e a receita líquida sai **vazia**. Exemplo da carteira Corporate em 26/10: bruta 41.451,68 e líquida vazia (`results/achado_net_null_antes.txt`). A correção foi `expr: "{gross_revenue} - COALESCE({refunds_completed}, 0)"`, que o Cosmos aceita (`results/achado_net_null_depois.txt`). No desenho da Metric View, a tabela gold já faz `COALESCE(refund_completed, 0)` por pedido, então `SUM` dá 0 e não NULL. **Para o gateway:** é preciso uma suíte de equivalência (os números da referência contra os da camada semântica) por métrica e por grão, incluindo dia sem evento.

## 5. Metric Views no papel

### 5.1 O que a documentação diz hoje [DOC]
- Criação: `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$`.
- A especificação YAML é versionada à parte do runtime. As versões atuais são **0.1** (inicial) e **1.1**. A 1.1 trouxe metadados para agentes (`display_name`, formatação, `synonyms`, `comment`) e, a partir do Runtime 18.1, `cardinality: one_to_many`, `offset` em janelas e `inclusive`/`exclusive`. As Metric Views surgiram no Runtime 16.4.
- Campos de topo: `version` (obrigatório), `comment`, `source` (tabela, view, metric view ou SQL), `parameters`, `filter`, `joins`, `fields` (`dimensions` continua aceito), `measures` e `materialization`.
- Measures usam funções de agregação, aceitam `FILTER (WHERE ...)` e podem referenciar measures anteriores com `MEASURE()`.
- Toda consulta usa `MEASURE()` (no Runtime 18.1+ também `agg`). Não dá para fazer JOIN direto: é preciso envolver em uma CTE. Uma metric view com parâmetros é chamada como função de tabela com argumento nomeado, e consultá-la exige o Runtime 18.2+.
- O join padrão é `many_to_one`, feito como LEFT OUTER JOIN. No caso de muitos para muitos, vale a primeira linha da dimensão.
- `DESCRIBE TABLE EXTENDED ... AS JSON` devolve o YAML completo.
- Permissões: SELECT na metric view basta, seguindo a hierarquia do UC. **Não é possível aplicar ABAC na própria metric view.** Row filters e masks ficam nas tabelas.
- No exemplo de materialização da doc, `filter`, `fields` e `measures` não podem usar expressões dependentes de quem consulta (`current_user()`, `is_member()`). Uma tabela de origem com RLS, máscara ou ABAC não pode ser materializada.
- Consumo: dashboards AI/BI, Genie Agents, alertas, JDBC/ODBC, ferramentas de BI externas, Excel e Google Sheets.

### 5.2 Desenho escolhido
- **Fonte:** a tabela gold `fct_pedidos` (grão de pedido, com `item_total` e `refund_completed` pré-agregados e a carteira desnormalizada). Escolhi a gold em vez de joins `one_to_many` por três motivos: a gold roda em qualquer runtime; a regra "uma agregação referencia uma fonte só" [DOC] complicaria `SUM(itens) FILTER (WHERE status ...)`; e o row filter precisa estar no fato. Uma alternativa com `one_to_many` é possível, mas fica **[NÃO TESTADO]**.
- **Parâmetro `as_of` sem default:** todo consumidor (o PDP, o Genie, um dashboard) precisa fixar a data de referência. É o equivalente do `as_of` fixado no Cosmos e serve ao determinismo e ao replay. Um parâmetro sem default é permitido [DOC]. O uso por Genie e dashboards com parâmetro obrigatório fica **[NÃO TESTADO]**.
- **Equivalência:** traduzi as measures para SQL puro em DuckDB sobre a mesma `fct_pedidos` (em `scripts/rodar_poc.py`). Bateram 15 de 15 com o Cosmos [RODADO]. Isso **não** prova que o Databricks dá o mesmo número: semântica de `FILTER`, `try_divide`, tipos DECIMAL e rollups pode divergir [INF].

### 5.3 Governança no UC, identidade e auditoria
| Tema | Como ficaria | Status |
|---|---|---|
| Row filter por carteira | Função `rf_carteira(carteira)` com `is_account_group_member`, aplicada com `ALTER TABLE fct_pedidos SET ROW FILTER` | DOC (row filters); sintaxe exata da função [INF] |
| Por que no fato | A metric view faz LEFT JOIN da fonte com a dimensão. Um filtro só na dimensão de clientes deixaria a carteira NULL em vez de remover os pedidos | INF (derivado da doc de joins) |
| ABAC | Por governed tag na tabela gold. Na metric view não é suportado | DOC |
| Identidade de quem consulta | Os row filters das tabelas são avaliados para o usuário que consulta a metric view | INF (trecho de busca e doc de terceiros; testar com 2 usuários) |
| OBO | Os MCPs gerenciados e o Genie One MCP recomendam OBO: o token do usuário é repassado e o UC avalia privilégios, row filters e masks. Com M2M, todos viram uma identidade só | DOC (páginas de MCP e blog do Genie One, lidos por trecho) |
| MCP gerenciado | O Genie One MCP (`system.ai.genie_one_mcp`, GA) passa pelo Unity Gateway. O Genie Agent MCP (Public Preview) **não** passa pelo Unity Gateway. O DBSQL MCP (`system.ai.dbsql`) está em Beta | DOC (trecho da página Databricks-provided MCPs, 18/11) |
| Auditoria | `system.query.history` (SQL, quem executou) e `system.access.audit` (eventos do UC) | INF (não reconferido hoje) |
| Recibo | Não há envelope por resposta. O PDP grava `statement_id`, o hash do YAML publicado (`DESCRIBE ... AS JSON`), `as_of`, o `sql_hash` do texto enviado e o `result_hash` calculado no PDP | Desenho proposto |

## 6. Comparação critério a critério para o gateway

| Critério | Cosmos Semantic | Metric Views (+ Genie/MCP) | Para o gateway |
|---|---|---|---|
| Definição única | YAML próprio (vocabulário do dbt SL), com import e export de dbt, Cube e Ossie [RODADO/código] | YAML no UC, versão de spec 1.1 [DOC] | Empate no conceito. A Metric View vive onde estão os dados e os direitos |
| Determinismo | Compilador SQLGlot, sem LLM. 15/15 combinações com hashes estáveis [RODADO] | Execução determinística dada a consulta `MEASURE()` [INF]. O Genie gera SQL com LLM | Os dois são determinísticos depois que a métrica foi escolhida |
| Escolha da métrica pelo agente | O agente escolhe (o glossário ajuda). Não há resolvedor determinístico | O Genie escolhe com LLM, usando sinônimos e metadados [DOC] | **Nenhum resolve. O PDP deve escolher pelo catálogo** (sinônimo para métrica, com tabela fechada) e negar quando houver ambiguidade |
| Evidência e recibo | Envelope completo, `replay` e diagnóstico de mudança [RODADO] | Não nativo. Há `DESCRIBE`, query history e lineage | **Copiar o envelope do Cosmos no PDP** |
| Identidade até o dado | Token de serviço no warehouse. Não há OBO [código] | OBO com UC [DOC/INF] | Metric Views |
| Row filter | SQL injetado pelo Cosmos a partir dos claims. Fail closed quando falta claim [RODADO] | Row filter ou ABAC na tabela, avaliados pelo UC [DOC/INF] | Metric Views. O fail closed por claim fica no PDP |
| LGPD (dado pessoal) | Bloqueio por coluna classificada, só no canal de agente. Fora dele, passa [RODADO] | Máscara de coluna no UC para qualquer canal [DOC] | Máscara no UC, mais bloqueio no PDP |
| Auditoria | JSONL local com hashes, sem encadeamento [RODADO] | System tables [INF] | Recibo próprio encadeado em Delta, com referência ao `statement_id` |
| Versionamento | `model_hash`, regras com `effective_from`, `rules_as_of` e testes [RODADO] | Versão da spec, mas não da definição. Versionar via Git e CI [INF] | Git + CI publicando a Metric View, com o hash do YAML no recibo e regras com vigência |
| MCP/REST | MCP próprio (8 tools) e REST, com JWT OIDC [código] | Genie One MCP (GA), Genie Agent MCP (Preview), DBSQL MCP (Beta), JDBC/ODBC [DOC] | Atrás do PEP, preferir uma tool própria do agente que chama `MEASURE()` via DBSQL com OBO |
| Maturidade e suporte | Alpha 0.5.0, um mantenedor mais agentes, 1 mês de vida | Produto da plataforma com suporte da Databricks [INF] | Metric Views |
| Custo e lock-in | Apache-2.0, multi-warehouse. Custo é sustentar internamente | Incluído no Databricks (custo de warehouse). Lock-in no UC, mas YAML exportável | Aceitável, se a empresa já está em Databricks |

## 7. Desenho recomendado

1. **Metric Views como fonte da verdade:** YAML em Git (ontologia como código), PR com revisão do dono da métrica, CI que publica `CREATE OR REPLACE VIEW ... WITH METRICS` e grava o hash do YAML. O dbt gera as tabelas gold e o filtro fica no fato.
2. **Direitos no UC:** row filter ou ABAC nas tabelas gold e máscara de CNPJ. Os consumidores recebem só SELECT na metric view.
3. **PDP Python:**
   - Resolve termo para métrica pelo glossário (sinônimos dos `synonyms` da própria Metric View) sem LLM. Se o termo for ambíguo ("faturamento"), nega ou pede esclarecimento.
   - Exige os claims (fail closed) e fixa o `as_of`.
   - Monta a consulta `MEASURE()` a partir de um template, com valores parametrizados.
4. **Execução com OBO** pelo DBSQL, com o token do usuário trocado no PEP (API gateway). Nunca um token de serviço único.
5. **Envelope e recibo estilo Cosmos:** `request`, `principal`, `as_of`, hash do YAML da Metric View, `sql_hash`, `statement_id`, `result_hash` independente da ordem, regras e filtros aplicados (declarados) e caveats. Tudo encadeado (`prev_hash`) em Delta append-only, mais um `replay` que reexecuta e diagnostica o que mudou.
6. **Suíte de equivalência** (como esta POC) por métrica e por grão, contra o SQL de referência, incluindo os casos de borda (dia sem reembolso, divisão por zero).
7. **Genie / Genie One MCP:** para exploração humana. Para os agentes analíticos com recibo, a tool determinística acima. O Genie Agent MCP não passa pelo Unity Gateway [DOC].

## 8. Limitações
- Nada foi executado no Databricks. A sintaxe da Metric View foi conferida na doc, mas a criação, os row filters, o OBO e o Genie **não foram testados**.
- A equivalência foi provada contra uma tradução manual das measures em DuckDB, não contra o motor da Databricks.
- Os dados são sintéticos e pequenos (6.000 pedidos). Não medi desempenho.
- O MCP e o REST do Cosmos via HTTP com JWT real **não foram testados** (só a CLI). O claim foi passado por `-u carteira=...`.
- As páginas de MCP, ABAC e o blog do Genie One foram lidos por trechos da busca. A sintaxe de `CREATE POLICY` (ABAC) e as colunas das system tables **não foram reconferidas hoje**.

## 9. Fontes (documentação oficial da Databricks, acessada em 23/11/2026)
- [Unity Catalog metric views (visão geral)](https://docs.databricks.com/aws/en/metric-views/), atualizada em 29/10/2026
- [Metric view YAML syntax reference](https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference), atualizada em 16/11/2026
- [Metric view feature availability e versões da spec](https://docs.databricks.com/aws/en/uc-semantics/metric-views/feature-availability)
- [Create a metric view (SQL, WITH METRICS)](https://docs.databricks.com/aws/en/metric-views/create/sql)
- [Query metric views](https://docs.databricks.com/aws/en/uc-semantics/metric-views/query), atualizada em 09/11/2026
- [Use parameters with metric views](https://docs.databricks.com/aws/en/uc-semantics/metric-views/use-parameters)
- [Manage metric views (permissões)](https://docs.databricks.com/aws/en/uc-semantics/metric-views/manage)
- [Row filters and column masks](https://docs.databricks.com/aws/en/data-governance/unity-catalog/filters-and-masks)
- [ABAC: requirements and limitations (metric views não suportadas)](https://docs.databricks.com/aws/en/data-governance/unity-catalog/abac/requirements)
- [Databricks-provided MCPs](https://docs.databricks.com/aws/en/agents/mcp-tools/built-in-mcp-services) e [Genie Agent MCP server](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-agent)
- [Blog: Genie One MCP (OBO)](https://www.databricks.com/blog/genie-one-mcp-give-any-ai-agent-right-business-context), 22/09/2026
