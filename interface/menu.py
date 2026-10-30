def show_menu():
    print("        ================================")
    print("                  Pylens CLI            ")
    print("        ================================")
    print(
        """
        1. Start monitoring
        2. Manage execution
        3. Stop execution
        4. Performance reports
        5. Execution history
        6. System resources
        7. Logs
        8. Settings
        9. About PyLens

        0. Exit

        ================================""")

def get_user_choice():
    choice = int(input("Select an option: "))
    return choice

def main():
    show_menu()
    choice = get_user_choice()
