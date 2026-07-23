from agents.queen.service import QueenService

def main():
    service = QueenService()
    goal="Build a multi-agent os"
    strategy=service.generate_strategy(goal)
    print("\n=====Generated Summary=====\n")
    print(strategy)

if __name__=="__main__":
    main()