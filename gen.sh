#!/bin/bash

rm -rf tmp
mkdir tmp
cp -r bin public tmp
cp tasks.json tmp

echo -n "-- project uuid: "
read -r project_uuid
echo -n "-- install path: "
read -r install_path
mkdir -p $install_path
if [ $? -ne 0 ]; then
	echo "-- fail to create path $install_path"
	exit 1
fi
echo -n "-- http port: "
read -r http_port

json_path=${install_path}/tasks.json
trigger_path=${install_path}/bin/trigger.py
sed -i "s#JSONPATH#$json_path#g" tmp/bin/bridge.py
sed -i "s#TRIGGERPATH#${trigger_path}#g" tmp/bin/bridge.py
sed -i "s#HTTP_PORT#$http_port#g" tmp/bin/bridge.py
sed -i "s#HTTP_PORT#$http_port#g" tmp/bin/trigger.py
sed -i "s#HTTP_PORT#$http_port#g" tmp/public/index.htm

mv tmp/* $install_path
rm -rf tmp

echo "-- complete !"