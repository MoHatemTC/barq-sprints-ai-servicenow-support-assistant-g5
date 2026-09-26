(function executeRule(current, previous /*null when async*/) {

    var reviewField =
        'x_2216229_sprint_1_human_review_required';

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

    // Fulfiller added an internal work note.
    if (current.work_notes.changes()) {

        var workNote =
            current.work_notes.getJournalEntry(1);

        // Ignore AI-generated escalation notes.
        if (
            workNote &&
            workNote.indexOf('AI escalation reason:') != -1
        ) {
            return;
        }

        current.setValue(reviewField, false);
    }

})(current, previous);