```javascript
/*
 * ServiceNow UI Action Export
 * Name: Reject AI Suggestion
 * Table: Incident [incident]
 * Action name: rejectAISuggestion
 *
 * Condition:
 * current.x_2216229_sprint_1_ai_status == 'suggested' &&
 * current.x_2216229_sprint_1_human_review_required == true
 */

function rejectAISuggestion() {
    if (!confirm('Reject this AI suggestion and escalate the incident?')) {
        return false;
    }

    g_form.setValue(
        'x_2216229_sprint_1_human_review_required',
        'false'
    );

    g_form.setValue(
        'x_2216229_sprint_1_ai_status',
        'escalated'
    );

    g_form.setValue(
        'work_notes',
        'AI suggestion rejected by fulfiller.'
    );

    g_form.save();
}
```
