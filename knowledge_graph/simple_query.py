from graph_cypher_query_tool import query_graph_with_trace

print("\n" + "="*50)
print("知识图谱查询系统（支持多轮对话上下文理解）")
print("="*50)
print("输入问题开始查询，输入 'exit' 退出，输入 'clear' 清空历史")
print("示例问题：和贵州茅台同行业的公司有哪些？")
print("后续提问：它们的财务指标怎么样？（系统会自动理解'它们'指前面的公司）")
print("="*50)

conversation_history = []

while True:
    question = input("\n请输入问题: ").strip()
    
    if question.lower() == 'exit':
        print("再见！")
        break
    
    if question.lower() == 'clear':
        conversation_history = []
        print("✓ 对话历史已清空")
        continue
    
    if not question:
        continue
    
    try:
        result = query_graph_with_trace(question, conversation_history=conversation_history)
        answer = result.get("answer", "")
        source = result.get("source", "knowledge_graph")
        fallback_reason = result.get("fallback_reason", "")

        if source == "knowledge_graph":
            print("\n[来源] 知识图谱")
        else:
            print("\n[来源] 大模型通用回答（未命中知识图谱）")
            if fallback_reason:
                print(f"[回退原因] {fallback_reason}")

        print(f"答案: {answer}")
        
        # 记录到对话历史
        conversation_history.append({"role": "user", "content": question})
        conversation_history.append({"role": "assistant", "content": answer})
        
    except Exception as e:
        print(f"错误: {e}")