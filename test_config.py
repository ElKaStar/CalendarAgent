import os
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv('GIGACHAT_CLIENT_ID')
client_secret = os.getenv('GIGACHAT_CLIENT_SECRET')

print(f"CLIENT_ID: {client_id}")
print(f"CLIENT_ID length: {len(client_id) if client_id else 0}")
print(f"CLIENT_SECRET: {client_secret[:50]}...{client_secret[-10:] if client_secret and len(client_secret) > 60 else ''}")
print(f"CLIENT_SECRET length: {len(client_secret) if client_secret else 0}")
print(f"CLIENT_SECRET has newline: {'\\n' in (client_secret or '')}")
print(f"CLIENT_SECRET has spaces: {' ' in (client_secret or '')}")
print(f"CLIENT_SECRET repr: {repr(client_secret[:100]) if client_secret else 'None'}")

# Проверяем base64 encoding
if client_id and client_secret:
    import base64
    auth_string = f"{client_id}:{client_secret}"
    auth_base64 = base64.b64encode(auth_string.encode()).decode()
    print(f"\nAuth string length: {len(auth_string)}")
    print(f"Auth base64: {auth_base64[:50]}...")
    print(f"Auth base64 length: {len(auth_base64)}")

