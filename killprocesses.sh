#!/bin/bash
# This script will give your decision.

NAME=$1
parentid=$(ps -o ppid= -p ${NAME})
kill -9 ${parentid}
