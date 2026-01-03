"""
Neo4j Schema Fix Script - 修复约束冲突

运行此脚本来清理旧约束并重建正确的Schema
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from neo4j import GraphDatabase
from src.config import load_settings


def fix_neo4j_constraints():
    """清理旧约束，重建正确的Schema"""
    settings = load_settings()
    
    if not settings.neo4j.uri:
        print("Error: NEO4J_URI not configured in .env")
        return
    
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password)
    )
    
    try:
        with driver.session() as session:
            print("=" * 60)
            print("Neo4j Schema Fix Tool")
            print("=" * 60)
            
            # 1. 查看当前所有约束
            print("\n[1/4] Current constraints:")
            result = session.run("SHOW CONSTRAINTS")
            constraints = list(result)
            
            if not constraints:
                print("  No constraints found.")
            else:
                for record in constraints:
                    print(f"  - {record.get('name', 'unnamed')}: {record.get('entityType', '')} {record.get('labelsOrTypes', '')} on {record.get('properties', [])}")
            
            # 2. 删除GeoFeature相关的旧约束
            print("\n[2/4] Dropping old GeoFeature constraints...")
            
            # 尝试删除可能存在的旧约束
            old_constraint_patterns = [
                "DROP CONSTRAINT constraint_geofeature_feature_id IF EXISTS",
                "DROP CONSTRAINT IF EXISTS FOR (f:GeoFeature) REQUIRE f.feature_id IS UNIQUE",
            ]
            
            for pattern in old_constraint_patterns:
                try:
                    session.run(pattern)
                    print(f"  ✓ Dropped: {pattern}")
                except Exception as e:
                    print(f"  ℹ Skip: {pattern} ({e.__class__.__name__})")
            
            # 3. 删除所有数据（可选，取消注释以启用）
            print("\n[3/4] Data cleanup (optional):")
            response = input("  Delete all existing data? [y/N]: ").lower()
            
            if response == 'y':
                session.run("MATCH (n) DETACH DELETE n")
                print("  ✓ All data deleted")
            else:
                print("  ℹ Data preserved")
            
            # 4. 重建正确的约束
            print("\n[4/4] Creating correct constraints...")
            
            constraints_to_create = [
                ("Part.part_id", "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Part) REQUIRE p.part_id IS UNIQUE"),
                ("GeoFeature.feature_uid", "CREATE CONSTRAINT IF NOT EXISTS FOR (f:GeoFeature) REQUIRE f.feature_uid IS UNIQUE"),
                ("ProcessAction.action_id", "CREATE CONSTRAINT IF NOT EXISTS FOR (a:ProcessAction) REQUIRE a.action_id IS UNIQUE"),
                ("ImageROI.id", "CREATE CONSTRAINT IF NOT EXISTS FOR (r:ImageROI) REQUIRE r.id IS UNIQUE"),
                ("ProcessStep.step_id", "CREATE CONSTRAINT IF NOT EXISTS FOR (ps:ProcessStep) REQUIRE ps.step_id IS UNIQUE"),
                ("ProcessParam.param_id", "CREATE CONSTRAINT IF NOT EXISTS FOR (pp:ProcessParam) REQUIRE pp.param_id IS UNIQUE"),
                ("Standard.standard_id", "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Standard) REQUIRE s.standard_id IS UNIQUE"),
                ("Resource.resource_id", "CREATE CONSTRAINT IF NOT EXISTS FOR (res:Resource) REQUIRE res.resource_id IS UNIQUE"),
                ("Tolerance.tolerance_id", "CREATE CONSTRAINT IF NOT EXISTS FOR (tol:Tolerance) REQUIRE tol.tolerance_id IS UNIQUE"),
            ]
            
            for name, cypher in constraints_to_create:
                try:
                    session.run(cypher)
                    print(f"  ✓ Created: {name}")
                except Exception as e:
                    print(f"  ℹ Already exists: {name}")
            
            print("\n" + "=" * 60)
            print("✅ Schema fix completed!")
            print("=" * 60)
            print("\nYou can now run your commands normally.")
            
    finally:
        driver.close()


if __name__ == "__main__":
    fix_neo4j_constraints()

