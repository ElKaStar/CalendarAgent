import os
import base64
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv('GIGACHAT_CLIENT_ID')
client_secret = os.getenv('GIGACHAT_CLIENT_SECRET')
scope = os.getenv('GIGACHAT_SCOPE', 'GIGACHAT_API_PERS')

print(f"CLIENT_ID: {client_id}")
print(f"CLIENT_SECRET length: {len(client_secret)}")
print(f"SCOPE: {scope}")

auth_string = f"{client_id}:{client_secret}"
auth_base64 = base64.b64encode(auth_string.encode()).decode()

print(f"\nAuth string: {auth_string[:50]}...")
print(f"Auth base64: {auth_base64[:50]}...")

async def test():
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        try:
            response = await client.post(
                'https://ngw.devices.sberbank.ru:9443/api/v2/oauth',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json',
                    'RqUID': 'test-123',
                    'Authorization': f'Basic {auth_base64}'
                },
                data={
                    'scope': scope
                }
            )
            
            print(f"\nStatus: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            
        except Exception as e:
            print(f"\nError: {e}")

asyncio.run(test())

