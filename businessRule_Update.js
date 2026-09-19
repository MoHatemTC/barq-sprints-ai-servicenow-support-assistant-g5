(function executeRule(current, previous) {

    try {

        // ==========================================
        // 1. Determine Operation
        // ==========================================

        var operation = "";

        // INSERT
        if (current.operation() == "insert") {

            operation = "insert";
        }

        // PUBLISHED -> RETIRED
        else if (
            current.operation() == "update" &&
            previous &&
            previous.getValue("workflow_state") == "published" &&
            current.getValue("workflow_state") == "retired"
        ) {

            operation = "delete";
        }

        // NORMAL UPDATE
        else if (current.operation() == "update") {

            operation = "update";
        }

        // UNSUPPORTED OPERATION
        else {

            gs.info(
                "[KB Sync] Unsupported operation. " +
                "sys_id=" + current.getValue("sys_id")
            );

            return;
        }


        // ==========================================
        // 2. Read Knowledge Article Fields
        // ==========================================

        var sysId = current.getValue("sys_id");

        // ServiceNow field is "number"
        // API contract field is "article_id"
        var articleId = current.getValue("number");

        var version = current.getValue("version");
        var shortDescription = current.getValue("short_description");
        var author = current.getValue("author");
        var kbCategory = current.getValue("kb_category");
        var workflowState = current.getValue("workflow_state");
        var sysUpdatedOn = current.getValue("sys_updated_on");
        var text = current.getValue("text");


        // ==========================================
        // 3. Validate Required Fields
        // ==========================================

        if (
            !sysId ||
            !articleId ||
            !version ||
            !shortDescription ||
            !author ||
            !kbCategory ||
            !workflowState ||
            !sysUpdatedOn ||
            !text
        ) {

            gs.error(
                "[KB Sync] Payload validation failed. " +
                "Required field is missing. " +
                "sys_id=" + sysId +
                ", article_id=" + articleId +
                ", version=" + version +
                ", short_description=" + shortDescription +
                ", author=" + author +
                ", kb_category=" + kbCategory +
                ", workflow_state=" + workflowState +
                ", sys_updated_on=" + sysUpdatedOn +
                ", text=" + text
            );

            return;
        }


        // ==========================================
        // 4. Build Payload
        // ==========================================

        var payload = {

            sys_id: sysId,
            article_id: articleId,
            version: version,
            short_description: shortDescription,
            author: author,
            kb_category: kbCategory,
            workflow_state: workflowState,
            sys_updated_on: sysUpdatedOn,
            text: text,
            operation: operation
        };


        // ==========================================
        // 5. Get Outbound REST Message
        // ==========================================

        var r = new sn_ws.RESTMessageV2(
            "KB Sync API",
            "KB Event"
        );


        // ==========================================
        // 6. Set Request Body
        // ==========================================

        r.setRequestBody(
            JSON.stringify(payload)
        );


        // ==========================================
        // 7. Execute Outbound Request
        // ==========================================

        var response = r.execute();


        // ==========================================
        // 8. Read Response
        // ==========================================

        var statusCode = response.getStatusCode();
        var responseBody = response.getBody();


        // ==========================================
        // 9. Handle Successful Response
        // ==========================================

        if (statusCode >= 200 && statusCode < 300) {

            gs.info(
                "[KB Sync] Event dispatched successfully. " +
                "operation=" + operation +
                ", article_id=" + articleId +
                ", sys_id=" + sysId +
                ", workflow_state=" + workflowState +
                ", status=" + statusCode
            );
        }


        // ==========================================
        // 10. Handle API Error
        // ==========================================

        else {

            gs.error(
                "[KB Sync] External API returned an error. " +
                "operation=" + operation +
                ", article_id=" + articleId +
                ", sys_id=" + sysId +
                ", status=" + statusCode +
                ", response=" + responseBody
            );
        }

    }

    catch (ex) {

        // ==========================================
        // 11. Exception Handling
        // ==========================================

        gs.error(
            "[KB Sync] Failed to dispatch event. " +
            "Error: " + ex.message
        );
    }

})(current, previous);