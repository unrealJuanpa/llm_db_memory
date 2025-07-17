from composite_agent import CompositeAgent
from llm_agent import LLMAgent

def main():
    agent = CompositeAgent(
        name="my_agent",
        server_ip="http://192.168.40.14:11434",
        model="deepseek-r1:latest",
        system_prompt="You are a helpful assistant.",
        max_interactions=16,
        retrieval_limit=16,
        debug_print=True
    )

    print("Type 'exit' to quit.")
    while True:
        user_input = input("You: ")
        if user_input.lower() in ("exit", "quit"):
            break
        response = agent.chat(user_input)
        print("Agent:", response)

if __name__ == "__main__":
    main()
