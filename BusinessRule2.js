(function executeRule(current, previous /*null when async*/) {

    // Only act when human review is currently required. 
    if (current.x_2216229_sprint_1_human_review_required != true) {
        return;
    }

    // 1. Fulfiller posted an internal work note. 
    if (current.work_notes.changes()) {
        current.x_2216229_sprint_1_human_review_required = false;
        return;
    }

    // 2. Incident moved to Resolved, Closed, or Canceled. 
    if (
        current.state.changesTo(6) ||
        current.state.changesTo(7) ||
        current.state.changesTo(8)
    ) {
        current.x_2216229_sprint_1_human_review_required = false;
        return;
    }

})(current, previous);