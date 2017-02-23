if ! pgrep -x "java" > /dev/null
then
    killall -u vcap  
fi