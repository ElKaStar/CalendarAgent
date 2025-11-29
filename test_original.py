import httpx
import asyncio

# Original base64 secret from .env
auth_base64 = 'MDE5YTBiN2ItNjE2OC03OGEyLWJjYjAtMGZlOTg3NmRmMjM5OjUzZDYxZTc2LTNiYzEtNDM1OS05MWQ1LTRjZWM3MzM2MTJmNQ=='

async def test():
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        try:
            response = await client.post(
                'https://ngw.devices.sberbank.ru:9443/api/v2/oauth',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json',
                    'RqUID': 'test-original',
                    'Authorization': f'Basic {auth_base64}'
                },
                data={
                    'scope': 'GIGACHAT_API_PERS'
                }
            )
            
            print(f'Status: {response.status_code}')
            print(f'Response: {response.text}')
            
        except Exception as e:
            print(f'Error: {e}')

asyncio.run(test())

