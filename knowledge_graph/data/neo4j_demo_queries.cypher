// 1) 导入 CSV（Neo4j Browser 执行，file URL 需按本机路径调整）
// 示例: :auto LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row ...

// 节点导入
LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
MERGE (n {id: row.`id:ID`})
SET n:Entity,
    n:Company = CASE WHEN row.`:LABEL` = 'Company' THEN true ELSE null END,
    n:Industry = CASE WHEN row.`:LABEL` = 'Industry' THEN true ELSE null END,
    n.node_type = row.node_type,
    n.name = row.name,
    n.ts_code = row.ts_code,
    n.industry = row.industry,
    n.industry_name = row.industry_name,
    n.is_st = CASE WHEN row.`is_st:boolean` = '' THEN null ELSE toBoolean(row.`is_st:boolean`) END,
    n.company_count = CASE WHEN row.`company_count:long` = '' THEN null ELSE toInteger(row.`company_count:long`) END;

// 关系导入
LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
MATCH (s {id: row.`:START_ID`}), (t {id: row.`:END_ID`})
CALL {
  WITH s, t, row
  WITH s, t, row, row.`:TYPE` AS relType
  CALL apoc.create.relationship(s, relType, {
    relation: row.relation,
    share_ratio: CASE WHEN row.`share_ratio:double` = '' THEN null ELSE toFloat(row.`share_ratio:double`) END,
    share_amount: CASE WHEN row.`share_amount:double` = '' THEN null ELSE toFloat(row.`share_amount:double`) END,
    guarantee_count: CASE WHEN row.`guarantee_count:double` = '' THEN null ELSE toFloat(row.`guarantee_count:double`) END,
    guarantee_amount: CASE WHEN row.`guarantee_amount:double` = '' THEN null ELSE toFloat(row.`guarantee_amount:double`) END,
    same_controller: CASE WHEN row.`same_controller:boolean` = '' THEN null ELSE toBoolean(row.`same_controller:boolean`) END,
    source: row.source,
    report_date: row.report_date
  }, t) YIELD rel
  RETURN rel
}
RETURN count(*) AS imported_rels;

// 2) 风险路径查询: 找出所有通过担保链与 ST 公司相连的公司（1~4 跳）
MATCH (st:Entity {is_st: true})
MATCH p = (c:Entity)-[:GUARANTEES*1..4]->(st)
WHERE c.id <> st.id
RETURN DISTINCT c.id AS company_id, c.name AS company_name, st.id AS st_id, st.name AS st_name, length(p) AS hops
ORDER BY hops ASC, company_name
LIMIT 200;

// 3) 股权 + 担保混合风险链（有同实控人优先）
MATCH (st:Entity {is_st: true})
MATCH p = (c:Entity)-[:OWNS_SHARES|GUARANTEES*1..4]->(st)
WHERE c.id <> st.id
WITH c, st, p,
     any(r IN relationships(p) WHERE coalesce(r.same_controller, false) = true) AS has_same_controller
RETURN DISTINCT c.name AS company_name, st.name AS st_company, length(p) AS hops, has_same_controller
ORDER BY has_same_controller DESC, hops ASC, company_name
LIMIT 200;
