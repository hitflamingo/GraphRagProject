# LangChain 版本兼容性解决方案

## 当前状态

系统已回退到**简化版本**（直接调用工具），以兼容当前的 LangChain 1.2.0 版本。

## 问题说明

### 当前环境
- **LangChain**: 1.2.0
- **requirements.txt 要求**: >= 0.3.0
- **问题**: `create_tool_calling_agent` 和 `AgentExecutor` 在 1.2.0 中不可用

### 架构影响

**简化版本**（当前）:
- ✅ 核心架构保持不变（Supervisor-Worker Pattern）
- ✅ LangGraph 工作流完整
- ✅ 所有功能可用
- ❌ Agent 内部失去 LLM 自主决策能力
- ❌ 无法实现"再看一眼"、"自愈机制"等智能特性

**完整版本**（需要升级后）:
- ✅ 所有简化版本的功能
- ✅ Agent 内部 LLM 自主决策
- ✅ "再看一眼"能力（JSON 解析失败时自动重试）
- ✅ 自愈机制（Neo4j 约束错误自动修正）
- ✅ 主动推理（Risk-Actuary 主动生成警告）

## 解决方案

### 方案 1: 升级 LangChain（推荐）

升级到 LangChain 0.3.0+ 以使用完整架构：

```bash
# 方法 1: 使用 pip 升级（推荐）
pip install --upgrade langchain>=0.3.0 langchain-openai>=0.2.0 langchain-core>=0.3.0

# 方法 2: 重新安装所有依赖
pip install -r requirements.txt --upgrade

# 方法 3: 创建新的虚拟环境（最干净）
conda create -n graphrag_swarm python=3.11
conda activate graphrag_swarm
pip install -r requirements.txt
```

**验证升级**:
```bash
python -c "import langchain; print(langchain.__version__)"
# 应该显示 0.3.x 或更高版本
```

**升级后恢复完整架构**:
升级完成后，可以恢复使用 `AgentExecutor` 的完整实现。代码已经准备好，只需要：
1. 取消注释 `create_xxx_agent()` 函数
2. 恢复使用 `agent_executor.invoke()` 而不是直接调用工具

### 方案 2: 使用 LangChain 1.2.0 兼容 API

如果必须使用 LangChain 1.2.0，可以尝试以下兼容方案：

```python
# 尝试使用 LangChain 1.2.0 的 API
from langchain.agents import create_agent
from langchain.agents.factory import AgentExecutor

# 或者使用 ReAct 模式
from langchain.agents import initialize_agent, AgentType
```

**注意**: 这个方案需要大量代码修改，不推荐。

### 方案 3: 保持当前简化版本

如果当前简化版本满足需求，可以继续使用：
- ✅ 所有核心功能可用
- ✅ 稳定可靠
- ✅ 易于调试
- ❌ 失去部分智能特性

## 推荐步骤

### 步骤 1: 检查当前版本

```bash
python -c "import langchain; print('LangChain:', langchain.__version__)"
python -c "import langchain_core; print('LangChain Core:', langchain_core.__version__)"
python -c "import langchain_openai; print('LangChain OpenAI:', langchain_openai.__version__)"
```

### 步骤 2: 备份当前环境

```bash
# 导出当前环境
pip freeze > requirements_current.txt

# 或者使用 conda
conda list --export > environment_current.yml
```

### 步骤 3: 升级 LangChain

```bash
# 升级核心包
pip install --upgrade langchain>=0.3.0 langchain-openai>=0.2.0 langchain-core>=0.3.0 langgraph>=0.2.0

# 验证
python -c "from langchain.agents import create_tool_calling_agent, AgentExecutor; print('✅ API available')"
```

### 步骤 4: 测试系统

```bash
# 运行验证脚本
python tests/validate_swarm.py

# 运行导入测试
python tests/test_imports.py
```

### 步骤 5: 恢复完整架构（可选）

如果升级成功，可以恢复完整架构：

1. **恢复 geo_analyst.py**:
   - 取消注释 `create_geo_analyst_agent()` 函数
   - 恢复使用 `agent_executor.invoke()`

2. **恢复 kg_librarian.py**:
   - 取消注释 `create_kg_librarian_agent()` 函数
   - 恢复使用 `agent_executor.invoke()`

3. **恢复 risk_actuary.py**:
   - 取消注释 `create_risk_actuary_agent()` 函数
   - 恢复使用 `agent_executor.invoke()`

## 版本兼容性矩阵

| LangChain 版本 | create_tool_calling_agent | AgentExecutor | 推荐方案 |
|---------------|---------------------------|---------------|----------|
| < 0.2.0 | ❌ 不存在 | ❌ 不存在 | 升级 |
| 0.2.x | ⚠️ 部分支持 | ✅ 可用 | 升级到 0.3+ |
| 0.3.0+ | ✅ 完全支持 | ✅ 完全支持 | ✅ 推荐 |
| 1.2.0 | ❌ 不存在 | ❌ 位置不同 | 升级或使用简化版 |

## 故障排查

### 问题 1: 升级后导入错误

```bash
# 清理缓存
pip cache purge
python -m pip install --upgrade --force-reinstall langchain langchain-openai langchain-core
```

### 问题 2: 版本冲突

```bash
# 检查冲突
pip check

# 解决冲突
pip install --upgrade --force-reinstall langchain langchain-openai langchain-core langgraph
```

### 问题 3: 其他包依赖旧版本

```bash
# 查看依赖树
pip show langchain

# 如果其他包强制旧版本，考虑创建新环境
conda create -n graphrag_new python=3.11
```

## 当前代码状态

所有智能体文件当前使用**简化版本**（直接调用工具）：

- ✅ `src/swarm/agents/geo_analyst.py` - 直接调用 `extract_features_tool`
- ✅ `src/swarm/agents/kg_librarian.py` - 直接调用工具链
- ✅ `src/swarm/agents/risk_actuary.py` - 直接调用工具链

**完整版本的代码已注释保留**，升级后可以快速恢复。

## 下一步

1. **立即**: 使用当前简化版本，系统完全可用
2. **短期**: 升级 LangChain 到 0.3.0+
3. **长期**: 恢复完整架构，启用所有智能特性

## 参考

- LangChain 迁移指南: https://python.langchain.com/docs/versions/
- LangGraph 文档: https://langchain-ai.github.io/langgraph/
- 项目 requirements.txt: `requirements.txt`

