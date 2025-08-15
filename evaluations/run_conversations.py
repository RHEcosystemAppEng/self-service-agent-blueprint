#!/usr/bin/env python3

from helpers.run_conversation_flow import ConversationFlowTester

if __name__ == "__main__":
    tester = ConversationFlowTester()
    tester.run_flows(
        "conversations_config/conversations", "results/conversation_results"
    )
