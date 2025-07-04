import pyotp
import dotenv
import os

dotenv.load_dotenv()

secret_key = os.getenv("TOPT")

def getTOTP():
    try:
        totp = pyotp.TOTP(secret_key)
        return totp.now()
    except Exception as e:
        print(f"Error creating TOTP object or generating code: {e}")
        print("Ensure your secret key is a valid Base32 encoded string.")

if __name__ == "__main__":
    print(getTOTP())