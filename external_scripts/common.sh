#!/bin/bash
#
# Common functions for mudra external scripts

# DRYRUN with a default of False
DRYRUN="${DRYRUN:=False}"
DRYRUN_OUTFILE_PATH="logs/dryrun.log"
touch ${DRYRUN_OUTFILE_PATH}

# Run common.sh only once.
test -n "${MUDRA_COMMON_SH__:-}" || declare -i MUDRA_COMMON_SH__=0
if (( MUDRA_COMMON_SH__++ == 0 )); then
  
# kubectl override to implement retry logic
function kubectl() {
    local count=1
    local max_retry=3
    local result=0
    # If DRYRUN is set, then just echo the command to DRYRUN_OUTFILE_PATH and exit 0
    if [ -n "${DRYRUN:-}" ]; then
        echo "$(date --rfc-3339=seconds) INFO: Executing, kubectl ${@}" >> "${DRYRUN_OUTFILE_PATH}"
        echo "INFO: DRYRUN Enabled, Would have executed, kubectl ${@}" >&2
        exit 0
    else
        echo "$(date --rfc-3339=seconds) INFO: Executing, kubectl ${@}" >&2
    fi
    until command kubectl ${@}; do
        result="$?"
        [[ ${count} -eq ${max_retry} ]] && echo "FAIL: kubectl command, kubectl ${@}" >&2 && exit ${result}
        sleep 1
        count=$(($count + 1))
        echo "WARN: Try #${count}/${max_retry}" >&2
    done
}

fi # once common.sh
