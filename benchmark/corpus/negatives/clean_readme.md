# Widget Service

A small internal service that resizes uploaded images and stores thumbnails
in object storage. Configuration is supplied entirely through environment
variables at deploy time; no credentials are checked into this repository.

## Local development

1. Copy `.env.example` to `.env` and fill in your own local values.
2. Run `make dev` to start the service with hot reload.
3. Run `make test` before opening a pull request.

## Architecture

Requests are validated, queued, processed by a worker pool, and the result
is written to the configured storage backend. See `docs/architecture.md`
for a diagram.
