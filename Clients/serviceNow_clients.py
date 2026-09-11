import httpx
import os


class serviceNow_client:

    @staticmethod
    async def KB_connection():
        url = f"{os.getenv('SERVICENOW_INSTANCE_URL', '').rstrip('/')}/api/now/table/kb_knowledge"
        username = os.getenv("SERVICENOW_USERNAME")
        password = os.getenv("SERVICENOW_PASSWORD")
        header = {
            "Accept": "application/json"
        }
        # Confirmed via ServiceNow UI (i) icon → URL sys_id
        kb_knowledge_base_id = os.getenv("SERVICENOW_KB_ID")
        kb_category_id = os.getenv("SERVICENOW_KB_CATEGORY_ID")

        params = {
            "sysparm_query": (
                f"kb_knowledge_base={kb_knowledge_base_id}"
                f"^kb_category={kb_category_id}"
                f"^workflow_state=published"
            ),
            "sysparm_fields": "number,short_description,author,kb_category,workflow_state,sys_updated_on,text,version",
            "sysparm_display_value": "all"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url=url,
                params=params,
                auth=(username, password),
                headers=header
            )
            response.raise_for_status()
            return response.json()