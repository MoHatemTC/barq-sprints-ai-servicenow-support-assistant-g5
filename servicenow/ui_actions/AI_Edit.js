```javascript
/*
 * ServiceNow UI Action Export
 * Name: Edit AI Suggestion
 * Table: Incident [incident]
 * Action name: editAISuggestion
 *
 * Condition:
 * current.x_2216229_sprint_1_ai_status == 'suggested' &&
 * current.x_2216229_sprint_1_human_review_required == true &&
 * !gs.nil(current.x_2216229_sprint_1_ai_suggested_response)
 */

function editAISuggestion() {

    g_form.setValue(
        'comments',
        g_form.getValue('x_2216229_sprint_1_ai_suggested_response')
    );

}
```
