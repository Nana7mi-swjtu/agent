# Logging System

This backend uses a shared logging foundation with three categories:

- `app`: runtime diagnostics, warnings, exceptions, background job lifecycle
- `access`: one record per HTTP request
- `audit`: user-triggered business actions

## Environment Variables

- `LOG_LEVEL`: minimum enabled log level, such as `DEBUG`, `INFO`, or `WARNING`
- `LOG_DIR`: output directory for rotating log files
- `LOG_MAX_BYTES`: max size of each log file before rotation
- `LOG_BACKUP_COUNT`: number of rotated files to retain
- `LOG_SERVICE_NAME`: static service label written to log records
- `LOG_ENVIRONMENT`: environment label such as `development` or `production`

## Outputs

The logging bootstrap writes to two sinks at the same time:

- console: compact text output for local development and terminal debugging
- files: newline-delimited JSON logs under `LOG_DIR`

Default file layout:

- `app.log`
- `access.log`
- `audit.log`

## Correlation Fields

The logging context injects these fields when available:

- `request_id`
- `user_id`
- `workspace_id`
- `job_id`
- `document_id`
- `record_id`
- `method`
- `path`
- `remote_addr`

The backend accepts or generates `X-Request-ID` for each request and returns it in the response headers.

## Debugging Workflow

1. Start from `access.log` using `request_id`, path, status code, and latency.
2. Follow the same `request_id` in `audit.log` to see which business action was attempted.
3. Check `app.log` for exceptions, warnings, or async job lifecycle events with the same correlation fields.
4. For RAG incidents, follow `job_id` from enqueue to `rag.index.started`, `rag.index.finished`, or `rag.index.failed`.

## Redaction Rules

The logging layer suppresses or masks known sensitive values before writing to console or files.

Protected values include:

- passwords
- verification codes
- reset codes
- API keys
- raw authorization credentials

Email addresses should be masked when full values are not operationally necessary. Full request bodies, uploaded file contents, and model prompts should not be written to audit logs.
