"""Terminal chat:  python -m mannmitra.cli"""
from .agent import MannMitraAgent
from .llm import get_provider


def main():
    provider = get_provider()
    agent = MannMitraAgent(provider)
    print(f"MannMitra ({provider.name} mode). I'm an AI, not a doctor. Type /help, or 'quit' to exit.\n")
    print(agent.handle("cli-user", "/start", "cli") + "\n")
    while True:
        try:
            text = input("you> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.strip().lower() in ("quit", "exit"):
            break
        print("\nmannmitra> " + agent.handle("cli-user", text, "cli") + "\n")


if __name__ == "__main__":
    main()
