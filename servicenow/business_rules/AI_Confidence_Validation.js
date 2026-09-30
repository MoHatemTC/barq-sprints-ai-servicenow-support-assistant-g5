/*
 * ServiceNow Business Rule Export
 * Name: AI Confidence Validation
 * Table: Incident [incident]
 * When: before   |  Insert: true  |  Update: true
 *
 * AI Confidence must be a number from 0.0 to 1.0 (both ends allowed:
 * an escalation with nothing retrieved is recorded as 0.0).
 * Empty is allowed (the incident has not been processed by the AI yet).
 * Out-of-range values are blocked: the record is not saved.
 *
 * Keep this identical to the rule in the PDI. The Python client validates
 * the same range (src/writeback/servicenow_writeback.py::_validate_confidence).
 */
(function executeRule(current, previous /*null when async*/) {

    var value = current.getValue(
        'x_2216229_sprint_1_ai_confidence'
    );

    // Empty confidence is allowed. gs.nil() covers null, undefined and ''.
    if (gs.nil(value)) {
        return;
    }

    var confidence = parseFloat(value);

    if (
        isNaN(confidence) ||
        confidence < 0 ||
        confidence > 1
    ) {
        gs.addErrorMessage(
            'AI Confidence must be between 0.0 and 1.0.'
        );

        current.setAbortAction(true);
    }

})(current, previous);
