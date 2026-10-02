/*
 * ServiceNow UI Action Export
 * Name: Edit AI Suggestion
 * Table: Incident [incident]
 * Action name: editAISuggestion
 * Client: true  |  Onclick: editAISuggestion()
 *
 * Condition:
 * current.x_2216229_sprint_1_ai_status == 'suggested' &&
 * current.x_2216229_sprint_1_human_review_required == true &&
 * !gs.nil(current.x_2216229_sprint_1_ai_suggested_response)
 *
 * Copies the suggestion into Additional comments (customer-visible) so the
 * fulfiller can edit it. The internal "(pending human approval)" header is
 * removed here too, so it can never reach the customer by accident.
 */

function editAISuggestion() {

    var suggestion = g_form.getValue(
        'x_2216229_sprint_1_ai_suggested_response'
    ) || '';

    g_form.setValue(
        'comments',
        suggestion.replace(/^\s*Suggested resolution \(pending human approval\):\s*/i, '').trim()
    );

}
