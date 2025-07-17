from composite_agent import CompositeAgent
from llm_agent import LLMAgent

def main():
    agent = CompositeAgent(
        agent_name="my_agent",
        server_ip="http://192.168.40.14:11434",
        expert_model="deepseek-r1:latest",
        tagger_model="gemma3:latest",
        interpreter_model="gemma3:latest",
        system_prompt="You are a helpful assistant.",
        short_term_items=16,
        long_term_top_results=6
    )

    print("Type 'exit' to quit.")
    while True:
        user_input = input("You: ")
        if user_input.lower() in ("exit", "quit"):
            break
        response = agent.chat(user_input)
        print("Agent:", response)
        print()

if __name__ == "__main__":
    main()
