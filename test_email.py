from app.core.email import send_password_reset_email

try:
    send_password_reset_email(
        "asadullahaleem0@gmail.com",
        "http://localhost:3000/reset-password?token=test123"
    )
    print("Email sent successfully!")
except Exception as e:
    print(f"Error Type: {type(e).__name__}")
    print(f"Error Details: {e}")