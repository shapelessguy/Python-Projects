from cryptography.fernet import Fernet

# Function to generate a key and save it into a file
def write_key():
    key = Fernet.generate_key()
    with open("secret.key", "wb") as key_file:
        key_file.write(key)

# Function to load the key from the current directory
def load_key():
    return open("secret.key", "rb").read()

# Function to encrypt a message
def encrypt_message(message):
    key = load_key()
    f = Fernet(key)
    encrypted_message = f.encrypt(message.encode())
    return encrypted_message

# Function to decrypt a message
def decrypt_message(encrypted_message):
    key = load_key()
    f = Fernet(key)
    decrypted_message = f.decrypt(encrypted_message)
    return decrypted_message.decode()

# Example of usage:
if __name__ == "__main__":
    # write_key()  # Run this once to generate and save the key
    key = load_key()

    # Copy the encrypted password and copy it into the .env file as OUTLOOK_PASS
    encrypted = encrypt_message("PASSWORD_HERE")
    print("Encrypted:", encrypted)
