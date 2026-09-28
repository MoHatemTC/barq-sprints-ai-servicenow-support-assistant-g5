(function executeRule(current, previous) {

    var value = current.getValue(
        'x_2216229_sprint_1_ai_confidence'
    );

    // Empty confidence is allowed
    if (value == '') {
        return;
    }

    var confidence = parseFloat(value);

    if (isNaN(confidence) || confidence <= 0 || confidence >= 1) {
        gs.addErrorMessage(
            'AI Confidence must be strictly between 0.0 and 1.0.'
        );
    }

})(current, previous);