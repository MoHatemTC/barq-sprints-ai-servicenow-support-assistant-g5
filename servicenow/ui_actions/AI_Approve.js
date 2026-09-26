```javascript
/*
 * ServiceNow UI Action Export
 * Name: Approve AI Suggestion
 * Table: Incident [incident]
 * Action name: approveAISuggestion
 *
 * Condition:
 * current.x_2216229_sprint_1_ai_status == 'suggested' &&
 * current.x_2216229_sprint_1_human_review_required == true &&
 * !gs.nil(current.x_2216229_sprint_1_ai_suggested_response)
 */

function approveAISuggestion() {
    if (!confirm('Approve this AI suggestion and send it to the customer?')) {
        return false;
    }

    g_form.setValue(
        'comments',
        g_form.getValue('x_2216229_sprint_1_ai_suggested_response')
    );

    g_form.setValue(
        'x_2216229_sprint_1_human_review_required',
        'false'
    );

    g_form.save();
}
```
