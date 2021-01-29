rc_user="user"
rc_pass="pass"
json_fmt='{"main": {"BackupDir": "encrypted_gdrive_1:archive/hdd_videos/hdd_videos_%s", "MaxDuration": 21600000000000, "Transfers": 1}}'
json_str=$(printf "$json_fmt" "$(date +%d_%m_%Y)")
docker exec rclone rclone rc options/set --json "$json_str" --rc-user=$rc_user --rc-pass=$rc_pass
#options=$(docker exec rclone rclone rc options/get --rc-user=$rc_user --rc-pass=$rc_pass)
#echo $options
docker exec rclone rclone rc sync/sync --json '{"srcFs": "/data/hdd/videos", "dstFs": "encrypted_gdrive_1:hdd_videos", "_async": true}' --rc-user=$rc_user --rc-pass=$rc_pass
#docker exec -d rclone rclone rc options/set --json '{"main": {"BackupDir": ""}}' --rc-user=$rc_user --rc-pass=$rc_pass
