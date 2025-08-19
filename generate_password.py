import random, string
def generate_password():
            characters = string.ascii_letters + string.digits
            password = "".join(random.choices(characters, k=7))
            return password