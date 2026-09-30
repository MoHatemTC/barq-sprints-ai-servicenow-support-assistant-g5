/*
 * ServiceNow Business Rule Export
 * Name: AI Lifecycle Guard
 * Table: Incident [incident]
 * When: before   |  Insert: false  |  Update: true
 *
 * Human Review Required is cleared when a HUMAN acts on the incident:
 *   - the incident moves to Resolved / Closed / Canceled, or
 *   - a human adds a work note.
 *
 * Notes written by the AI must NOT clear the flag. Since escalations now keep
 * Human Review checked, an AI note in the same update would otherwise switch
 * it off immediately. A note counts as written by the AI when:
 *   1. it starts with "[AI]" (every note added by the addworknote tool), or
 *      contains "AI escalation reason:" (written by escalate()), or
 *   2. the update was made by the AI integration user. Optional: create the
 *      system property  x_2216229_sprint_1.ai_integration_user  with that
 *      user's user name (the same account as SERVICENOW_USERNAME in .env).
 */
(function executeRule(current, previous /*null when async*/) {

    var reviewField =
        'x_2216229_sprint_1_human_review_required';

    var AI_NOTE_MARKERS = ['[AI]', 'AI escalation reason:'];

    var reviewValue = current.getValue(reviewField);

    // Only act when human review is currently required.
    if (reviewValue != 'true' && reviewValue != '1') {
        return;
    }

    // Terminal states:
    // Resolved = 6
    // Closed   = 7
    // Canceled = 8
    if (
        current.state.changesTo(6) ||
        current.state.changesTo(7) ||
        current.state.changesTo(8)
    ) {
        current.setValue(reviewField, false);
        return;
    }

    if (!current.work_notes.changes()) {
        return;
    }

    // Optional: everything the AI integration user writes is an AI note.
    var aiUser = gs.getProperty(
        'x_2216229_sprint_1.ai_integration_user',
        ''
    );
    if (aiUser && gs.getUserName() == aiUser) {
        return;
    }

    // In a "before" rule the new note is the pending value of the field.
    // If that is empty (rule configured as "after"), read the journal instead.
    var workNote = String(current.getValue('work_notes') || '');
    if (!workNote) {
        workNote = String(
            current.work_notes.getJournalEntry(1) || ''
        );
    }

    // Ignore AI-generated notes.
    for (var i = 0; i < AI_NOTE_MARKERS.length; i++) {
        if (workNote.indexOf(AI_NOTE_MARKERS[i]) != -1) {
            return;
        }
    }

    // A human wrote the note: the AI suggestion has been reviewed.
    current.setValue(reviewField, false);

})(current, previous);
