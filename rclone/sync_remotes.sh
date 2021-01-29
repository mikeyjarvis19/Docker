rc_user="user"
rc_pass="pass"
json_fmt='{"main": {"BackupDir": "", "Transfers": 500}}'
json_str=$(printf "$json_fmt" "$(date +%d_%m_%Y)")
docker exec rclone rclone rc options/set --json "$json_str" --rc-user=$rc_user --rc-pass=$rc_pass
#options=$(docker exec rclone rclone rc options/get --rc-user=$rc_user --rc-pass=$rc_pass)
#echo $options
docker exec rclone rclone rc sync/sync --json '{"srcFs": "gdrive_1:", "dstFs": "gdrive_2:", "_async": true}' --rc-user=$rc_user --rc-pass=$rc_pass
#docker exec -d rclone rclone rc options/set --json '{"main": {"BackupDir": ""}}' --rc-user=$rc_user --rc-pass=$rc_pass
