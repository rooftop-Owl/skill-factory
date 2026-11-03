#!/usr/bin/env bash
# Pass iff the worker wrote the token only the ab-fixture skill states.
# $1 = the run's clone, $2 = file holding the worker's final message.
[ "$(cat "$1/hello.txt" 2>/dev/null)" = "SF-FIXTURE-7" ]
