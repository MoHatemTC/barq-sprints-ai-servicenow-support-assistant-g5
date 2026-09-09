import httpx
import os


class serviceNow_client:
    
    async def KB_connection():
        url = f"{os.getenv("SERVICENOW_URL")}/api/sn_km_api/knowledge/articles"
        username = os.getenv("USERNAME")
        password = os.getenv("PASSWORD")
        header = {
            "Accept" : "application/json"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url=url,
                auth=(username , password),
                headers=header
                )
            response.raise_for_status()
            return response.json()