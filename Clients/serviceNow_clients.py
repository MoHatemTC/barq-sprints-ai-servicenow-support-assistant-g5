import httpx
import os


class serviceNow_client:

    @staticmethod
    async def KB_connection():

        url = (
            f"{os.getenv('SERVICENOW_INSTANCE_URL', '').rstrip('/')}"
            "/api/now/table/kb_knowledge"
        )

        username = os.getenv("SERVICENOW_USERNAME")
        password = os.getenv("SERVICENOW_PASSWORD")
        author_sys_id = os.getenv("AUTHOR_SYS_ID")

        headers = {
            "Accept": "application/json"
        }

        params = {
            "sysparm_query": (
                f"author={author_sys_id}"
                "^workflow_state=published"
            ),
            "sysparm_fields": (
                "number,"
                "short_description,"
                "author,"
                "category,"
                "workflow_state,"
                "sys_updated_on,"
                "text,"
                "version"
            )
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url=url,
                params=params,
                auth=(username, password),
                headers=headers
            )

            response.raise_for_status()

            return response.json()