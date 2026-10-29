-- MACBS流程任务依赖只读查询；这是技能导出模板，不是增量交付脚本。
-- 替换 {{schema}} 和 {{flowchartid}} 后执行，保留表头导出完整CSV。
-- 即使只分析某一步骤，也保留目标流程全部步骤和任务，以识别跨步骤关系。
WITH params AS (
    SELECT CAST({{flowchartid}} AS INTEGER) AS target_flowchartid
), target_info AS (
    SELECT i.flowchartid, i.flowchartname, i.pre_flowchartid
    FROM {{schema}}.comm_flowchartinfo i
    CROSS JOIN params p
    WHERE i.flowchartid = p.target_flowchartid
), related_info AS (
    SELECT i.flowchartid, i.flowchartname, i.pre_flowchartid
    FROM {{schema}}.comm_flowchartinfo i
    CROSS JOIN params p
    WHERE i.flowchartid = p.target_flowchartid
       -- 匹配当前流程的直接后置流程，逗号边界避免25误匹配125。
       OR (',' || REPLACE(COALESCE(i.pre_flowchartid, ''), ' ', '') || ',')
          LIKE ('%,' || CAST(p.target_flowchartid AS TEXT) || ',%')
       -- 匹配当前流程配置的直接前置流程。
       OR EXISTS (
           SELECT 1
           FROM target_info t
           WHERE (',' || REPLACE(COALESCE(t.pre_flowchartid, ''), ' ', '') || ',')
                 LIKE ('%,' || CAST(i.flowchartid AS TEXT) || ',%')
       )
), exported AS (
    SELECT
        CAST('INFO' AS TEXT) AS row_type,
        i.flowchartid,
        CAST(i.flowchartname AS TEXT) AS flowchartname,
        CAST(i.pre_flowchartid AS TEXT) AS pre_flowchartid,
        CAST(NULL AS INTEGER) AS stepno,
        CAST(NULL AS TEXT) AS stepname,
        CAST(NULL AS TEXT) AS precondition,
        CAST(NULL AS TEXT) AS setactive,
        CAST(NULL AS INTEGER) AS recordno,
        CAST(NULL AS TEXT) AS recordname,
        CAST(NULL AS TEXT) AS beforerecordno
    FROM related_info i

    UNION ALL

    SELECT
        'STEP',
        s.flowchartid,
        NULL,
        NULL,
        s.stepno,
        COALESCE(NULLIF(TRIM(s.stepname), ''), NULLIF(TRIM(s.stepfullname), '')),
        s.precondition,
        s.setactive,
        NULL,
        NULL,
        NULL
    FROM {{schema}}.comm_flowchart s
    CROSS JOIN params p
    WHERE s.flowchartid = p.target_flowchartid

    UNION ALL

    SELECT
        'TASK',
        r.flowchartid,
        NULL,
        NULL,
        r.stepno,
        COALESCE(NULLIF(TRIM(s.stepname), ''), NULLIF(TRIM(s.stepfullname), '')),
        NULL,
        NULL,
        r.recordno,
        r.recordname,
        r.beforerecordno
    FROM {{schema}}.comm_flowrecord r
    CROSS JOIN params p
    LEFT JOIN {{schema}}.comm_flowchart s
        ON s.flowchartid = r.flowchartid AND s.stepno = r.stepno
    WHERE r.flowchartid = p.target_flowchartid
)
SELECT row_type, flowchartid, flowchartname, pre_flowchartid,
       stepno, stepname, precondition, setactive,
       recordno, recordname, beforerecordno
FROM exported
ORDER BY row_type, flowchartid, stepno, recordno;
