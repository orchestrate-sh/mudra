#!/usr/bin/env bash

touch /tmp/mudra/dbs.swap
while read line; do
  nohup python node_interfaces/Database.py swap "$line" &
done </tmp/mudra/dbs.swap
rm -rf /tmp/mudra/dbs.swap

touch /tmp/mudra/dbs.commit_swap
while read line; do
  python node_interfaces/Database.py swap "$line"
done </tmp/mudra/dbs.commit_swap
rm -rf /tmp/mudra/dbs.commit_swap

touch /tmp/mudra/dbs.cutover
while read line; do
  nohup python node_interfaces/Database.py cutover "$line" &
done </tmp/mudra/dbs.cutover
rm -rf /tmp/mudra/dbs.cutover

touch /tmp/mudra/dbs.test
while read line; do
  nohup python node_interfaces/Database.py test "$line" &
done </tmp/mudra/dbs.test
rm -rf /tmp/mudra/dbs.test
