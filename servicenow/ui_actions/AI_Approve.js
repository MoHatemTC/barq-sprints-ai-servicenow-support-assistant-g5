/*
 * ServiceNow UI Action Export
 * Name: Approve AI Suggestion
 * Table: Incident [incident]
 * Action name: approveAISuggestion
 * Client: true  |  Onclick: approveAISuggestion()
 *
 * Condition:
 * current.x_2216229_sprint_1_ai_status == 'suggested' &&
 * current.x_2216229_sprint_1_human_review_required == true &&
 * !gs.nil(current.x_2216229_sprint_1_ai_suggested_response)
 *
 * The AI response starts with an internal header line
 * ("Suggested resolution (pending human approval):"). That line is for the
 * fulfiller only, so it is removed before the text goes to the customer.
 */

function approveAISuggestion() {
    if (!confirm('Approve this AI suggestion and send it to the customer?')) {
        return false;
    }

    var suggestion = g_form.getValue(
        'x_2216229_sprint_1_ai_suggested_response'
    ) || '';

    // Remove the internal "(pending human approval)" header line.
    var customerText = suggestion
        .replace(/^\s*Suggested resolution \(pending human approval\):\s*/i, '')
        .trim();

    if (!customerText) {
        alert('The AI suggestion is empty. Nothing to send to the customer.');
        return false;
    }

    g_form.setValue('comments', customerText);

    g_form.setValue(
        'x_2216229_sprint_1_human_review_required',
        'false'
    );

    g_form.save();
}
