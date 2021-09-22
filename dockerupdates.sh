#!/bin/bash
 
# Declare a string array with type
declare -a StringArray=("gluetun" "transmission" "jackett" "sabnzbd" 
"sonarr" "radarr" "bazarr" "portainer" "caddy" "ddclient" "linuxserver-nextcloud"
"ombi" "rclone" "tautulli" "diun")
 
# Read the array values with space
for val in "${StringArray[@]}"; do
  echo "Updating container for $val"
  cd /home/pi/Docker/$val
  docker-compose pull 
  docker-compose up -d --remove-orphans
done
echo "Pruning docker images"
docker image prune -a -f