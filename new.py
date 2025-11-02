import random


player_choice = input("Enter a Choice (rock, paper, scissors: )")
options = ["rock", "paper", "scissors"]
computer_choice = random.choice(options)
print(f"you chose {player_choice}, computer chose {computer_choice}")
if player_choice == computer_choice:
    print("it is a tie")
elif player_choice == "rock" and computer_choice == "paper":
    print("paper beats rock! you lose!")
elif player_choice == "rock" and computer_choice == "scissors":
    print("rock beats scissors! you win!")
elif player_choice == "paper" and computer_choice == "rock":
    print("paper covers rock! you win!")
elif player_choice == "paper" and computer_choice == "scissors":
    print("scissors beat paper! you lose!")
elif player_choice == "scissors" and computer_choice == "rock":
    print("rock beats scissors! you lose")
elif player_choice == "scissors" and computer_choice == "paper":
    print("scissors beat paper! you win!")
else:
    print("invalid input")
