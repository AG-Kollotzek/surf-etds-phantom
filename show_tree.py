import os


def list_files(startpath):
    for root, dirs, files in os.walk(startpath):
        # Ignoriere Systemordner und virtuelle Umgebungen
        dirs[:] = [d for d in dirs if
                   not d.startswith('.') and d not in ['venv', '.venv', '__pycache__', '.idea', 'target']]

        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f'{indent}[{os.path.basename(root)}/]')
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            if not f.startswith('.'):
                print(f'{subindent}{f}')


if __name__ == "__main__":
    print("--- PROJEKT STRUKTUR ---")
    list_files(os.getcwd())