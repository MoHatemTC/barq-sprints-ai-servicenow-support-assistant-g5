import httpx
import os


class serviceNow_client:

    @staticmethod
    async def KB_connection():
        url = f"{os.getenv('SERVICENOW_INSTANCE_URL', '').rstrip('/')}/api/now/table/kb_knowledge"

        username = os.getenv("SERVICENOW_USERNAME")
        password = os.getenv("SERVICENOW_PASSWORD")

        headers = {
            "Accept": "application/json"
        }

        params = {
            "sysparm_query": "workflow_state=published"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url=url,
                auth=(username, password),
                headers=headers,
                params=params
            )

            response.raise_for_status()
            return response.json()