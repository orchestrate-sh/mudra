#!/bin/bash
NAME=$1
SLEEP_SECONDS=$2

echo Check script for DNS $NAME running...
FAIL=$(($RANDOM % 3))
sleep $SLEEP_SECONDS
if [ "$FAIL" -eq "0" ]; then
   echo "FAIL"
   exit
fi
echo Successful.
