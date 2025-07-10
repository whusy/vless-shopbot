import pyotp
import dotenv
import os
import logging

dotenv.load_dotenv()
logger = logging.getLogger(__name__)

secret_key = os.getenv("TOPT")

def getTOTP():
    try:
        totp = pyotp.TOTP(secret_key)
        return totp.now()
    except Exception as e:
        logger.error(f"Error creating TOTP object: {e}", exc_info=True)
        logger.warning("Ensure your TOPT secret key is a valid Base32 encoded string in .env file.")
        return None
    
if __name__ == "__main__":
    otp_code = getTOTP()
    if otp_code:
        print(f"Generated OTP code: {otp_code}")
    else:
        print("Failed to generate OTP code.")