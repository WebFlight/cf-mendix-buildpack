#!/bin/bash
while :
do
  if ! pgrep -x "java" > /dev/null
  then
      killall -u vcap  
  fi
  sleep 1
done
