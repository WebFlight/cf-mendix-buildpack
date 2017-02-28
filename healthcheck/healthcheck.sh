#!/bin/bash
min_live_time=3600
total_live_time=$(($min_live_time + ${CF_INSTANCE_INDEX} * 200))
counter=0

function killAllVcapProcesses {
  killall -u vcap  
}

while :
do
  # if ! pgrep -x "java" > /dev/null
  # then
  #   killAllVcapProcesses 
  #   break
  # fi
  if [ $total_live_time -lt $counter ]
    then
    killAllVcapProcesses
    break
  fi
  echo $counter
  let counter=counter+1
  sleep 1
done
