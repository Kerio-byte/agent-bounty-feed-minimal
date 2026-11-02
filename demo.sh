#!/bin/sh
# demo.sh — prove the client works, in one command, in under a minute.
#
#   sh demo.sh            # all checks, compact output
#   sh demo.sh --full     # same, with the full listing output
#
# Exit code 0 means every step the README promises actually ran.

set -u
FULL=0
[ "${1:-}" = "--full" ] && FULL=1
PY=${PYTHON:-python3}
FAIL=0

step() {
    printf '\n--- %s\n' "$1"
    shift
    out=$("$@" 2>&1)
    code=$?
    if [ "$code" -eq 0 ]; then
        printf 'OK   exit 0\n'
        if [ "$FULL" -eq 1 ]; then
            printf '%s\n' "$out" | head -40
        else
            printf '%s\n' "$out" | head -4
        fi
    else
        printf 'FAIL exit %s\n%s\n' "$code" "$out" | head -12
        FAIL=1
    fi
}

printf 'client: feed_client.py, %s lines\n' "$(wc -l < feed_client.py | tr -d ' ')"
printf 'python: %s\n' "$("$PY" --version 2>&1)"

step "MCP handshake + stats + 5 bounties  (python3 feed_client.py)" $PY feed_client.py
step "static feed, no MCP                 (feed 3)" $PY feed_client.py feed 3
step "filters                             (bounties 3 --exclude kyc,github --min-usd 1)" \
    $PY feed_client.py bounties 3 --exclude kyc,github --min-usd 1
step "fresh window, required since        (new 2)" $PY feed_client.py new 2
step "zero-install entry point            (earn-now)" $PY feed_client.py earn-now

printf '\n--- usage errors must exit 2\n'
for mode in nosuchmode "--min-usd abc"; do
    # shellcheck disable=SC2086
    $PY feed_client.py $mode >/dev/null 2>&1
    code=$?
    if [ "$code" -eq 2 ]; then
        printf 'OK   %-14s exit 2\n' "$mode"
    else
        printf 'FAIL %-14s exit %s\n' "$mode" "$code"
        FAIL=1
    fi
done

printf '\n'
if [ "$FAIL" -eq 0 ]; then
    printf 'ALL STEPS PASSED\n'
else
    printf 'SOMETHING FAILED — see above\n'
fi
exit "$FAIL"
