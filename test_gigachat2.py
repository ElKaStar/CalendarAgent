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
print(f"CLIENT_SECRET: {client_secret}")
print(f"SCOPE: {scope}")

# Variant 1: Use CLIENT_SECRET directly as base64 (original from .env was base64)
# But we already decoded it, so let's try encoding it back
original_secret_base64 = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
print(f"\nOriginal base64 (if it was): MDE5YTBiN2ItNjE2OC03OGEyLWJjYjAtMGZlOTg3NmRmMjM5OjUzZDYxZTc2LTNiYzEtNDM1OS05MWQ1LTRjZWM3MzM2MTJmNQ==")

# Variant 2: Encode client_id:client_secret
auth_string = f"{client_id}:{client_secret}"
auth_base64_v2 = base64.b64encode(auth_string.encode()).decode()

print(f"\nAuth base64 v2: {auth_base64_v2[:50]}...")

async def test_variant(auth_base64, variant_name):
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        try:
            response = await client.post(
                'https://ngw.devices.sberbank.ru:9443/api/v2/oauth',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json',
                    'RqUID': f'test-{variant_name}',
                    'Authorization': f'Basic {auth_base64}'
                },
                data={
                    'scope': scope
                }
            )
            
            print(f"\n{variant_name} - Status: {response.status_code}")
            print(f"{variant_name} - Response: {response.text[:500]}")
            
        except Exception as e:
            print(f"\n{variant_name} - Error: {e}")

# Test variant 2 (current approach)
async def main():
    await test_variant(auth_base64_v2, "V2")

asyncio.run(main())
