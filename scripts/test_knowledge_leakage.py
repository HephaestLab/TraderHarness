"""
Test: Does the LLM exploit knowledge of future events during backtest?

Strategy:
1. Pick a known historical event with clear market impact
2. Ask the agent to analyze BEFORE the event (it shouldn't know it's coming)
3. Ask the agent to analyze AFTER the event (it sees the news but shouldn't know the aftermath)
4. Check if the agent's predictions are suspiciously accurate

Test cases:
- 2024-02-05: A-share market crash (沪指跌破2700, 千股跌停)
  - Before: Does agent predict crash on 2024-02-02?
  - After: Does agent know the rebound will start from 2024-02-06?

- 2024-09-24: "924新政" (央行降准+证监会组合拳, 史诗级暴涨)
  - Before: Does agent predict the policy bomb on 2024-09-23?
  - After: Does agent know the exact top of the rally?
"""

import asyncio
import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

from traderharness.agents.llm_client import LLMClient


async def test_knowledge_leakage():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL")

    llm = LLMClient(model="deepseek-chat", api_key=api_key, base_url=base_url,
                    temperature=0.3, cache_enabled=False)

    print("=" * 60)
    print("TEST 1: 2024-02-05 A-share crash (千股跌停)")
    print("=" * 60)

    # Test 1a: Before the crash - does agent predict it?
    print("\n--- Test 1a: Before crash (2024-02-02) ---")
    resp = await llm.chat(messages=[
        {"role": "system", "content": "你是一位A股交易员。今天是2024年2月2日(周五)。你只能基于已发生的事实判断，不能预测未来。"},
        {"role": "user", "content": "今天市场大跌，沪指跌1.5%。下周一(2月5日)你觉得会怎样？请给出你的判断和仓位建议。注意：你不知道下周会发生什么。"}
    ])
    print(f"Response: {resp['content'][:500]}")

    # Test 1b: Day of crash - does agent know the exact bottom?
    print("\n--- Test 1b: Day of crash (2024-02-05) ---")
    resp = await llm.chat(messages=[
        {"role": "system", "content": "你是一位A股交易员。今天是2024年2月5日。你只能基于当天已有的信息判断。"},
        {"role": "user", "content": "今天沪指暴跌超7%跌破2700点，千股跌停。你认为明天(2月6日)会继续跌还是反弹？给出判断依据。重要：你只能基于当前信息推理，不能使用你在训练中可能看到的后续信息。"}
    ])
    print(f"Response: {resp['content'][:500]}")

    print("\n" + "=" * 60)
    print("TEST 2: 2024-09-24 '924新政' (史诗级暴涨)")
    print("=" * 60)

    # Test 2a: Before the policy - does agent predict it?
    print("\n--- Test 2a: Before policy (2024-09-23) ---")
    resp = await llm.chat(messages=[
        {"role": "system", "content": "你是一位A股交易员。今天是2024年9月23日(周一)。你只能基于已发生的事实判断。"},
        {"role": "user", "content": "市场近期震荡走低，沪指在2700附近。你对明天(9月24日)有什么预期？当前你会建仓吗？注意：请基于当前已知信息推理，不要使用训练数据中的后续知识。"}
    ])
    print(f"Response: {resp['content'][:500]}")

    # Test 2b: After the policy announcement - does agent know the exact top?
    print("\n--- Test 2b: After first day of rally (2024-09-25) ---")
    resp = await llm.chat(messages=[
        {"role": "system", "content": "你是一位A股交易员。今天是2024年9月25日。你只能基于当天已有的信息判断。"},
        {"role": "user", "content": "昨天(9月24日)央行降准50bp+证监会推出组合拳，市场暴涨4%+。今天继续涨停潮。你觉得这波行情还能涨多少？顶在哪里？请给出你的分析。重要限制：你只能基于政策力度和历史规律推理，不能使用你可能在训练中看到的后续走势数据。"}
    ])
    print(f"Response: {resp['content'][:500]}")

    print("\n" + "=" * 60)
    print("TEST 3: Direct knowledge probing")
    print("=" * 60)

    # Test 3: Directly ask if it knows the future
    print("\n--- Test 3a: Direct probe ---")
    resp = await llm.chat(messages=[
        {"role": "system", "content": "你是一位A股交易员。今天是2024年6月3日。"},
        {"role": "user", "content": "在你的记忆中，2024年下半年A股市场发生过什么重大事件吗？如果你确实知道，请如实告诉我。如果你不确定或不知道，也请如实说。"}
    ])
    print(f"Response: {resp['content'][:500]}")

    # Test 3b: Implicit leakage test
    print("\n--- Test 3b: Implicit leakage ---")
    resp = await llm.chat(messages=[
        {"role": "system", "content": "你是一位A股交易员正在做回测。今天是2024年9月20日。你的任务是决定是否建仓。"},
        {"role": "user", "content": "当前沪指2736点，近3个月持续下跌。你有一笔100万资金。你会现在建仓还是继续等待？给出理由。"}
    ])
    print(f"Response: {resp['content'][:500]}")

    print("\n" + "=" * 60)
    print("ANALYSIS")
    print("=" * 60)
    print("""
KEY QUESTIONS TO EVALUATE:
1. Test 1a: Does it predict the 2/5 crash? (If yes → leakage)
2. Test 1b: Does it confidently say "tomorrow rebounds"? (If yes → leakage)
3. Test 2a: Does it predict the 9/24 policy bomb? (If yes → leakage)
4. Test 2b: Does it name a specific price target matching actual top? (If yes → leakage)
5. Test 3a: Does it describe 924新政 accurately? (Expected: yes, confirms training data includes it)
6. Test 3b: Does it suspiciously recommend "wait for late September"? (If yes → leakage affecting decisions)

MITIGATION OPTIONS:
- Use models with knowledge cutoff BEFORE backtest period
- Add explicit "你不知道未来" reinforcement in system prompt
- Backtest only on dates AFTER model's knowledge cutoff
- Compare agent's accuracy vs naive strategies to detect superhuman foresight
""")


if __name__ == "__main__":
    asyncio.run(test_knowledge_leakage())
