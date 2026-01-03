import random
from datetime import datetime, timedelta
from neo4j import GraphDatabase
from .config import load_settings


def seed_defect_history():
    settings = load_settings()
    if not settings.neo4j.uri:
        print("Error: Neo4j URI not configured.")
        return

    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password)
    )

    print("🌱 Seeding simulated historical defect data for Graph RAG...")

    queries = [
        # 1. 确保 DefectRecord 的 ID 唯一性约束
        "CREATE CONSTRAINT IF NOT EXISTS FOR (d:DefectRecord) REQUIRE d.id IS UNIQUE",

        # 2. 场景一：针对工序 20 (NC Routing/铣削)
        # 修改点：使用 WHERE toString(...) 进行宽松匹配，兼容数字和字符串
        """
        MATCH (p:ProcessStep)
        WHERE toString(p.step_id) CONTAINS '20' 
           OR p.step_id = 20 
           OR p.name CONTAINS 'Routing'
        WITH p LIMIT 1
        UNWIND range(1, 5) as i
        MERGE (d:DefectRecord {id: 'DEF_NC_' + toString(i)})
        SET d.type = 'SizeDeviation',
            d.feature_size = 6.2,
            d.severity = 0.85,
            d.description = 'Hole diameter undersize due to cutter wear',
            d.occurred_at = toString(datetime() - duration({days: i*10}))
        MERGE (p)-[:HAS_DEFECT_HISTORY]->(d)
        """,

        # 3. 场景二：针对工序 80 (Forming/成型)
        """
        MATCH (p:ProcessStep)
        WHERE toString(p.step_id) CONTAINS '80' 
           OR p.step_id = 80 
           OR p.name CONTAINS 'Forming'
        WITH p LIMIT 1
        UNWIND range(1, 3) as i
        MERGE (d:DefectRecord {id: 'DEF_FORM_' + toString(i)})
        SET d.type = 'Springback',
            d.feature_size = 90.0,
            d.severity = 0.6,
            d.description = 'Angle springback exceeds tolerance',
            d.occurred_at = toString(datetime() - duration({days: i*15}))
        MERGE (p)-[:HAS_DEFECT_HISTORY]->(d)
        """
    ]

    with driver.session() as session:
        for idx, q in enumerate(queries):
            try:
                result = session.run(q)
                # 获取执行统计，确认是否真的写入了数据
                summary = result.consume()
                counters = summary.counters
                if idx > 0:  # 跳过约束创建的检查
                    if counters.nodes_created > 0 or counters.relationships_created > 0:
                        print(
                            f"   Query {idx}: ✅ Success! Created {counters.nodes_created} nodes, {counters.relationships_created} relationships.")
                    else:
                        print(f"   Query {idx}: ⚠️  Executed but NO data created. (Did not match any ProcessStep?)")
            except Exception as e:
                print(f"   Query {idx} failed: {e}")

    print("------------------------------------------------")
    print("If you saw 'Success' above, the Risk Miner is now active.")
    driver.close()


if __name__ == "__main__":
    seed_defect_history()