# Read version from VERSION file
def get_version():
    try:
        with open("VERSION", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "1.0.0"  # fallback version
