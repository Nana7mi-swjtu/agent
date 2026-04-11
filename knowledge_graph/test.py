from graph_cypher_query_tool import _build_spark_llm

# 测试LLM连接
try:
    llm = _build_spark_llm()
    response = llm.invoke("你好，请简单介绍一下自己")
    print("✅ LLM连接成功！")
    print(f"回复: {response.content}")
except Exception as e:
    print(f"❌ 连接失败: {e}")